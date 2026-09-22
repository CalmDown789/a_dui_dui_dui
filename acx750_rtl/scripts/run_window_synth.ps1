param(
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado',
    [string]$Part = 'xc7a200tfbg484-2',
    [string]$ResultPrefix = 'xc7a200t',
    [string]$CaseLabel = ''
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$vivado = Join-Path $VivadoRoot 'bin\vivado.bat'
$cases = @(
    @{ Top='window3x3_stream'; Source='window3x3_stream.v'; Label='window3x3' },
    @{ Top='window3x3_bram'; Source='window3x3_bram.v'; Label='window3x3_bram' },
    @{ Top='window5x5_stream'; Source='window5x5_stream.v'; Label='window5x5' },
    @{ Top='window5x5_bram'; Source='window5x5_bram.v'; Label='window5x5_bram' }
)

foreach ($case in $cases) {
    if ((-not [string]::IsNullOrWhiteSpace($CaseLabel)) -and
        ($case.Label -ne $CaseLabel)) {
        continue
    }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $synthWork = Join-Path $env:TEMP "acx750_$($case.Label)_synth_$stamp"
    $reportWork = Join-Path $synthWork 'reports'
    New-Item -ItemType Directory -Path $synthWork | Out-Null

    Copy-Item -LiteralPath (Join-Path $taskRoot "rtl\window\$($case.Source)") `
        -Destination $synthWork
    Copy-Item -LiteralPath (Join-Path $taskRoot 'constraints\clock_200mhz_benchmark.xdc') `
        -Destination $synthWork
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'synth_window_baseline.tcl') `
        -Destination $synthWork

    Push-Location $synthWork
    try {
        & $vivado '-mode' 'batch' '-source' 'synth_window_baseline.tcl' `
            '-tclargs' $synthWork $reportWork $Part $case.Top $case.Source
        if ($LASTEXITCODE -ne 0) { throw "Vivado synthesis failed: $($case.Top)" }
    } finally {
        Pop-Location
    }

    $savedReports = Join-Path $taskRoot `
        (Join-Path 'results' "$($ResultPrefix)_$($case.Label)_baseline")
    New-Item -ItemType Directory -Path $savedReports -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $reportWork 'window_utilization.rpt') `
        -Destination $savedReports -Force
    Copy-Item -LiteralPath (Join-Path $reportWork 'window_timing_synth.rpt') `
        -Destination $savedReports -Force
    Write-Host "SAVED_REPORTS=$savedReports"
}
