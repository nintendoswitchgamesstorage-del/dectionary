param([string[]]$StarterPdf = @())
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
function Check-NativeExit {
    if ($LASTEXITCODE -ne 0) { throw "Build command failed with exit code $LASTEXITCODE" }
}
if (-not (Test-Path '.venv-build\Scripts\python.exe')) {
    py -3.12 -m venv .venv-build
    Check-NativeExit
}
$Python = Join-Path (Get-Location) '.venv-build\Scripts\python.exe'
& $Python -m pip install -r backend/requirements.lock -r desktop/requirements-build.txt
Check-NativeExit
npm ci
Check-NativeExit
npm run build
Check-NativeExit
$ImportArguments = @('-m', 'desktop.prepare')
foreach ($Pdf in $StarterPdf) { $ImportArguments += @('--starter-pdf', $Pdf) }
& $Python @ImportArguments
Check-NativeExit
& $Python -m PyInstaller --noconfirm --clean --distpath releases --workpath .packaging/build desktop/LexicalAlchemy.spec
Check-NativeExit
Copy-Item desktop/README-Windows.txt releases/README-Windows.txt
Copy-Item SOURCES.md releases/SOURCES.md
$Hash = (Get-FileHash releases/LexicalAlchemy.exe -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -Path releases/SHA256SUMS.txt -Value "$Hash  LexicalAlchemy.exe" -Encoding ASCII
Compress-Archive -Path releases/LexicalAlchemy.exe,releases/README-Windows.txt,releases/SOURCES.md,releases/SHA256SUMS.txt -DestinationPath releases/LexicalAlchemy-Windows-x64.zip -Force
Write-Host 'Ready: releases/LexicalAlchemy.exe and releases/LexicalAlchemy-Windows-x64.zip'
