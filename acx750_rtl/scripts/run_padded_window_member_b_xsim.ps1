# 成员B工作 / Team member B: SAME padding plus BRAM window regression.
param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork=Join-Path $env:TEMP "acx750_member_b_padded_window_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null
$sources=@(
    (Join-Path $taskRoot 'rtl\stream\same_pad_raster.sv'),
    (Join-Path $taskRoot 'rtl\window\window3x3_bram.v'),
    (Join-Path $taskRoot 'rtl\window\window5x5_bram.v'),
    (Join-Path $taskRoot 'tb\padded_window_member_b_tb.sv')
)
foreach($source in $sources){Copy-Item -LiteralPath $source -Destination $xsimWork}
Push-Location $xsimWork
try {
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') '-sv' 'same_pad_raster.sv' 'window3x3_bram.v' 'window5x5_bram.v' 'padded_window_member_b_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & (Join-Path $VivadoRoot 'bin\xelab.bat') 'padded_window_member_b_tb' '-s' 'padded_window_member_b_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & (Join-Path $VivadoRoot 'bin\xsim.bat') 'padded_window_member_b_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally {Pop-Location}
Write-Host "XSIM_WORK=$xsimWork"
