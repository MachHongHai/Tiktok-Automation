param(
  [switch]$SkipCompile
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path -LiteralPath $Python)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}

$env:PYTHONPATH = Join-Path $Root "src"

if (!$SkipCompile) {
  & $Python -m compileall -q (Join-Path $Root "src") (Join-Path $Root "scripts") (Join-Path $Root "test")
  if ($LASTEXITCODE -ne 0) {
    throw "Python compilation failed."
  }
}

& $Python -m unittest discover -s (Join-Path $Root "test") -p "test_*.py"
if ($LASTEXITCODE -ne 0) {
  throw "Test suite failed."
}

