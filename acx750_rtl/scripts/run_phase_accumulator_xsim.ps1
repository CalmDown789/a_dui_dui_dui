# 成员B工作 / Team member B: five-layer eight-phase accumulation regression.
param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork=Join-Path $env:TEMP "acx750_member_b_phase_acc_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null
foreach($source in @((Join-Path $taskRoot 'rtl\stream\phase_accumulator.sv'),(Join-Path $taskRoot 'tb\phase_accumulator_tb.sv'))){Copy-Item -LiteralPath $source -Destination $xsimWork}
Push-Location $xsimWork
try {
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') '-sv' 'phase_accumulator.sv' 'phase_accumulator_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & (Join-Path $VivadoRoot 'bin\xelab.bat') 'phase_accumulator_tb' '-s' 'phase_accumulator_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & (Join-Path $VivadoRoot 'bin\xsim.bat') 'phase_accumulator_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally {Pop-Location}
Write-Host "XSIM_WORK=$xsimWork"
