param(
  [string]$Config = "$PSScriptRoot\retainpdf-relay-proxy.json",
  [string]$RetainPdfExe = "",
  [switch]$Gui,
  [switch]$ConfigureAndRun,
  [switch]$PatchDesktopConfig,
  [string]$DesktopConfig = "",
  [string]$RetainPdfApiKey = "",
  [switch]$Background
)

$ErrorActionPreference = "Stop"
$Script = Join-Path $PSScriptRoot "retainpdf_relay_proxy.py"

if (-not (Test-Path -LiteralPath $Script)) {
  throw "Proxy script not found: $Script"
}

$Python = "python"
$Args = @($Script)
if ($Config -and ((Test-Path -LiteralPath $Config) -or $Gui -or $ConfigureAndRun)) {
  $Args += @("--config", $Config)
}
if ($RetainPdfExe) {
  $Args += @("--launch", $RetainPdfExe)
}
if ($Gui) {
  $Args += "--gui"
}
if ($ConfigureAndRun) {
  $Args += "--configure-and-run"
}
if ($PatchDesktopConfig) {
  $Args += "--patch-desktop-config"
}
if ($DesktopConfig) {
  $Args += @("--desktop-config", $DesktopConfig)
}
if ($RetainPdfApiKey) {
  $Args += @("--retainpdf-api-key", $RetainPdfApiKey)
}

if ($Background) {
  $UsePythonW = $false
  $PythonW = Get-Command pythonw -ErrorAction SilentlyContinue
  if ($PythonW) {
    $Python = $PythonW.Source
    $UsePythonW = $true
  }

  $StartParams = @{
    FilePath = $Python
    ArgumentList = $Args
    WorkingDirectory = $PSScriptRoot
  }
  if (-not $UsePythonW) {
    $StartParams.WindowStyle = "Hidden"
  }
  Start-Process @StartParams
  return
}

& $Python @Args
