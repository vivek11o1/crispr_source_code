"""
License Layer — validates the free license key generated on the docs
website, caches the result, and tolerates brief offline periods without
blocking the app. Separate from provider API keys and the GitHub token —
this identifies the INSTALLATION, not which LLM/service it's talking to.
"""

from datetime import datetime , timedelta, timezone
from config import save_config

import httpx

VALIDATE_URL = "https://cripr-docs-backend.onrender.com/api/license/validate"
GRACE_PERIOD = timedelta(days=7)
REVALIDATE_INTERVAL = timedelta(days=7)


def ensure_valid_license(config: dict) -> dict:
    """Called once during bootstrap(). Prompts for a key if missing,
    re-validates on a weekly cadence (not every run), and tolerates the
    validation server being briefly unreachable via a cached grace period.
    Raises RuntimeError only when there is truly no way to proceed."""
    
    lic = config.get("license", {"key": "", "tier": "", "last_validated": ""})
    if not lic.get("key"):
        print("No license key found.")
        print("Generate one for free at: https://crispr-docs-frontend.onrender.com/")   
        lic["key"] = input("paste your license key: ").strip()
        
    needs_check = _needs_revalidation(lic.get("last_validated"))
    
    if needs_check:
        try:
            resp = httpx.post(VALIDATE_URL, json={"license_key": lic["key"]}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            lic["tier"] = data.get("tier", "free")
            lic["last_validated"] = datetime.now(timezone.utc).isoformat()
        except httpx.HTTPError:
            _handle_validatation_failure(lic)
            
    config["license"] = lic
    save_config(config)
    return config   


def _needs_revalidation(last_validated: str) -> bool:
    if not last_validated:
        return True
    last = datetime.fromisoformat(last_validated)
    return datetime.now(timezone.utc) - last > REVALIDATE_INTERVAL

def _handle_validatation_failure(lic: dict) -> None:
    last_validated = lic.get("last_validated")
    if not last_validated:
        raise RuntimeError(
            "Could not validate license and no prior successful validation exists. "
            "Check your internet connection and try again."
        )
    last = datetime.fromisoformat(last_validated)
    age = datetime.now(timezone.utc) - last
    if age < GRACE_PERIOD:
        days_left = (GRACE_PERIOD - age).days
        print(f"[offline: using cached license, please reconnect within {days_left} day(s)]")
    else:
        raise RuntimeError(
            "License could not be revalidated and the offline grace period has expired. "
        )