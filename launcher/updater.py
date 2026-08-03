"""
Update Manager — checks for a newer crispr-core build, downloads it, and
swaps it in atomically. Every download is routed back through
manifest.py's verify_checksum() before anything replaces the existing
binar
"""

import os, json, httpx
from pathlib import Path
from manifest import (
    REMOTE_MANIFEST_URL,
    LOCAL_MANIFEST_PATH,
    _install_dir,
    verify_checksum,
    _fetch_remote_manifest,
)


def check_for_update() -> dict | None:
    try:
        resp = httpx.get(REMOTE_MANIFEST_URL, timeout=5, follow_redirects=True)
        resp.raise_for_status()
        remote_manifest = resp.json()
        manifest = resp.json()
    except httpx.HTTPError:
        return None
    if not LOCAL_MANIFEST_PATH.exists():
        return remote_manifest
    with open(LOCAL_MANIFEST_PATH) as f:
        local_manifest = json.load(f)
    if remote_manifest["core_version"] != local_manifest["core_version"]:
        return remote_manifest
    return None

def apply_update(manifest: dict) -> None:
    core_url = manifest.get("core_download_url")
    if not core_url:
        raise RuntimeError("manifest.json has no core_download_url — cannot update.")
    
    target_path = _install_dir()/manifest["core_path"]
    tmp_path = target_path.with_suffix(".tmp")
    
    try:
        with httpx.stream("GET", core_url, timeout=60, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
    except httpx.HTTPError as e:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed: {e}")
    if not verify_checksum(str(tmp_path), manifest["sha256"]):
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("Downloaded crispr-core failed checksum verification. Aborted update.")
    # Make it executable on Unix-like systems before swapping in.
    if os.name != "nt":
        os.chmod(tmp_path, 0o755)
    os.replace(tmp_path, target_path)  # atomic swap — same pattern as config.py/manifest.py
    # Only update the local manifest.json once the binary swap succeeded.
    _fetch_remote_manifest()
    