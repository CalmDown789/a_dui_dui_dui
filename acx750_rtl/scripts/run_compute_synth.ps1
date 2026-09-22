param(
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado',
    [string]$Part = 'xc7a200tfbg484-2',
    [string]$ResultLabel = 'xc7a200t_compute_baseline'
)

$ErrorActionPreference = 'Stop'

$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$synthWork = Join-Path $env:TEMP "acx750_compute_synth_$stamp"
$reportWork = Join-Path $synthWork 'reports'
New-Item -ItemType Directory -Path $synthWork | Out-Null

$sources = @(
    (Join-Path $taskRoot 'rtl\compute\dot9_pipeline.v'),
    (Join-Path $taskRoot 'rtl\compute\channel_accumulator.v'),
    (Join-Path $taskRoot 'rtl\compute\conv3x3_backend.v'),
    (Join-Path $taskRoot 'constraints\clock_200mhz_benchmark.xdc'),
    (Join-Path $PSScriptRoot 'synth_compute_baseline.tcl')
)

foreach ($source in $sources) {
    Copy-Item -LiteralPath $source -Destination $synthWork
}

$vivado = Join-Path $VivadoRoot 'bin\vivado.bat'
if (-not (Test-Path -LiteralPath $vivado)) {
    throw "Vivado not found: $vivado"
}

Push-Location $synthWork
try {
    & $vivado '-mode' 'batch' '-source' 'synth_compute_baseline.tcl' `
        '-tclargs' $synthWork $reportWork $Part
    if ($LASTEXITCODE -ne 0) { throw 'Vivado synthesis failed' }
} finally {
    Pop-Location
}

$savedReports = Join-Path $taskRoot (Join-Path 'results' $ResultLabel)
New-Item -ItemType Directory -Path $savedReports -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $reportWork 'compute_baseline_utilization.rpt') `
    -Destination $savedReports -Force
Copy-Item -LiteralPath (Join-Path $reportWork 'compute_baseline_timing_synth.rpt') `
    -Destination $savedReports -Force

Write-Host "SYNTH_WORK=$synthWork"
Write-Host "SAVED_REPORTS=$savedReports"
