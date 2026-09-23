# 成员B工作 / Team member B: test C's ROM with serialized member A input.
param(
    [string]$CSideRoot='F:\FPGA预选\.artifacts\member_b_c_side_zip_20260923\a_dui_dui_dui-c-side-latest',
    [string]$InputMemDir='F:\FPGA预选\10h冲刺\.artifacts\member_b_c_input_mem',
    [string]$VivadoRoot='F:\Xilinx\2025.2\Vivado'
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$work=Join-Path $env:TEMP ("acx750_member_b_c_input_rom_"+(Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $work | Out-Null
Copy-Item -LiteralPath (Join-Path $CSideRoot 'rtl\c_config.vh') -Destination $work
Copy-Item -LiteralPath (Join-Path $CSideRoot 'rtl\input_rom.v') -Destination $work
Copy-Item -LiteralPath (Join-Path $InputMemDir 'member_a_input_960x540_y_u8.mem') -Destination $work
Copy-Item -LiteralPath (Join-Path $taskRoot 'tb\member_b_c_input_rom_tb.sv') -Destination $work
Push-Location $work
try {
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') '-sv' '-i' $work 'input_rom.v' 'member_b_c_input_rom_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & (Join-Path $VivadoRoot 'bin\xelab.bat') 'member_b_c_input_rom_tb' '-s' 'member_b_c_input_rom_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & (Join-Path $VivadoRoot 'bin\xsim.bat') 'member_b_c_input_rom_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally {Pop-Location}
Write-Host "XSIM_WORK=$work"
