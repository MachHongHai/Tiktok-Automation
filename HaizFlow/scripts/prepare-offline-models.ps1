param(
  [switch]$SkipCpuModel,
  [switch]$SkipGpuModel,
  [switch]$SkipWhisperModel
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "Project environment is missing. Run scripts\install-desktop-env.ps1 first."
}

$Scripts = @()
if (!$SkipWhisperModel) { $Scripts += "prepare-whisper-model.py" }
if (!$SkipCpuModel) { $Scripts += "prepare-cpu-model.py" }
if (!$SkipGpuModel) { $Scripts += "prepare-gpu-model.py" }

foreach ($Script in $Scripts) {
  & $Python (Join-Path $PSScriptRoot $Script)
  if ($LASTEXITCODE -ne 0) {
    throw "$Script failed with exit code $LASTEXITCODE."
  }
}

Write-Output "Pinned offline models are ready under the configured MODELS_DIR."
