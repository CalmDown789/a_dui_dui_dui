# 成员B工作 / Team member B: five independent 6x5 quantized layer streams.
param(
    [string]$DeliveryRoot='F:\FPGA预选\10h冲刺\.artifacts\member_a_review_83a9fcd',
    [string]$VivadoRoot='F:\Xilinx\2025.2\Vivado',
    [string]$PythonExe='C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork=Join-Path $env:TEMP "acx750_member_b_five_quant_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null
& $PythonExe (Join-Path $PSScriptRoot 'generate_small_network_golden.py') --delivery-root $DeliveryRoot --output-dir $xsimWork --width 6 --height 5
if($LASTEXITCODE-ne 0){throw 'golden generation failed'}
$sources=@(
    (Join-Path $taskRoot 'rtl\stream\same_pad_raster.sv'),
    (Join-Path $taskRoot 'rtl\stream\elastic_fifo.sv'),
    (Join-Path $taskRoot 'rtl\stream\window_kminus1_bram.sv'),
    (Join-Path $taskRoot 'rtl\stream\window_stream_frontend.sv'),
    (Join-Path $taskRoot 'rtl\stream\eight_phase_issue.sv'),
    (Join-Path $taskRoot 'rtl\stream\phase_mac_array.sv'),
    (Join-Path $taskRoot 'rtl\stream\phase_mac_pipeline.sv'),
    (Join-Path $taskRoot 'rtl\stream\phase_accumulator.sv'),
    (Join-Path $taskRoot 'rtl\stream\mac_issue_stage.sv'),
    (Join-Path $taskRoot 'rtl\postprocess\prelu_requantize.sv'),
    (Join-Path $taskRoot 'rtl\stream\vector_postprocess_elastic.sv'),
    (Join-Path $taskRoot 'tb\five_layer_quant_stream_tb.sv')
)
foreach($source in $sources){Copy-Item -LiteralPath $source -Destination $xsimWork}
Push-Location $xsimWork
try {
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') '-sv' 'same_pad_raster.sv' 'elastic_fifo.sv' 'window_kminus1_bram.sv' 'window_stream_frontend.sv' 'eight_phase_issue.sv' 'phase_mac_array.sv' 'phase_mac_pipeline.sv' 'phase_accumulator.sv' 'mac_issue_stage.sv' 'prelu_requantize.sv' 'vector_postprocess_elastic.sv' 'five_layer_quant_stream_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & (Join-Path $VivadoRoot 'bin\xelab.bat') 'five_layer_quant_stream_tb' '-s' 'five_layer_quant_stream_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & (Join-Path $VivadoRoot 'bin\xsim.bat') 'five_layer_quant_stream_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally {Pop-Location}
Write-Host "XSIM_WORK=$xsimWork"
