$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
  $Python = "python"
}

& $Python (Join-Path $Root "desktop_app.py")
