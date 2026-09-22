param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')

$ErrorActionPreference='Stop'
$regressions=@(
    'run_backend_xsim.ps1',
    'run_backend_random_xsim.ps1',
    'run_conv1x1_xsim.ps1',
    'run_window3x3_bram_xsim.ps1',
    'run_window5x5_bram_xsim.ps1',
    'run_dot25_xsim.ps1',
    'run_conv5x5_xsim.ps1'
)

foreach($regression in $regressions){
    Write-Host "RUNNING=$regression"
    & (Join-Path $PSScriptRoot $regression) -VivadoRoot $VivadoRoot
    if($LASTEXITCODE-ne 0){throw "Regression failed: $regression"}
}

Write-Host 'ACX750_ALL_XSIM_REGRESSIONS_PASS'
