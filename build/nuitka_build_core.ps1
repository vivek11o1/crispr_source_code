# build/nuitka_build_core.ps1
# Builds ONLY the core binary. Run this after the launcher build has
# already been confirmed working — isolates which binary broke if
# something goes wrong.

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
    --include-package=langchain_google_genai `
    --include-package=langgraph `
    --zig `
    main.py

deactivate
Pop-Location

Write-Host "Done: core\crispr-core.exe" -ForegroundColor Green
Write-Host "Test it now: cd core; `$env:CRISPR_CONFIG_PATH='<path-to-config.toml>'; .\crispr-core.exe --prompt 'list files here'"