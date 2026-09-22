param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')
$ErrorActionPreference='Stop';$taskRoot=Split-Path -Parent $PSScriptRoot
$work=Join-Path $env:TEMP "acx750_window5_bram_xsim_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $work|Out-Null
Copy-Item -LiteralPath (Join-Path $taskRoot 'rtl\window\window5x5_bram.v') -Destination $work
Copy-Item -LiteralPath (Join-Path $taskRoot 'tb\window5x5_bram_tb.sv') -Destination $work
$xvlog=Join-Path $VivadoRoot 'bin\xvlog.bat';$xelab=Join-Path $VivadoRoot 'bin\xelab.bat';$xsim=Join-Path $VivadoRoot 'bin\xsim.bat'
Push-Location $work
try{
 & $xvlog 'window5x5_bram.v' '-sv' 'window5x5_bram_tb.sv';if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
 & $xelab 'window5x5_bram_tb' '-s' 'window5x5_bram_tb_sim';if($LASTEXITCODE-ne 0){throw 'xelab failed'}
 & $xsim 'window5x5_bram_tb_sim' '-runall';if($LASTEXITCODE-ne 0){throw 'xsim failed'}
}finally{Pop-Location}
Write-Host "XSIM_WORK=$work"
