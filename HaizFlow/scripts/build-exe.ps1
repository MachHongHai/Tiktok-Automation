param(
  [switch]$SkipCpuModel,
  [switch]$SkipGpuModel,
  [switch]$SkipWhisperModel,
  [switch]$SkipFrozenSmokeTest
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$DistRoot = [System.IO.Path]::GetFullPath((Join-Path $Root "dist"))
$ArtifactPath = [System.IO.Path]::GetFullPath((Join-Path $DistRoot "HaizFlow"))
$CompliancePath = [System.IO.Path]::GetFullPath((Join-Path $Root "build\release-compliance"))
$FfmpegCompliancePath = [System.IO.Path]::GetFullPath((Join-Path $Root "runtime\compliance\ffmpeg"))
$FfmpegManifestPath = [System.IO.Path]::GetFullPath((Join-Path $Root "runtime\ffmpeg-manifest.json"))
$IncludeCpuModel = !$SkipCpuModel
$IncludeGpuModel = !$SkipGpuModel
$IncludeWhisperModel = !$SkipWhisperModel

function Invoke-PythonChecked {
  param([string[]]$Arguments, [string]$Label)
  & $Python @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE."
  }
}

if (!(Test-Path $Python)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}

Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "verify-runtime.py"), "--for-build") -Label "Runtime verification"
Invoke-PythonChecked -Arguments @((Join-Path $PSScriptRoot "test-ffmpeg-runtime.py")) -Label "FFmpeg codec regression"
Invoke-PythonChecked -Arguments @(
  (Join-Path $PSScriptRoot "generate-third-party-notices.py"),
  "--output", $CompliancePath,
  "--strict"
) -Label "Third-party notice generation"

