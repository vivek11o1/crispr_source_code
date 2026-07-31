# crispr_launcher/ui.py
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()

def print_banner():
    console.print(Panel.fit(
        "[bold cyan]crispr[/bold cyan] — agentic coding CLI",
        border_style="dim"
    ))

def print_checks(checks: list[tuple[str, bool, str]]):
    table = Table(title="crispr doctor", show_lines=False)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    for name, passed, message in checks:
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        table.add_row(name, status, message)

    console.print(table)

def print_health(license_ok: bool, core_ok: bool):
    console.print(f"License:  {'[green]OK[/green]' if license_ok else '[red]NOT VALIDATED[/red]'}")
    console.print(f"Core:     {'[green]OK[/green]' if core_ok else '[red]MISSING/INVALID[/red]'}")

def prompt_api_key(provider_hint: str = "") -> str:
    hint = f" ({provider_hint})" if provider_hint else ""
    return Prompt.ask(f"[bold]Paste your LLM provider API key{hint}[/bold]", password=True)

def print_provider_status(config: dict):
    table = Table(title="Providers", show_header=True)
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Key")

    for name, settings in config["providers"].items():
        marker = "[cyan]->[/cyan] " if name == config["active_provider"] else "  "
        has_key = "[green]set[/green]" if settings["api_key"] else "[dim]not set[/dim]"
        table.add_row(f"{marker}{name}", settings["model"], has_key)

    console.print(table)

def spinner(message: str):
    return console.status(f"[cyan]{message}[/cyan]")