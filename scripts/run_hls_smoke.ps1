param(
    [string]$VitisRun = 'F:\Xilinx\2025.2\Vitis\bin\vitis-run.bat',
    [string]$WorkRoot = 'F:\Xilinx_Installers\pld10h_hls_smoke'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $repoRoot 'hls\smoke'

if (-not (Test-Path -LiteralPath $VitisRun)) {
    throw "Vitis HLS launcher not found: $VitisRun"
}

New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceDir 'add_one.cpp') -Destination $WorkRoot -Force
Copy-Item -LiteralPath (Join-Path $sourceDir 'add_one_tb.cpp') -Destination $WorkRoot -Force
Copy-Item -LiteralPath (Join-Path $sourceDir 'run_smoke.tcl') -Destination $WorkRoot -Force

$tclPath = Join-Path $WorkRoot 'run_smoke.tcl'
& $VitisRun --mode hls --tcl $tclPath
if ($LASTEXITCODE -ne 0) {
    throw "Vitis HLS smoke test failed with exit code $LASTEXITCODE"
}
