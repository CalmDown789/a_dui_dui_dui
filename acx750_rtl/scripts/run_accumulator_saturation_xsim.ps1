param(
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork = Join-Path $env:TEMP "acx750_accumulator_saturation_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null

$sources = @(
    (Join-Path $taskRoot 'rtl\compute\channel_accumulator.v'),
    (Join-Path $taskRoot 'tb\channel_accumulator_saturation_tb.sv')
)
foreach ($source in $sources) {
    Copy-Item -LiteralPath $source -Destination $xsimWork
}

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

Push-Location $xsimWork
try {
    & $xvlog 'channel_accumulator.v' '-sv' 'channel_accumulator_saturation_tb.sv'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & $xelab 'channel_accumulator_saturation_tb' '-s' 'channel_accumulator_saturation_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & $xsim 'channel_accumulator_saturation_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
} finally {
    Pop-Location
}

Write-Host "XSIM_WORK=$xsimWork"
