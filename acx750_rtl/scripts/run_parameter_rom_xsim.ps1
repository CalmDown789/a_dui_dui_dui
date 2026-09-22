param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork=Join-Path $env:TEMP "acx750_parameter_rom_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null
foreach($source in @(
    (Join-Path $taskRoot 'rtl\memory\sync_parameter_rom.sv'),
    (Join-Path $taskRoot 'tb\sync_parameter_rom_tb.sv'),
    (Join-Path $taskRoot 'tb\parameter_rom_test.mem')
)){Copy-Item -LiteralPath $source -Destination $xsimWork}
$xvlog=Join-Path $VivadoRoot 'bin\xvlog.bat';$xelab=Join-Path $VivadoRoot 'bin\xelab.bat';$xsim=Join-Path $VivadoRoot 'bin\xsim.bat'
Push-Location $xsimWork
try{
    & $xvlog '-sv' 'sync_parameter_rom.sv' 'sync_parameter_rom_tb.sv'
    if($LASTEXITCODE-ne 0){throw 'xvlog failed'}
    & $xelab 'sync_parameter_rom_tb' '-s' 'sync_parameter_rom_tb_sim'
    if($LASTEXITCODE-ne 0){throw 'xelab failed'}
    & $xsim 'sync_parameter_rom_tb_sim' '-runall'
    if($LASTEXITCODE-ne 0){throw 'xsim failed'}
}finally{Pop-Location}
Write-Host "XSIM_WORK=$xsimWork"
