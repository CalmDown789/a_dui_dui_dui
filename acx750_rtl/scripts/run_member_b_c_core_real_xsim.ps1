# 成员B工作 / Team member B: isolated C ZIP + real B core integration regression.
param(
    [string]$CSideRoot='F:\FPGA预选\.artifacts\member_b_c_side_zip_20260923\a_dui_dui_dui-c-side-latest',
    [string]$DeliveryRoot='F:\FPGA预选\10h冲刺\.artifacts\member_a_review_83a9fcd',
    [string]$VivadoRoot='F:\Xilinx\2025.2\Vivado',
    [string]$PythonExe='C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe',
    [string]$ParameterRomDir=''
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$work=Join-Path $env:TEMP ("acx750_member_b_c_core_real_"+(Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $work | Out-Null
& $PythonExe (Join-Path $PSScriptRoot 'generate_small_network_golden.py') --delivery-root $DeliveryRoot --output-dir $work --width 6 --height 5
if($LASTEXITCODE-ne 0){throw 'golden generation failed'}
if($ParameterRomDir){
    $romFiles=Get-ChildItem -LiteralPath $ParameterRomDir -Filter '*_packed.mem' -File
    if($romFiles.Count-ne 19){throw "expected 19 packed ROM files, got $($romFiles.Count)"}
    foreach($rom in $romFiles){
        $generated=@(Get-Content -LiteralPath (Join-Path $work $rom.Name) | Where-Object {$_ -notmatch '^\s*//' -and $_.Trim()})[-1]
        $packaged=@(Get-Content -LiteralPath $rom.FullName | Where-Object {$_ -notmatch '^\s*//' -and $_.Trim()})[-1]
        if($generated-ne $packaged){throw "ROM package mismatch: $($rom.Name)"}
        Copy-Item -LiteralPath $rom.FullName -Destination $work -Force
    }
}
Copy-Item -LiteralPath (Join-Path $CSideRoot 'rtl\c_config.vh') -Destination $work
$cNames=@('b_core_if.v','c_core.v','c_ctrl.v','input_rom.v','input_stream.v','stripe_buffer.v',
    'pingpong_buffer.v','output_stream.v','uart_tx.v','readback_ctrl.v')
foreach($name in $cNames){Copy-Item -LiteralPath (Join-Path $CSideRoot "rtl\$name") -Destination $work}
$ifPath=Join-Path $work 'b_core_if.v'
$ifText=Get-Content -LiteralPath $ifPath -Raw
$old='b_core_real u_b_core ('
$new='b_core_real #(.IMG_W(IMG_W),.IMG_H(IMG_H),.STRIPE_H(STRIPE_H)) u_b_core ('
if(-not $ifText.Contains($old)){throw 'C b_core_if.v changed: parameter patch point not found'}
$ifText=$ifText.Replace($old,$new)
Set-Content -LiteralPath $ifPath -Value $ifText -Encoding utf8
$bNames=@('same_pad_raster.sv','elastic_fifo.sv','window_kminus1_bram.sv','window_stream_frontend.sv',
    'eight_phase_issue.sv','phase_mac_pipeline.sv','phase_accumulator.sv','mac_issue_stage.sv',
    'vector_postprocess_shared.sv','fsrcnn_stream_layer.sv','pixel_shuffle2x_row_banks.sv',
    'fsrcnn_network_core.sv','fsrcnn_network_mem_top.sv','b_core_real.sv')
foreach($name in $bNames){Copy-Item -LiteralPath (Join-Path $taskRoot "rtl\stream\$name") -Destination $work}
Copy-Item -LiteralPath (Join-Path $taskRoot 'rtl\postprocess\prelu_requantize.sv') -Destination $work
Copy-Item -LiteralPath (Join-Path $taskRoot 'tb\member_b_c_core_real_integration_tb.sv') -Destination $work
Push-Location $work
try {
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') '-sv' '-d' 'C_SIM' '-d' 'C_USE_B_REAL' '-i' $work @cNames @bNames 'prelu_requantize.sv' 'member_b_c_core_real_integration_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & (Join-Path $VivadoRoot 'bin\xelab.bat') 'member_b_c_core_real_integration_tb' '-s' 'member_b_c_core_real_integration_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & (Join-Path $VivadoRoot 'bin\xsim.bat') 'member_b_c_core_real_integration_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally {Pop-Location}
Write-Host "XSIM_WORK=$work"
