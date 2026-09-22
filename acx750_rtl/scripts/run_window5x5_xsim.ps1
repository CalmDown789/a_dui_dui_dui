param(
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork = Join-Path $env:TEMP "acx750_window5x5_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null

Copy-Item -LiteralPath (Join-Path $taskRoot 'rtl\window\window5x5_stream.v') `
    -Destination $xsimWork
Copy-Item -LiteralPath (Join-Path $taskRoot 'tb\window5x5_stream_tb.sv') `
    -Destination $xsimWork

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

Push-Location $xsimWork
try {
    & $xvlog 'window5x5_stream.v' '-sv' 'window5x5_stream_tb.sv'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & $xelab 'window5x5_stream_tb' '-s' 'window5x5_stream_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & $xsim 'window5x5_stream_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
} finally {
    Pop-Location
}

Write-Host "XSIM_WORK=$xsimWork"
