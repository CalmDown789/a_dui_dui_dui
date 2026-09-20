param(
    [string]$VitisRun = 'F:\Xilinx\2025.2\Vitis\bin\vitis-run.bat',
    [string]$WorkRoot = 'F:\Xilinx_Installers\pld10h_hls_window'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $repoRoot 'hls\window'
$typeHeader = Join-Path $repoRoot 'hls\core\sr_types.hpp'
$resultDir = Join-Path $repoRoot 'results\hls_window'

if (-not (Test-Path -LiteralPath $VitisRun)) {
    throw "Vitis HLS launcher not found: $VitisRun"
}

New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
Get-ChildItem -LiteralPath $sourceDir -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $WorkRoot -Force
}
Copy-Item -LiteralPath $typeHeader -Destination $WorkRoot -Force

$tclPath = Join-Path $WorkRoot 'run_window.tcl'
& $VitisRun --mode hls --tcl $tclPath
if ($LASTEXITCODE -ne 0) {
    throw "Vitis HLS window test failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path $resultDir | Out-Null
$csimLog = Join-Path $WorkRoot 'work\solution1\csim\report\window3x3_stream_top_csim.log'
$synthReport = Join-Path $WorkRoot 'work\solution1\syn\report\window3x3_stream_top_csynth.rpt'

Copy-Item -LiteralPath $csimLog -Destination $resultDir -Force
Copy-Item -LiteralPath $synthReport -Destination $resultDir -Force

Write-Host "HLS window reports copied to $resultDir"
