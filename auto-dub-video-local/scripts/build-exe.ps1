$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
  $Python = "python"
}

$ArgsList = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--windowed",
  "--onedir",
  "--name", "AutoDubVideoLocal",
  "--paths", (Join-Path $Root "backend"),
  (Join-Path $Root "desktop_app.py")
)

$BinPath = Join-Path $Root "backend\bin"
if (Test-Path $BinPath) {
  $ArgsList += @("--add-data", "$BinPath;bin")
}

& $Python @ArgsList
