# 成员B工作 / Team member B: padded BRAM window with FIFO backpressure.
param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork=Join-Path $env:TEMP "acx750_member_b_window_stream_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null
$sources=@(
    (Join-Path $taskRoot 'rtl\stream\same_pad_raster.sv'),
    (Join-Path $taskRoot 'rtl\stream\elastic_fifo.sv'),
    (Join-Path $taskRoot 'rtl\stream\window_kminus1_bram.sv'),
    (Join-Path $taskRoot 'rtl\stream\window_stream_frontend.sv'),
    (Join-Path $taskRoot 'tb\window_stream_frontend_tb.sv')
)
foreach($source in $sources){Copy-Item -LiteralPath $source -Destination $xsimWork}
Push-Location $xsimWork
try {
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') '-sv' 'same_pad_raster.sv' 'elastic_fifo.sv' 'window_kminus1_bram.sv' 'window_stream_frontend.sv' 'window_stream_frontend_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & (Join-Path $VivadoRoot 'bin\xelab.bat') 'window_stream_frontend_tb' '-s' 'window_stream_frontend_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & (Join-Path $VivadoRoot 'bin\xsim.bat') 'window_stream_frontend_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally {Pop-Location}
Write-Host "XSIM_WORK=$xsimWork"
