# 成员B工作 / Team member B: eight-phase issue regression.
param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork=Join-Path $env:TEMP "acx750_member_b_eight_phase_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null
foreach($source in @((Join-Path $taskRoot 'rtl\stream\eight_phase_issue.sv'),(Join-Path $taskRoot 'tb\eight_phase_issue_tb.sv'))){Copy-Item -LiteralPath $source -Destination $xsimWork}
Push-Location $xsimWork
try {
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') '-sv' 'eight_phase_issue.sv' 'eight_phase_issue_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & (Join-Path $VivadoRoot 'bin\xelab.bat') 'eight_phase_issue_tb' '-s' 'eight_phase_issue_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & (Join-Path $VivadoRoot 'bin\xsim.bat') 'eight_phase_issue_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
} finally {Pop-Location}
Write-Host "XSIM_WORK=$xsimWork"
