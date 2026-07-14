param(
  [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

$env:PYTHONUTF8 = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

if ($Recreate -and (Test-Path -LiteralPath $Venv)) {
  $ResolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
  $ResolvedVenv = [System.IO.Path]::GetFullPath($Venv).TrimEnd('\')
  if (!$ResolvedVenv.StartsWith($ResolvedRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove a virtual environment outside the project: $ResolvedVenv"
  }
  Remove-Item -LiteralPath $ResolvedVenv -Recurse -Force
}

if (!(Test-Path $Python)) {
  $Bootstrap = Get-Command python -ErrorAction SilentlyContinue
  if (!$Bootstrap) {
    throw "Python 3.11-3.13 is required to create .venv."
  }
  & $Bootstrap.Source -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)"
  if ($LASTEXITCODE -ne 0) {
    throw "Unsupported Python version. Install Python 3.11, 3.12, or 3.13."
  }
  & $Bootstrap.Source -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "requirements.txt")
& $Python -m pip check
& $Python (Join-Path $PSScriptRoot "verify-runtime.py")
