param(
  [string]$Version = "dev",
  [string]$OutputDir = "$PSScriptRoot\release",
  [switch]$BuildExe
)

$ErrorActionPreference = "Stop"

if ($BuildExe) {
  & (Join-Path $PSScriptRoot "Build-WindowsExe.ps1")
}

$PackageName = "retainpdf-relay-proxy-$Version"
$StageDir = Join-Path $OutputDir $PackageName
$ZipPath = Join-Path $OutputDir "$PackageName.zip"

if ((Resolve-Path -LiteralPath $PSScriptRoot).Path -eq (Resolve-Path -LiteralPath $OutputDir -ErrorAction SilentlyContinue).Path) {
  throw "OutputDir must not be the project root."
}

if (Test-Path -LiteralPath $StageDir) {
  Remove-Item -LiteralPath $StageDir -Recurse -Force
}
New-Item -ItemType Directory -Path $StageDir -Force | Out-Null

$Files = @(
  "retainpdf_relay_proxy.py",
  "retainpdf-relay-proxy.example.json",
  "Start-RetainPdfRelayProxy.ps1",
  "OneClick-Start-RetainPDF-Relay.bat",
  "OneClick-Start-RetainPDF-Relay.vbs",
  "Build-WindowsExe.ps1",
  "Package-Release.ps1",
  "RetainPdfRelayProxy.exe.manifest",
  "README.md",
  "LICENSE",
  ".gitignore"
)

foreach ($File in $Files) {
  $Source = Join-Path $PSScriptRoot $File
  if (Test-Path -LiteralPath $Source) {
    Copy-Item -LiteralPath $Source -Destination (Join-Path $StageDir $File)
  }
}

$ExePath = Join-Path $PSScriptRoot "dist\RetainPdfRelayProxy.exe"
if (Test-Path -LiteralPath $ExePath) {
  $DistDir = Join-Path $StageDir "dist"
  New-Item -ItemType Directory -Path $DistDir | Out-Null
  Copy-Item -LiteralPath $ExePath -Destination (Join-Path $DistDir "RetainPdfRelayProxy.exe")
}

if (Test-Path -LiteralPath $ZipPath) {
  Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath

Write-Host "Release package created:"
Write-Host "  $StageDir"
Write-Host "  $ZipPath"
