#!/usr/bin/env bash
# build/nuitka_build_core.sh
# Builds ONLY the core binary, for Linux/Mac CI runners or local testing
# on those platforms. Mirrors nuitka_build_core.ps1.
#
# Uses GCC/Clang default instead of --zig. Zig's native default targets
# the build machine's CPU, producing binaries with AVX-512 instructions
# that crash on older CPUs with STATUS_ILLEGAL_INSTRUCTION (0xC000001D).

set -e

echo "=== Building crispr-core (Linux/Mac) ==="

cd core

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt nuitka --quiet

# -march=x86-64 targets the x86-64 baseline (SSE2 only, no AVX/AVX2/AVX-512).
# Works with both GCC and Clang. On Mac/arm64 this flag is ignored (arm64
# doesn't have x86 SIMD tiers).
export CFLAGS="-march=x86-64"

python -m nuitka --onefile --standalone --output-filename=crispr-core \
    --assume-yes-for-downloads \
    --follow-imports \
    --include-package=ui \
    --include-package=langchain_groq \
    --include-package=langchain_openai \
    --include-package=langchain_anthropic \
    --include-package=langgraph \
    main.py

deactivate
cd ..

echo "Done: core/crispr-core"
echo "Test it now: cd core && CRISPR_CONFIG_PATH=<path-to-config.toml> ./crispr-core --prompt 'list files here'"