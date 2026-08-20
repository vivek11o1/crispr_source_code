#!/usr/bin/env bash
# build/nuitka_build_launcher.sh
# Builds ONLY the launcher binary, for Linux/Mac CI runners or local
# testing on those platforms. Mirrors nuitka_build_launcher.ps1.
#
# Uses GCC/Clang default instead of --zig. See nuitka_build_core.sh
# for why --zig was removed.

set -e

echo "=== Building crispr launcher (Linux/Mac) ==="

cd launcher

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt nuitka --quiet

# -march=x86-64 targets the x86-64 baseline (SSE2 only, no AVX/AVX2/AVX-512).
export CFLAGS="-march=x86-64"

python -m nuitka --onefile --standalone --output-filename=crispr \
    --assume-yes-for-downloads \
    --follow-imports \
    main.py

deactivate
cd ..

echo "Done: launcher/crispr"
echo "Test it now: cd launcher && ./crispr doctor"