"""
build/generate_manifest.py

Generates manifest.json for a release: hashes the compiled crispr-core
binary, fills in the GitHub Release download URLs, writes the file.
Run this AFTER both binaries are built, BEFORE uploading to GitHub Releases.

Usage:
    python build/generate_manifest.py <core_binary_path> <version> <repo>

Example:
    python build/generate_manifest.py dist/crispr-core.exe 0.1.0 vivek11o1/crispr_code
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def hash_file(path: str) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def generate_manifest(core_binary_path: str, version: str, repo: str) -> dict:
    core_path_obj = Path(core_binary_path)
    if not core_path_obj.exists():
        raise FileNotFoundError(f"Core binary not found: {core_binary_path}")

    core_filename = core_path_obj.name
    checksum = hash_file(core_binary_path)

    manifest = {
        "launcher_version": version,
        "core_version": version,
        "core_path": core_filename,
        "core_download_url": f"https://github.com/{repo}/releases/download/v{version}/{core_filename}",
        "sha256": checksum,
        "released_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = Path("manifest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"manifest.json written -> {out_path.resolve()}")
    print(f"  core_path:         {manifest['core_path']}")
    print(f"  core_download_url: {manifest['core_download_url']}")
    print(f"  sha256:            {manifest['sha256']}")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python generate_manifest.py <core_binary_path> <version> <repo>")
        sys.exit(1)
    generate_manifest(core_binary_path=sys.argv[1], version=sys.argv[2], repo=sys.argv[3])