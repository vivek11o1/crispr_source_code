#!/usr/bin/env bash
# build/nuitka_build_core.sh
# Builds ONLY the core binary, for Linux/Mac CI runners or local testing
# on those platforms. Mirrors nuitka_build_core.ps1.

set -e

echo "=== Building crispr-core (Linux/Mac) ==="

cd core

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt nuitka --quiet

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