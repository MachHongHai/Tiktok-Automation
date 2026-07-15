param(
  [switch]$IncludeCpuModel
)

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
  "tornado"
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

$ArgsList += @("--collect-all", "llama_cpp")
$ArgsList += @("--collect-all", "accelerate")
$ArgsList += @("--collect-all", "yt_dlp")

if ($IncludeCpuModel) {
  $SourcePath = Join-Path $Root "src"
  $ModelPath = & $Python -c "import sys; sys.path.insert(0, r'$SourcePath'); from autodub.config import HYMT2_CPU_MODEL_FILE, MODELS_DIR; from pathlib import Path; print(Path(MODELS_DIR) / 'hymt2-gguf' / HYMT2_CPU_MODEL_FILE)"
  if (!(Test-Path -LiteralPath $ModelPath)) {
    throw "CPU model is missing. Run: .venv\Scripts\python.exe scripts\prepare-cpu-model.py"
  }
  $ArgsList += @("--add-data", "$ModelPath;models\hymt2-gguf")
}

& $Python @ArgsList
