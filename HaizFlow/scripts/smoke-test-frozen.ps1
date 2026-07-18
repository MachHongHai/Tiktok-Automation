param(
  [string]$ArtifactPath = "",
  [switch]$RequireCpuModel,
  [switch]$RequireGpuModel,
  [switch]$ProbeGpu
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (!$ArtifactPath) {
  $ArtifactPath = Join-Path $Root "dist\HaizFlow"
}
$ArtifactPath = [System.IO.Path]::GetFullPath($ArtifactPath)
$Executable = Join-Path $ArtifactPath "HaizFlow.exe"
if (!(Test-Path -LiteralPath $Executable -PathType Leaf)) {
  throw "Frozen executable is missing: $Executable"
}

function Invoke-FrozenCheck {
  param([string[]]$Arguments, [string]$Label)
  $Process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
  if ($Process.ExitCode -ne 0) {
    throw "$Label failed with exit code $($Process.ExitCode)."
  }
  Write-Output "[OK] $Label"
}

$ReleaseArguments = @("--release-smoke")
if ($RequireCpuModel) {
  $ReleaseArguments += "--require-cpu-model"
}
if ($RequireGpuModel) {
  $ReleaseArguments += "--require-gpu-model"
}
Invoke-FrozenCheck -Arguments $ReleaseArguments -Label "Frozen files and native media tools"
Invoke-FrozenCheck -Arguments @("--runtime-probe", "cpu") -Label "Frozen CPU runtime"
if ($ProbeGpu) {
  Invoke-FrozenCheck -Arguments @("--runtime-probe", "gpu") -Label "Frozen GPU runtime"
}

$SmokeParent = [System.IO.Path]::GetFullPath((Join-Path $Root "build\smoke-runtime"))
$SmokeRoot = [System.IO.Path]::GetFullPath((Join-Path $SmokeParent ([guid]::NewGuid().ToString("N"))))
if (![System.IO.Path]::GetDirectoryName($SmokeRoot).Equals($SmokeParent, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to use an unsafe smoke-test directory: $SmokeRoot"
}
$PreviousRuntimeData = $env:RUNTIME_DATA_DIR
$PreviousQtPlatform = $env:QT_QPA_PLATFORM
$PreviousSmokeFlag = $env:HAIZFLOW_SMOKE_TEST
try {
  New-Item -ItemType Directory -Path $SmokeRoot -Force | Out-Null
  $env:RUNTIME_DATA_DIR = $SmokeRoot
  $env:QT_QPA_PLATFORM = "offscreen"
  $env:HAIZFLOW_SMOKE_TEST = "1"
  Invoke-FrozenCheck -Arguments @("--ui-smoke-test") -Label "Frozen Qt/QML startup"
}
finally {
  $env:RUNTIME_DATA_DIR = $PreviousRuntimeData
  $env:QT_QPA_PLATFORM = $PreviousQtPlatform
  $env:HAIZFLOW_SMOKE_TEST = $PreviousSmokeFlag
  if (Test-Path -LiteralPath $SmokeRoot) {
    $ResolvedSmokeRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $SmokeRoot).Path)
    if (![System.IO.Path]::GetDirectoryName($ResolvedSmokeRoot).Equals($SmokeParent, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to delete an unsafe smoke-test directory: $ResolvedSmokeRoot"
    }
    Remove-Item -LiteralPath $ResolvedSmokeRoot -Recurse -Force
  }
}

Write-Output "Frozen release smoke test passed: $ArtifactPath"
