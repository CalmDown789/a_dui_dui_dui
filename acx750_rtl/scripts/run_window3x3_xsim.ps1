param(
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado'
)

$ErrorActionPreference = 'Stop'

$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork = Join-Path $env:TEMP "acx750_window3x3_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null

$sources = @(
    (Join-Path $taskRoot 'rtl\window\window3x3_stream.v'),
    (Join-Path $taskRoot 'rtl\compute\dot9_pipeline.v'),
    (Join-Path $taskRoot 'rtl\compute\channel_accumulator.v'),
    (Join-Path $taskRoot 'rtl\compute\conv3x3_backend.v'),
    (Join-Path $taskRoot 'tb\window3x3_stream_tb.v'),
    (Join-Path $taskRoot 'tb\window_backend_integration_tb.v')
)

foreach ($source in $sources) {
    Copy-Item -LiteralPath $source -Destination $xsimWork
}

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

foreach ($tool in @($xvlog, $xelab, $xsim)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "Vivado simulator tool not found: $tool"
    }
}

Push-Location $xsimWork
try {
    & $xvlog 'window3x3_stream.v' `
        'dot9_pipeline.v' 'channel_accumulator.v' 'conv3x3_backend.v' `
        'window3x3_stream_tb.v' 'window_backend_integration_tb.v'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }

    & $xelab 'window3x3_stream_tb' '-s' 'window3x3_stream_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }

    & $xsim 'window3x3_stream_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }

    & $xelab 'window_backend_integration_tb' '-s' 'window_backend_integration_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'integration xelab failed' }

    & $xsim 'window_backend_integration_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'integration xsim failed' }
} finally {
    Pop-Location
}

Write-Host "XSIM_WORK=$xsimWork"
