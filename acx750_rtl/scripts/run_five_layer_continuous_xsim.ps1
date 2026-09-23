# 成员B工作 / Team member B: five concurrently running 6x5 RTL layers.
param(
    [string]$DeliveryRoot='F:\FPGA预选\10h冲刺\.artifacts\member_a_review_83a9fcd',
    [string]$VivadoRoot='F:\Xilinx\2025.2\Vivado',
    [string]$PythonExe='C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe',
    [int]$Width=6,
    [int]$Height=5
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork=Join-Path $env:TEMP "acx750_member_b_five_continuous_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null
& $PythonExe (Join-Path $PSScriptRoot 'generate_small_network_golden.py') --delivery-root $DeliveryRoot --output-dir $xsimWork --width $Width --height $Height
if($LASTEXITCODE-ne 0){throw 'golden generation failed'}
$names=@('same_pad_raster.sv','elastic_fifo.sv','window_kminus1_bram.sv','window_stream_frontend.sv',
    'eight_phase_issue.sv','phase_mac_array.sv','phase_mac_pipeline.sv','phase_accumulator.sv','mac_issue_stage.sv',
    'vector_postprocess_elastic.sv','vector_postprocess_shared.sv','fsrcnn_stream_layer.sv','pixel_shuffle2x_row_banks.sv')
foreach($name in $names){Copy-Item -LiteralPath (Join-Path $taskRoot "rtl\stream\$name") -Destination $xsimWork}
Copy-Item -LiteralPath (Join-Path $taskRoot 'rtl\postprocess\prelu_requantize.sv') -Destination $xsimWork
Copy-Item -LiteralPath (Join-Path $taskRoot 'tb\five_layer_continuous_tb.sv') -Destination $xsimWork
$tbPath=Join-Path $xsimWork 'five_layer_continuous_tb.sv'
$tbText=Get-Content -LiteralPath $tbPath -Raw
$tbText=$tbText.Replace('`define TB_W 6',('`' + 'define TB_W ' + $Width))
$tbText=$tbText.Replace('`define TB_H 5',('`' + 'define TB_H ' + $Height))
Set-Content -LiteralPath $tbPath -Value $tbText -Encoding utf8
Push-Location $xsimWork
try {
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') '-sv' @names 'prelu_requantize.sv' 'five_layer_continuous_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & (Join-Path $VivadoRoot 'bin\xelab.bat') 'five_layer_continuous_tb' '-s' 'five_layer_continuous_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & (Join-Path $VivadoRoot 'bin\xsim.bat') 'five_layer_continuous_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally {Pop-Location}
Write-Host "XSIM_WORK=$xsimWork"
