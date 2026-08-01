#!/usr/bin/env bash
# build/nuitka_build_launcher.sh
# Builds ONLY the launcher binary, for Linux/Mac CI runners or local
# testing on those platforms. Mirrors nuitka_build_launcher.ps1.

set -e

echo "=== Building crispr launcher (Linux/Mac) ==="

cd launcher

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt nuitka --quiet

python -m nuitka --onefile --standalone --output-filename=crispr \
    --follow-imports \
    main.py

deactivate
cd ..

echo "Done: launcher/crispr"
echo "Test it now: cd launcher && ./crispr doctor"