[CmdletBinding()]
param(
  [string]$Destination = "",
  [switch]$Move
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root "data"
if ([string]::IsNullOrWhiteSpace($Destination)) {
  $AppDataBase = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME "AppData\Local" }
  $Destination = Join-Path $AppDataBase "AutoDubVideoLocal\data"
}

if (!(Test-Path $Source)) {
  Write-Output "No legacy source data directory found: $Source"
  exit 0
}

$items = @("jobs", "logs", "cache", "models")
if (!$Move) {
  Write-Output "Migration preview. No files were moved."
  Write-Output "Source: $Source"
  Write-Output "Destination: $Destination"
  Write-Output "Run again with -Move after choosing the destination."
  exit 0
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
foreach ($item in $items) {
  $from = Join-Path $Source $item
  $to = Join-Path $Destination $item
  if (!(Test-Path $from)) {
    continue
  }
  if (Test-Path $to) {
    Write-Warning "Skipped existing destination: $to"
    continue
  }
  Move-Item -LiteralPath $from -Destination $to
  Write-Output "Moved $item"
}
