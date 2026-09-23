# 成员B工作 / Team member B: full-frame RTL comparison against A-confirmed integer Golden.
param(
    [string]$ADeliveryRoot='F:\FPGA预选\10h冲刺\.artifacts\member_a_full_integer_zip_20260923\a_dui_dui_dui-member-a',
    [string]$VivadoRoot='F:\Xilinx\2025.2\Vivado',
    [string]$PythonExe='C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$work=Join-Path $env:TEMP ('acx750_member_b_a_full_integer_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $work | Out-Null
& $PythonExe (Join-Path $PSScriptRoot 'stage_member_b_a_full_integer.py') `
    --a-delivery-root $ADeliveryRoot --rom-dir (Join-Path $taskRoot 'rom\member_a_d16_s8_m1_c16') --output-dir $work
if($LASTEXITCODE-ne 0){throw 'A full integer vector staging failed'}
$names=@('same_pad_raster.sv','elastic_fifo.sv','window_kminus1_bram.sv','window_stream_frontend.sv',
    'eight_phase_issue.sv','phase_mac_array.sv','phase_mac_pipeline.sv','phase_accumulator.sv','mac_issue_stage.sv',
    'vector_postprocess_elastic.sv','vector_postprocess_shared.sv','fsrcnn_stream_layer.sv','pixel_shuffle2x_row_banks.sv',
    'fsrcnn_network_core.sv','fsrcnn_network_mem_top.sv')
foreach($name in $names){Copy-Item -LiteralPath (Join-Path $taskRoot "rtl\stream\$name") -Destination $work}
Copy-Item -LiteralPath (Join-Path $taskRoot 'rtl\postprocess\prelu_requantize.sv') -Destination $work
Copy-Item -LiteralPath (Join-Path $taskRoot 'tb\fsrcnn_network_mem_top_tb.sv') -Destination $work
$tbPath=Join-Path $work 'fsrcnn_network_mem_top_tb.sv'
$tbText=Get-Content -LiteralPath $tbPath -Raw
$tbText=$tbText.Replace('`define TB_W 6','`define TB_W 960').Replace('`define TB_H 5','`define TB_H 540')
Set-Content -LiteralPath $tbPath -Value $tbText -Encoding utf8
Push-Location $work
try {
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') '-sv' '-d' 'TB_ALWAYS_READY' '-d' 'TB_FULL_FRAME' @names 'prelu_requantize.sv' 'fsrcnn_network_mem_top_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & (Join-Path $VivadoRoot 'bin\xelab.bat') 'fsrcnn_network_mem_top_tb' '-s' 'fsrcnn_network_mem_top_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & (Join-Path $VivadoRoot 'bin\xsim.bat') 'fsrcnn_network_mem_top_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally {Pop-Location}
Write-Host "XSIM_WORK=$work"
