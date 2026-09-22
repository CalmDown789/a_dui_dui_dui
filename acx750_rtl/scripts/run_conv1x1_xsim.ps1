param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')
$ErrorActionPreference='Stop';$taskRoot=Split-Path -Parent $PSScriptRoot
$work=Join-Path $env:TEMP "acx750_conv1_xsim_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $work|Out-Null
$files=@('rtl\compute\dsp_signed_mult.v','rtl\compute\channel_accumulator.v','rtl\compute\conv1x1_backend.v','tb\conv1x1_backend_tb.v')
foreach($file in $files){Copy-Item -LiteralPath (Join-Path $taskRoot $file)-Destination $work}
$xvlog=Join-Path $VivadoRoot 'bin\xvlog.bat';$xelab=Join-Path $VivadoRoot 'bin\xelab.bat';$xsim=Join-Path $VivadoRoot 'bin\xsim.bat'
Push-Location $work
try{
 & $xvlog 'dsp_signed_mult.v' 'channel_accumulator.v' 'conv1x1_backend.v' 'conv1x1_backend_tb.v';if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
 & $xelab 'conv1x1_backend_tb' '-s' 'conv1x1_backend_tb_sim';if($LASTEXITCODE-ne 0){throw 'xelab failed'}
 & $xsim 'conv1x1_backend_tb_sim' '-runall';if($LASTEXITCODE-ne 0){throw 'xsim failed'}
}finally{Pop-Location}
Write-Host "XSIM_WORK=$work"
