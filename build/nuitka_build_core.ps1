# build/nuitka_build_core.ps1
# Builds ONLY the core binary. Run this after the launcher build has
# already been confirmed working — isolates which binary broke if
# something goes wrong.
#
# Uses MSVC (Nuitka's Windows default) instead of --zig. Zig's native
# default targets the build machine's CPU, and its CFLAGS handling
# doesn't support -mcpu=baseline — producing binaries with AVX-512
# instructions that crash on Zen 2 / older CPUs with STATUS_ILLEGAL_INSTRUCTION
# (0xC000001D). MSVC never emits AVX-512 unless /arch:AVX512 is explicit.

$ErrorActionPreference = "Stop"

Write-Host "=== Building crispr-core (Windows) ===" -ForegroundColor Cyan

Push-Location core

if (-not (Test-Path "venv")) {
    python -m venv venv
}
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt nuitka --quiet

python -m nuitka --onefile --standalone --output-filename=crispr-core.exe `
    --windows-console-mode=force `
    --assume-yes-for-downloads `
    --follow-imports `
    --include-package=ui `
    --include-package=langchain_groq `
    --include-package=langchain_openai `
    --include-package=langchain_anthropic `
    --include-package=langgraph `
    main.py

deactivate
Pop-Location

Write-Host "Done: core\crispr-core.exe" -ForegroundColor Green
Write-Host "Test it now: cd core; `$env:CRISPR_CONFIG_PATH='<path-to-config.toml>'; .\crispr-core.exe --prompt 'list files here'"