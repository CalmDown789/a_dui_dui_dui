param(
    [string]$VitisRun = 'F:\Xilinx\2025.2\Vitis\bin\vitis-run.bat',
    [string]$WorkRoot = 'F:\Xilinx_Installers\pld10h_hls_layer',
    [string]$PythonExe = 'C:\Users\24889\miniforge3\envs\srtp-fsrcnn\python.exe'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $repoRoot 'hls\layer'
$typeHeader = Join-Path $repoRoot 'hls\core\sr_types.hpp'
$resultDir = Join-Path $repoRoot 'results\hls_layer'
$vectorDir = Join-Path $repoRoot 'vectors\layer_smoke'
$vectorGenerator = Join-Path $repoRoot 'python\generate_layer_vector.py'

if (-not (Test-Path -LiteralPath $VitisRun)) {
    throw "Vitis HLS launcher not found: $VitisRun"
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python interpreter not found: $PythonExe"
}

& $PythonExe $vectorGenerator --output $vectorDir
if ($LASTEXITCODE -ne 0) {
    throw "Layer vector generation failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
Get-ChildItem -LiteralPath $sourceDir -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $WorkRoot -Force
}
Copy-Item -LiteralPath $typeHeader -Destination $WorkRoot -Force
Copy-Item -LiteralPath (Join-Path $vectorDir 'layer_vector.hpp') -Destination $WorkRoot -Force

$tclPath = Join-Path $WorkRoot 'run_layer.tcl'
& $VitisRun --mode hls --tcl $tclPath
if ($LASTEXITCODE -ne 0) {
    throw "Vitis HLS layer test failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path $resultDir | Out-Null
$csimLog = Join-Path $WorkRoot 'work\solution1\csim\report\conv3x3_layer_top_csim.log'
$synthReport = Join-Path $WorkRoot 'work\solution1\syn\report\conv3x3_layer_top_csynth.rpt'

Copy-Item -LiteralPath $csimLog -Destination $resultDir -Force
Copy-Item -LiteralPath $synthReport -Destination $resultDir -Force

Write-Host "HLS layer reports copied to $resultDir"
