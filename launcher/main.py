"""
The launcher entrypoint — compiles to crispr(.exe).
Owns: bootstrap, config + license loading, doctor/repair/version/config/health
commands, and handing off to crispr-core after manifest verification.
"""


import os
import sys
import subprocess
import typer
from rich.console import Console

from config import load_config, save_config, detect_provider, set_provider_key, set_github_token, _parse_config_file
from license import ensure_valid_license
from manifest import read_manifest, locate_core, verify_checksum, _install_dir
from env_check import run_all_checks
from updater import check_for_update, apply_update
from logging_setup import setup_logging

from UI import print_banner, print_checks, print_health, prompt_api_key, print_provider_status, spinner


from pathlib import Path
from platformdirs import user_config_dir

CONFIG_DIR = Path(user_config_dir("crispr"))
CONFIG_FILE = CONFIG_DIR/"config.toml"

console = Console()

_SUBCOMMANDS = {"doctor", "repair", "update", "version", "config", "health"}


def _run_prompt_mode(prompt_text: str, session_id: str | None = None) -> None:
    """Full bootstrap + launch core with the given prompt."""
    setup_logging()
    config = load_config()

    if not config["providers"].get(config["active_provider"], {}).get("api_key"):
        config = _prompt_for_provider_key(config)

    with spinner("Validating license..."):
        config = ensure_valid_license(config)

    core_path = _verify_core(config)
    args = [core_path, "--prompt", prompt_text]
    if session_id:
        args += ["--session", session_id]
    result = subprocess.run(args, env=_core_env(config))
    sys.exit(result.returncode)


def _prompt_for_provider_key(config: dict) -> dict:
    api_key = prompt_api_key()
    provider = detect_provider(api_key)

    if provider is None:
        provider = typer.prompt("Couldn't detect provider. Enter manually (zen/groq/openai/claude)")
    config = set_provider_key(config, provider, api_key)
    config["active_provider"] = provider
    save_config(config)
    typer.echo(f"Provider set to {provider}.")
    return config


def _verify_core(config: dict) -> str:
    manifest = read_manifest()
    try:
        core_path = locate_core(manifest)
    except FileNotFoundError:
        typer.secho(
            f"crispr-core is missing. Run 'crispr repair' to download it.",
            fg=typer.colors.RED,
        )
        sys.exit(1)

    if not verify_checksum(core_path, manifest["sha256"]):
        typer.secho(
            "crispr-core failed checksum verification. Run 'crispr repair'.",
            fg=typer.colors.RED,
        )
        sys.exit(1)
    return core_path

def _core_env(config: dict) -> dict:
    env = os.environ.copy()
    env["CRISPR_CONFIG_PATH"] = str(CONFIG_FILE)
    env["CRISPR_ACTIVE_PROVIDER"] = config["active_provider"]
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# ── Typer subcommands ──────────────────────────────────────────────

app = typer.Typer(add_completion=False)

@app.command()
def doctor():
    """Run environment + config + license checks, report pass/fail."""

    config = load_config()
    checks = run_all_checks(config)
    all_passed = True

    for name, passed, message in checks:
        icon = "PASS" if passed else "FAIL"
        typer.echo(f"[{icon}] {name}: {message}")
        all_passed = all_passed and passed

    if not all_passed:
        console.print("\n[yellow]Run 'crispr repair' to attempt fixes.[/yellow]")
        raise typer.Exit(1)

@app.command()
def repair():
    """Attempt to fix common issues: manifest, core binary, corrupted config."""
    typer.echo("Re-fetching manifest...")
    manifest = read_manifest(force_refresh=True)
    core_path = _install_dir() / manifest["core_path"]
    if not core_path.exists() or not verify_checksum(core_path, manifest["sha256"]):
        typer.echo("crispr-core missing or checksum invalid. Re-downloading...")
        apply_update(manifest)
    config = load_config()
    save_config(config)
    typer.echo("Repair complete. Run 'crispr doctor' to confirm.")

@app.command()
def update():
    """Check for and apply a newer crispr-core build."""
    new_manifest = check_for_update()

    if new_manifest is None:
        typer.echo("crispr-core is already up to date.")
        return

    typer.echo(f"Updating core to version {new_manifest['core_version']}...")
    apply_update(new_manifest)
    typer.echo("Update complete.")

@app.command()
def version():
    manifest = read_manifest()
    typer.echo(f"launcher {manifest.get('launcher_version', 'unknown')}")
    typer.echo(f"core     {manifest.get('core_version', 'unknown')}")

@app.command(name="config")
def config_cmd(
    action: str = typer.Argument("show"),
    provider: str = typer.Argument(None),
):
    """crispr config show | set <provider>"""
    config = load_config()

    if action == "show":
        print_provider_status(config)
        return

    if action == "set":
        if provider == "github":
            token = typer.prompt("GitHub Personal Access Token", hide_input=True)
            config = set_github_token(config, token)
            typer.echo("GitHub token saved.")
        else:
            api_key = typer.prompt(f"API key for {provider}", hide_input=True)
            config = set_provider_key(config, provider, api_key)
            config["active_provider"] = provider
            save_config(config)
            typer.echo(f"Switched to {provider}.")

@app.command()
def health():
    """Quick status: license valid? core present/valid?"""
    config = load_config()
    license_ok = bool(config["license"].get("last_validated"))
    manifest = read_manifest()
    try:
        core_path = locate_core(manifest)
        core_ok = verify_checksum(core_path, manifest["sha256"])
    except Exception:
        core_ok = False
    typer.echo(f"License:  {'OK' if license_ok else 'NOT VALIDATED'}")
    typer.echo(f"Core:     {'OK' if core_ok else 'MISSING/INVALID'}")


# ── Main dispatch ──────────────────────────────────────────────────

def main():
    """Dispatch: if first arg is a known subcommand, let Typer handle it.
    Otherwise treat everything as a prompt for crispr-core."""
    setup_logging()

    if len(sys.argv) > 1 and sys.argv[1] in _SUBCOMMANDS:
        app()
    else:
        prompt_words = list(sys.argv[1:])
        session_id = None
        if "--session" in prompt_words:
            idx = prompt_words.index("--session")
            prompt_words.pop(idx)
            if idx < len(prompt_words):
                session_id = prompt_words.pop(idx)
        prompt_text = " ".join(prompt_words) if prompt_words else typer.prompt("What do you want me to do")
        _run_prompt_mode(prompt_text, session_id=session_id)


if __name__ == "__main__":
    main()
