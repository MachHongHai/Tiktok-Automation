$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
  $Python = "python"
}

& $Python (Join-Path $Root "autodub_desktop.py")
