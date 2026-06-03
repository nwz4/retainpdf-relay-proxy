param(
  [string]$Version = "dev",
  [string]$OutputDir = "",
  [switch]$BuildExe
)

$ErrorActionPreference = "Stop"
$Args = @{
  Version = $Version
}
if ($OutputDir) {
  $Args["OutputDir"] = $OutputDir
}
if ($BuildExe) {
  $Args["BuildExe"] = $true
}

& (Join-Path $PSScriptRoot "scripts\Package-Release.ps1") @Args
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
