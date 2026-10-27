$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE) { throw 'Install Python 3.11 or newer before setup' }
}
& '.venv/Scripts/python.exe' -m pip install -r requirements.lock.txt
if ($LASTEXITCODE) { throw 'Python dependencies failed to install' }
& '.venv/Scripts/python.exe' -m pip install --no-deps -e .
if ($LASTEXITCODE) { throw 'AI KVM package installation failed' }
