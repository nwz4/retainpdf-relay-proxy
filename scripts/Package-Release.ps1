param(
  [string]$Version = "dev",
  [string]$OutputDir = "",
  [switch]$BuildExe
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
  $OutputDir = Join-Path $ProjectRoot "release"
}

if ($BuildExe) {
  & (Join-Path $PSScriptRoot "Build-WindowsExe.ps1")
}

$PackageName = "retainpdf-relay-proxy-$Version"
$StageDir = Join-Path $OutputDir $PackageName
$ZipPath = Join-Path $OutputDir "$PackageName.zip"

$ResolvedProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$ResolvedOutputDir = [IO.Path]::GetFullPath($OutputDir)
$ResolvedStageDir = [IO.Path]::GetFullPath($StageDir)
if ($ResolvedOutputDir.TrimEnd('\') -ieq $ResolvedProjectRoot.TrimEnd('\')) {
  throw "OutputDir must not be the project root."
}
if (-not $ResolvedStageDir.StartsWith($ResolvedOutputDir.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
  throw "StageDir must stay inside OutputDir."
}

if (Test-Path -LiteralPath $StageDir) {
  Remove-Item -LiteralPath $StageDir -Recurse -Force
}
New-Item -ItemType Directory -Path $StageDir -Force | Out-Null

$RootFiles = @(
  ".gitignore",
  "README.md",
  "LICENSE",
  "Start-RetainPdfRelayProxy.ps1",
  "OneClick-Start-RetainPDF-Relay.bat",
  "OneClick-Start-RetainPDF-Relay.vbs",
  "Build-WindowsExe.ps1",
  "Package-Release.ps1"
)

foreach ($File in $RootFiles) {
  $Source = Join-Path $ProjectRoot $File
  if (Test-Path -LiteralPath $Source) {
    Copy-Item -LiteralPath $Source -Destination (Join-Path $StageDir $File)
  }
}

foreach ($Directory in @("src", "assets", "config", "scripts")) {
  $Source = Join-Path $ProjectRoot $Directory
  if (Test-Path -LiteralPath $Source) {
    Copy-Item -LiteralPath $Source -Destination (Join-Path $StageDir $Directory) -Recurse
  }
}

Get-ChildItem -LiteralPath $StageDir -Directory -Recurse -Force |
  Where-Object { $_.Name -eq "__pycache__" } |
  Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $StageDir -File -Recurse -Force |
  Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
  Remove-Item -Force

$ExePath = Join-Path $ProjectRoot "dist\RetainPdfRelayProxy.exe"
if (Test-Path -LiteralPath $ExePath) {
  $DistDir = Join-Path $StageDir "dist"
  New-Item -ItemType Directory -Path $DistDir | Out-Null
  Copy-Item -LiteralPath $ExePath -Destination (Join-Path $DistDir "RetainPdfRelayProxy.exe")
}

if (Test-Path -LiteralPath $ZipPath) {
  Remove-Item -LiteralPath $ZipPath -Force
}
$PackageItems = Get-ChildItem -LiteralPath $StageDir -Force
Compress-Archive -LiteralPath $PackageItems.FullName -DestinationPath $ZipPath

Write-Host "Release package created:"
Write-Host "  $StageDir"
Write-Host "  $ZipPath"
