param(
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork = Join-Path $env:TEMP "acx750_dot25_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null

$sources = @(
    (Join-Path $taskRoot 'rtl\compute\dsp_signed_mult.v'),
    (Join-Path $taskRoot 'rtl\compute\dot25_pipeline.v'),
    (Join-Path $taskRoot 'tb\dot25_pipeline_tb.sv')
)
foreach ($source in $sources) {
    Copy-Item -LiteralPath $source -Destination $xsimWork
}

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

Push-Location $xsimWork
try {
    & $xvlog 'dsp_signed_mult.v' 'dot25_pipeline.v' '-sv' 'dot25_pipeline_tb.sv'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & $xelab 'dot25_pipeline_tb' '-s' 'dot25_pipeline_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & $xsim 'dot25_pipeline_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
} finally {
    Pop-Location
}

Write-Host "XSIM_WORK=$xsimWork"
