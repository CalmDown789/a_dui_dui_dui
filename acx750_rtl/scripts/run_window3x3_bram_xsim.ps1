param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$work=Join-Path $env:TEMP "acx750_window3_bram_xsim_$stamp"
New-Item -ItemType Directory -Path $work | Out-Null
Copy-Item -LiteralPath (Join-Path $taskRoot 'rtl\window\window3x3_bram.v') -Destination $work
Copy-Item -LiteralPath (Join-Path $taskRoot 'tb\window3x3_bram_tb.v') -Destination $work
$xvlog=Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab=Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim=Join-Path $VivadoRoot 'bin\xsim.bat'
Push-Location $work
try {
    & $xvlog 'window3x3_bram.v' 'window3x3_bram_tb.v'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & $xelab 'window3x3_bram_tb' '-s' 'window3x3_bram_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & $xsim 'window3x3_bram_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally { Pop-Location }
Write-Host "XSIM_WORK=$work"
