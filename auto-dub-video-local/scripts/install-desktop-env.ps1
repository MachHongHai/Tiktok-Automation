$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

if (!(Test-Path $Python)) {
  python -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "requirements.txt")
