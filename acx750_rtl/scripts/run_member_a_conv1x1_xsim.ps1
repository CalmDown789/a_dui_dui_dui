param(
    [Parameter(Mandatory=$true)]
    [string]$DeliveryRoot,
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado',
    [string]$PythonExe = 'C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork=Join-Path $env:TEMP "acx750_member_a_conv1x1_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null
foreach($source in @(
    (Join-Path $taskRoot 'rtl\compute\dsp_signed_mult.v'),
    (Join-Path $taskRoot 'rtl\compute\channel_accumulator.v'),
    (Join-Path $taskRoot 'rtl\compute\conv1x1_backend.v'),
    (Join-Path $taskRoot 'rtl\postprocess\prelu_requantize.sv'),
    (Join-Path $taskRoot 'tb\conv1x1_member_a_tb.sv')
)){Copy-Item -LiteralPath $source -Destination $xsimWork}
& $PythonExe (Join-Path $PSScriptRoot 'generate_1x1_vectors.py') --delivery-root $DeliveryRoot --output-dir $xsimWork
if($LASTEXITCODE-ne 0){throw '1x1 vector generation failed'}
$xvlog=Join-Path $VivadoRoot 'bin\xvlog.bat'; $xelab=Join-Path $VivadoRoot 'bin\xelab.bat'; $xsim=Join-Path $VivadoRoot 'bin\xsim.bat'
Push-Location $xsimWork
try{
    & $xvlog 'dsp_signed_mult.v' 'channel_accumulator.v' 'conv1x1_backend.v' '-sv' 'prelu_requantize.sv' 'conv1x1_member_a_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & $xelab 'conv1x1_member_a_tb' '-s' 'conv1x1_member_a_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & $xsim 'conv1x1_member_a_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
}finally{Pop-Location}
Write-Host "XSIM_WORK=$xsimWork"
