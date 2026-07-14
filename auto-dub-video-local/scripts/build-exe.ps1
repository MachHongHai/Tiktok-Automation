$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}

& $Python (Join-Path $PSScriptRoot "verify-runtime.py") --for-build

$ArgsList = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--windowed",
  "--onedir",
  "--name", "AutoDubVideoLocal",
  "--paths", (Join-Path $Root "src"),
  (Join-Path $Root "autodub_desktop.py")
)

$ExcludedModules = @(
  "bokeh",
  "cupy",
  "dash",
  "dask",
  "distributed",
  "django",
  "flask",
  "IPython",
  "ipywidgets",
  "jupyter",
  "jupyterlab",
  "notebook",
  "plotly",
  "pytest",
  "sklearn",
  "sqlalchemy",
  "tensorboard",
  "tensorflow",
  "torch.utils.tensorboard",
  "tornado",
  "yt_dlp"
)

foreach ($Module in $ExcludedModules) {
  $ArgsList += @("--exclude-module", $Module)
}

$BinPath = Join-Path $Root "runtime\bin"
if (Test-Path $BinPath) {
  $ArgsList += @("--add-data", "$BinPath;bin")
}

$QmlPath = Join-Path $Root "src\autodub\desktop\qml"
if (Test-Path $QmlPath) {
  $ArgsList += @("--add-data", "$QmlPath;autodub\desktop\qml")
}

& $Python @ArgsList
