$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}

$env:PYTHONUTF8 = "1"
Push-Location $Root
try {
  & $Python (Join-Path $Root "haizflow_desktop.py")
} finally {
  Pop-Location
}
