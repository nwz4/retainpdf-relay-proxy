param(
  [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
  $OutputDir = Join-Path $ProjectRoot "dist"
}

$Script = Join-Path $ProjectRoot "src\retainpdf_relay_proxy.py"
$AssetsDir = Join-Path $ProjectRoot "assets"
$Manifest = Join-Path $AssetsDir "RetainPdfRelayProxy.exe.manifest"
$Icon = Join-Path $AssetsDir "retainpdf-relay-proxy.ico"

if (-not (Test-Path -LiteralPath $Script)) {
  throw "Proxy script not found: $Script"
}
if (-not (Test-Path -LiteralPath $Manifest)) {
  throw "Manifest not found: $Manifest"
}
if (-not (Test-Path -LiteralPath $Icon)) {
  throw "Icon not found: $Icon"
}

python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
  Write-Host "PyInstaller is not installed. Install it with: python -m pip install pyinstaller"
  exit 1
}

python -m PyInstaller `
  --onefile `
  --noconsole `
  --name RetainPdfRelayProxy `
  --manifest $Manifest `
  --icon $Icon `
  --add-data "$AssetsDir;assets" `
  --distpath $OutputDir `
  --workpath (Join-Path $OutputDir "build") `
  --specpath $OutputDir `
  $Script
