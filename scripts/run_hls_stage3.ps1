param(
    [string]$VitisRun = 'F:\Xilinx\2025.2\Vitis\bin\vitis-run.bat',
    [string]$WorkRoot = 'F:\Xilinx_Installers\pld10h_hls_stage3'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$stageDir = Join-Path $repoRoot 'hls\stage3'
$resultDir = Join-Path $repoRoot 'results\hls_stage3'

if (-not (Test-Path -LiteralPath $VitisRun)) {
    throw "Vitis HLS launcher not found: $VitisRun"
}

New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
Get-ChildItem -LiteralPath $stageDir -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $WorkRoot -Force
}

$supportFiles = @(
    (Join-Path $repoRoot 'hls\core\sr_types.hpp'),
    (Join-Path $repoRoot 'hls\layer\conv3x3_layer.hpp'),
    (Join-Path $repoRoot 'hls\layer\conv3x3_layer.cpp'),
    (Join-Path $repoRoot 'hls\postprocess\postprocess.hpp'),
    (Join-Path $repoRoot 'hls\postprocess\postprocess.cpp'),
    (Join-Path $repoRoot 'hls\pixel_shuffle\pixel_shuffle.hpp'),
    (Join-Path $repoRoot 'hls\pixel_shuffle\pixel_shuffle.cpp')
)
foreach ($file in $supportFiles) {
    Copy-Item -LiteralPath $file -Destination $WorkRoot -Force
}

$tclPath = Join-Path $WorkRoot 'run_stage3.tcl'
& $VitisRun --mode hls --tcl $tclPath
if ($LASTEXITCODE -ne 0) {
    throw "Vitis HLS stage3 test failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path $resultDir | Out-Null
$csimLog = Join-Path $WorkRoot 'work\solution1\csim\report\stage3_pipeline_top_csim.log'
$synthReport = Join-Path $WorkRoot 'work\solution1\syn\report\stage3_pipeline_top_csynth.rpt'

Copy-Item -LiteralPath $csimLog -Destination $resultDir -Force
Copy-Item -LiteralPath $synthReport -Destination $resultDir -Force

Write-Host "HLS stage3 reports copied to $resultDir"
