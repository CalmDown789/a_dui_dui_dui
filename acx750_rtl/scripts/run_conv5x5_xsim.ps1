param(
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork = Join-Path $env:TEMP "acx750_conv5x5_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null

$sources = @(
    (Join-Path $taskRoot 'rtl\window\window5x5_stream.v'),
    (Join-Path $taskRoot 'rtl\compute\dsp_signed_mult.v'),
    (Join-Path $taskRoot 'rtl\compute\dot25_pipeline.v'),
    (Join-Path $taskRoot 'rtl\compute\channel_accumulator.v'),
    (Join-Path $taskRoot 'rtl\compute\conv5x5_backend.v'),
    (Join-Path $taskRoot 'tb\conv5x5_backend_tb.sv'),
    (Join-Path $taskRoot 'tb\window5_backend_integration_tb.sv')
)
foreach ($source in $sources) {
    Copy-Item -LiteralPath $source -Destination $xsimWork
}

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

Push-Location $xsimWork
try {
    & $xvlog 'window5x5_stream.v' 'dsp_signed_mult.v' 'dot25_pipeline.v' `
        'channel_accumulator.v' 'conv5x5_backend.v' '-sv' `
        'conv5x5_backend_tb.sv' 'window5_backend_integration_tb.sv'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }

    & $xelab 'conv5x5_backend_tb' '-s' 'conv5x5_backend_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'backend xelab failed' }
    & $xsim 'conv5x5_backend_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'backend xsim failed' }

    & $xelab 'window5_backend_integration_tb' '-s' 'window5_backend_integration_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'integration xelab failed' }
    & $xsim 'window5_backend_integration_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'integration xsim failed' }
} finally {
    Pop-Location
}

Write-Host "XSIM_WORK=$xsimWork"