foreach ($RequiredFile in ("LICENSE", "NOTICE")) {
  if (!(Test-Path -LiteralPath (Join-Path $Root $RequiredFile) -PathType Leaf)) {
    throw "Release compliance file is missing: $RequiredFile"
  }
}
foreach ($RequiredFile in (
  $FfmpegManifestPath,
  (Join-Path $FfmpegCompliancePath "LICENSE.txt"),
  (Join-Path $FfmpegCompliancePath "README.txt"),
  (Join-Path $FfmpegCompliancePath "ffmpeg-8.1.2.tar.xz"),
  (Join-Path $FfmpegCompliancePath "ffmpeg-8.1.2.tar.xz.asc")
)) {
  if (!(Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
    throw "FFmpeg compliance file is missing: $RequiredFile. Run scripts\download_ffmpeg.py."
  }
}

if (Test-Path -LiteralPath $ArtifactPath) {
  if ([System.IO.Path]::GetDirectoryName($ArtifactPath) -ne $DistRoot) {
    throw "Refusing to remove an artifact outside the dist directory: $ArtifactPath"
  }
  Remove-Item -LiteralPath $ArtifactPath -Recurse -Force
}

$ArgsList = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--windowed",
  "--onedir",
  "--name", "HaizFlow",
  "--paths", (Join-Path $Root "src"),
  (Join-Path $Root "haizflow_desktop.py")
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

$QmlPath = Join-Path $Root "src\haizflow\desktop\qml"
if (Test-Path $QmlPath) {
  $ArgsList += @("--add-data", "$QmlPath;haizflow\desktop\qml")
}

$ArgsList += @("--collect-all", "llama_cpp")
$ArgsList += @("--collect-all", "accelerate")
$ArgsList += @("--collect-all", "yt_dlp")
$ArgsList += @("--hidden-import", "haizflow.services.douyin_channel_worker")
$ArgsList += @("--hidden-import", "haizflow.vendor.douyin_xbogus")

if ($IncludeWhisperModel) {
  $SourcePath = Join-Path $Root "src"
  $ModelPath = & $Python -c "import sys; sys.path.insert(0, r'$SourcePath'); from haizflow.config import MODELS_DIR; from pathlib import Path; print(Path(MODELS_DIR) / 'whisper' / 'small')"
  if (!(Test-Path -LiteralPath (Join-Path $ModelPath "model.bin") -PathType Leaf)) {
    throw "Whisper model is missing. Run: .venv\Scripts\python.exe scripts\prepare-whisper-model.py"
  }
  Invoke-PythonChecked -Arguments @(
    "-c", "import sys; sys.path.insert(0, r'$SourcePath'); from pathlib import Path; from haizflow.core.model_integrity import verify_whisper_model; verify_whisper_model(Path(r'$ModelPath'))"
  ) -Label "Pinned Whisper model integrity"
  $ArgsList += @("--add-data", "$ModelPath;models\whisper\small")
}

if ($IncludeCpuModel) {
  $SourcePath = Join-Path $Root "src"
  $ModelPath = & $Python -c "import sys; sys.path.insert(0, r'$SourcePath'); from haizflow.config import HYMT2_CPU_MODEL_FILE, MODELS_DIR; from pathlib import Path; print(Path(MODELS_DIR) / 'hymt2-gguf' / HYMT2_CPU_MODEL_FILE)"
  if (!(Test-Path -LiteralPath $ModelPath)) {
    throw "CPU model is missing. Run: .venv\Scripts\python.exe scripts\prepare-cpu-model.py"
  }
  if ((Get-Item -LiteralPath $ModelPath).Length -lt 500MB) {
    throw "CPU model is incomplete or unexpectedly small: $ModelPath"
  }
  Invoke-PythonChecked -Arguments @(
    "-c", "import sys; sys.path.insert(0, r'$SourcePath'); from pathlib import Path; from haizflow.core.model_integrity import verify_cpu_model; verify_cpu_model(Path(r'$ModelPath'))"
  ) -Label "Pinned CPU model integrity"
  $ModelDirectory = Split-Path -Parent $ModelPath
  $ArgsList += @("--add-data", "$ModelDirectory;models\hymt2-gguf")
}

if ($IncludeGpuModel) {
  $SourcePath = Join-Path $Root "src"
  $ModelPath = & $Python -c "import sys; sys.path.insert(0, r'$SourcePath'); from haizflow.config import MODELS_DIR; from pathlib import Path; print(Path(MODELS_DIR) / 'hymt2-transformers')"
  $GpuWeights = Get-ChildItem -LiteralPath $ModelPath -Filter "*.safetensors" -File -ErrorAction SilentlyContinue
  $GpuWeightBytes = ($GpuWeights | Measure-Object -Property Length -Sum).Sum
  if (!(Test-Path -LiteralPath (Join-Path $ModelPath "config.json")) -or $GpuWeightBytes -lt 2GB) {
    throw "GPU model is missing. Run: .venv\Scripts\python.exe scripts\prepare-gpu-model.py"
  }
  Invoke-PythonChecked -Arguments @(
    "-c", "import sys; sys.path.insert(0, r'$SourcePath'); from pathlib import Path; from haizflow.core.model_integrity import verify_gpu_model; verify_gpu_model(Path(r'$ModelPath'))"
  ) -Label "Pinned GPU model integrity"
  $ArgsList += @("--add-data", "$ModelPath;models\hymt2-transformers")
}

Invoke-PythonChecked -Arguments $ArgsList -Label "PyInstaller build"

if (!(Test-Path -LiteralPath (Join-Path $ArtifactPath "HaizFlow.exe") -PathType Leaf)) {
  throw "PyInstaller did not create the expected artifact: $ArtifactPath"
}

Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination (Join-Path $ArtifactPath "LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $Root "NOTICE") -Destination (Join-Path $ArtifactPath "NOTICE.txt") -Force
Copy-Item -LiteralPath (Join-Path $CompliancePath "THIRD_PARTY_NOTICES.md") -Destination $ArtifactPath -Force
Copy-Item -LiteralPath (Join-Path $CompliancePath "licenses") -Destination (Join-Path $ArtifactPath "licenses") -Recurse -Force
Copy-Item -LiteralPath $FfmpegManifestPath -Destination (Join-Path $ArtifactPath "FFMPEG-MANIFEST.json") -Force
$ArtifactSources = Join-Path $ArtifactPath "sources"
New-Item -ItemType Directory -Path $ArtifactSources -Force | Out-Null
Copy-Item -LiteralPath $FfmpegCompliancePath -Destination $ArtifactSources -Recurse -Force

$FinalizeArguments = @(
  (Join-Path $PSScriptRoot "finalize-release.py"),
  "--artifact", $ArtifactPath
)
if ($IncludeCpuModel) {
  $FinalizeArguments += "--cpu-model"
}
if ($IncludeGpuModel) {
  $FinalizeArguments += "--gpu-model"
}
if ($IncludeWhisperModel) {
  $FinalizeArguments += "--whisper-model"
}
Invoke-PythonChecked -Arguments $FinalizeArguments -Label "Release manifest generation"

if (!$SkipFrozenSmokeTest) {
  $SmokeArguments = @{ ArtifactPath = $ArtifactPath }
  if ($IncludeCpuModel) {
    $SmokeArguments.RequireCpuModel = $true
  }
  if ($IncludeGpuModel) {
    $SmokeArguments.RequireGpuModel = $true
  }
  if ($IncludeWhisperModel) {
    $SmokeArguments.RequireWhisperModel = $true
  }
  $GpuAvailable = (& $Python -c "import torch; print('1' if torch.cuda.is_available() else '0')") -eq "1"
  if ($GpuAvailable) {
    $SmokeArguments.ProbeGpu = $true
  }
  & (Join-Path $PSScriptRoot "smoke-test-frozen.ps1") @SmokeArguments
  if ($LASTEXITCODE -ne 0) {
    throw "Frozen release smoke test failed with exit code $LASTEXITCODE."
  }
}

Write-Output "Release artifact ready: $ArtifactPath"
