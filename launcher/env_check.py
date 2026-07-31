"""
Environment Checks — what `crispr doctor` reports on. Each check returns
(name, passed, message) so doctor() can print a uniform pass/fail list
without needing to know the specifics of any individual check.
"""
import os
import shutil
import socket
def check_git() -> tuple[str, bool, str]:
    if shutil.which("git") is None:
        return ("git", False, "not found — install from https://git-scm.com/downloads")
    return ("git", True, "found")

def check_network() -> tuple[str, bool, str]:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return ("network", True, "reachable")
    except OSError:
        return ("network", False, "no internet connection detected")
    
def check_disk_space(min_mb: int = 500) -> tuple[str, bool, str]:
    stat = shutil.disk_usage(os.path.expanduser("~"))
    free_mb = stat.free // (1024 * 1024)
    if free_mb < min_mb:
        return ("disk_space", False, f"only {free_mb}MB free, need {min_mb}MB")
    return ("disk_space", True, f"{free_mb}MB free")

def check_config(config: dict) -> tuple[str, bool, str]:
    if not config.get("providers") or not any(
        p.get("api_key") for p in config["providers"].values()
    ):
        return ("config", False, "no provider API key configured")
    return ("config", True, "valid")

def check_license(config: dict) -> tuple[str, bool, str]:
    if not config.get("license", {}).get("last_validated"):
        return ("license", False, "not yet validated — run crispr once to set up")
    return ("license", True, "validated")

def run_all_checks(config: dict) -> list[tuple[str, bool, str]]:
    
    return [
        check_git(),
        check_network(),
        check_disk_space(),
        check_config(config),
        check_license(config),
    ]