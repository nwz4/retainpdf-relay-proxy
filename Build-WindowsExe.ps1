param(
  [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$Args = @{}
if ($OutputDir) {
  $Args["OutputDir"] = $OutputDir
}

& (Join-Path $PSScriptRoot "scripts\Build-WindowsExe.ps1") @Args
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
