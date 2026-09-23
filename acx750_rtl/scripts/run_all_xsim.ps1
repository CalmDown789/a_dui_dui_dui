param([string]$VivadoRoot='F:\Xilinx\2025.2\Vivado')

$ErrorActionPreference='Stop'
$regressions=@(
    'run_backend_xsim.ps1',
    'run_backend_random_xsim.ps1',
    'run_accumulator_saturation_xsim.ps1',
    'run_conv1x1_xsim.ps1',
    'run_window3x3_bram_xsim.ps1',
    'run_window5x5_bram_xsim.ps1',
    'run_dot25_xsim.ps1',
    'run_conv5x5_xsim.ps1',
    'run_conv5x5_u8s8_xsim.ps1',
    'run_prelu_requantize_xsim.ps1',
    'run_parameter_rom_xsim.ps1',
    'run_pixel_shuffle_map_xsim.ps1',
    'run_stream_control_xsim.ps1',
    'run_padded_window_member_b_xsim.ps1',
    'run_eight_phase_issue_xsim.ps1',
    'run_window_stream_frontend_xsim.ps1',
    'run_mac_lane_map_xsim.ps1',
    'run_phase_accumulator_xsim.ps1',
    'run_phase_mac_array_xsim.ps1'
)

foreach($regression in $regressions){
    Write-Host "RUNNING=$regression"
    & (Join-Path $PSScriptRoot $regression) -VivadoRoot $VivadoRoot
    if($LASTEXITCODE-ne 0){throw "Regression failed: $regression"}
}

Write-Host 'ACX750_ALL_XSIM_REGRESSIONS_PASS'
