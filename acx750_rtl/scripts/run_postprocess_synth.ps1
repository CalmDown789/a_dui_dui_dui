param(
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado',
    [string]$Part = 'xc7z020clg400-1',
    [string]$ResultLabel = 'fallback_xc7z020_postprocess'
)

$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$synthWork=Join-Path $env:TEMP "acx750_postprocess_synth_$stamp"
$reportWork=Join-Path $synthWork 'reports'
New-Item -ItemType Directory -Path $synthWork | Out-Null
foreach($source in @(
    (Join-Path $taskRoot 'rtl\postprocess\prelu_requantize.sv'),
    (Join-Path $taskRoot 'constraints\clock_200mhz_benchmark.xdc'),
    (Join-Path $PSScriptRoot 'synth_postprocess_baseline.tcl')
)){Copy-Item -LiteralPath $source -Destination $synthWork}

$vivado=Join-Path $VivadoRoot 'bin\vivado.bat'
Push-Location $synthWork
try{
    foreach($configuration in @(
        @{Label='hidden_i16'; OutWidth='16'; OutSigned='1'; ApplyPrelu='1'},
        @{Label='output_u8'; OutWidth='8'; OutSigned='0'; ApplyPrelu='0'}
    )){
        & $vivado '-mode' 'batch' '-source' 'synth_postprocess_baseline.tcl' '-tclargs' `
            $synthWork $reportWork $Part $configuration.OutWidth `
            $configuration.OutSigned $configuration.ApplyPrelu $configuration.Label
        if($LASTEXITCODE-ne 0){throw "Vivado synthesis failed: $($configuration.Label)"}
    }
}finally{Pop-Location}

$savedReports=Join-Path $taskRoot (Join-Path 'results' $ResultLabel)
New-Item -ItemType Directory -Path $savedReports -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $reportWork 'hidden_i16_utilization.rpt') -Destination $savedReports -Force
Copy-Item -LiteralPath (Join-Path $reportWork 'hidden_i16_timing_synth.rpt') -Destination $savedReports -Force
Copy-Item -LiteralPath (Join-Path $reportWork 'output_u8_utilization.rpt') -Destination $savedReports -Force
Copy-Item -LiteralPath (Join-Path $reportWork 'output_u8_timing_synth.rpt') -Destination $savedReports -Force
Write-Host "SYNTH_WORK=$synthWork"
Write-Host "SAVED_REPORTS=$savedReports"
