# build/nuitka_build_launcher.ps1
# Builds ONLY the launcher binary. Run and test this in isolation before
# touching core, per the "test each binary independently" rule.

$ErrorActionPreference = "Stop"

Write-Host "=== Building crispr launcher (Windows) ===" -ForegroundColor Cyan

Push-Location launcher

if (-not (Test-Path "venv")) {
    python -m venv venv
}
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt nuitka --quiet

# Baseline CPU target so the binary runs on older machines. Zig's native
# default targets the build machine's CPU, which crashes elsewhere with
# STATUS_ILLEGAL_INSTRUCTION (0xC000001D).
$env:CFLAGS = "-mcpu=baseline"

python -m nuitka --onefile --standalone --output-filename=crispr.exe `
    --windows-console-mode=force `
    --assume-yes-for-downloads `
    --follow-imports `
    --zig `
    main.py

deactivate
Pop-Location

Write-Host "Done: launcher\crispr.exe" -ForegroundColor Green
Write-Host "Test it now: cd launcher; .\crispr.exe doctor"