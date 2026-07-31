"""
Manifest handling — the trust layer between the launcher and crispr-core.
Owns: reading manifest.json (local, or re-fetched from the release server),
locating the core binary it points to, and verifying its checksum before
anything is ever executed.
"""

import hashlib, json, os, sys, httpx
from pathlib import Path

def _install_dir() -> Path:
    onefile_dir = os.environ.get("NUITKA_ONEFILE_DIRECTORY")
    if onefile_dir:
        return Path(onefile_dir)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

LOCAL_MANIFEST_PATH = _install_dir()/"manifest.json"
REMOTE_MANIFEST_URL = "https://github.com/vivek11o1/crispr_source_code/releases/latest/download/manifest.json"

def read_manifest(force_refresh: bool = False) -> dict:
    if force_refresh:
        _fetch_remote_manifest()
    
    if not LOCAL_MANIFEST_PATH.exists():
        _fetch_remote_manifest()
    
    try:
        with open(LOCAL_MANIFEST_PATH, "r") as f:
            manifest = json.load(f)
    except(json.JSONDecodeError, FileNotFoundError) as e:
        raise RuntimeError(
            f"manifest.json is missing or corrupted ({e}). Run 'crispr repair'."
        )
    _validate_manifest_shape(manifest)
    return manifest

def _fetch_remote_manifest() -> None:
    try:
        resp = httpx.get(REMOTE_MANIFEST_URL, timeout = 10, follow_redirects = True)
        resp.raise_for_status()
        remote_manifest = resp.json()
    except httpx.HTTPError:
        return
    
    tmp_path = LOCAL_MANIFEST_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(remote_manifest,f, indent=2)
    tmp_path.replace(LOCAL_MANIFEST_PATH) 
    
def _validate_manifest_shape(manifest: dict) -> None:
    required_keys = {"launcher_version", "core_version", "core_path", "sha256","core_download_url"}
    missing = required_keys - manifest.keys()
    if missing:
        raise RuntimeError(f"manifest.json missing required keys: {missing}")


def locate_core(manifest: dict) -> str:
    core_path = _install_dir() / manifest["core_path"]
    if not core_path.exists():
        raise FileNotFoundError(
            f"crispr-core not found at {core_path}. Run 'crispr repair'."
        )
    return str(core_path)

def verify_checksum(file_path: str, expected_sha256: str) -> bool:
    """Hash the file at file_path and compare against the manifest's
    recorded checksum. Returns False (never raises) on mismatch — callers
    decide how to react, e.g. main.py blocks launch and suggests repair."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
    except OSError:
        return False
    return sha256.hexdigest() == expected_sha256