param(
  [string]$OutputDir = "$PSScriptRoot\dist"
)

$ErrorActionPreference = "Stop"
$Script = Join-Path $PSScriptRoot "retainpdf_relay_proxy.py"
$Manifest = Join-Path $PSScriptRoot "RetainPdfRelayProxy.exe.manifest"

if (-not (Test-Path -LiteralPath $Script)) {
  throw "Proxy script not found: $Script"
}
if (-not (Test-Path -LiteralPath $Manifest)) {
  throw "Manifest not found: $Manifest"
}

$PyInstaller = python -m PyInstaller --version 2>$null
if (-not $?) {
  throw "PyInstaller is not installed. Install it with: python -m pip install pyinstaller"
}

python -m PyInstaller `
  --onefile `
  --noconsole `
  --name RetainPdfRelayProxy `
  --manifest $Manifest `
  --distpath $OutputDir `
  --workpath (Join-Path $OutputDir "build") `
  --specpath $OutputDir `
  $Script
