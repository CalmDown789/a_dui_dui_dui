param(
    [Parameter(Mandatory=$true)]
    [string]$DeliveryRoot,
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado',
    [string]$PythonExe = 'C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork = Join-Path $env:TEMP "acx750_member_a_feature_subpixel_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null

$sources = @(
    (Join-Path $taskRoot 'rtl\compute\dsp_u8s8_mult.v'),
    (Join-Path $taskRoot 'rtl\compute\dsp_signed_mult.v'),
    (Join-Path $taskRoot 'rtl\compute\dot25_u8s8_pipeline.v'),
    (Join-Path $taskRoot 'rtl\compute\dot25_pipeline.v'),
    (Join-Path $taskRoot 'rtl\compute\channel_accumulator.v'),
    (Join-Path $taskRoot 'rtl\compute\conv5x5_u8s8_backend.v'),
    (Join-Path $taskRoot 'rtl\compute\conv5x5_backend.v'),
    (Join-Path $taskRoot 'rtl\postprocess\prelu_requantize.sv'),
    (Join-Path $taskRoot 'tb\feature_subpixel_member_a_tb.sv')
)
foreach ($source in $sources) {
    Copy-Item -LiteralPath $source -Destination $xsimWork
}

& $PythonExe (Join-Path $PSScriptRoot 'generate_feature_subpixel_vectors.py') `
    --delivery-root $DeliveryRoot --output-dir $xsimWork
if ($LASTEXITCODE -ne 0) { throw 'feature/subpixel vector generation failed' }

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

Push-Location $xsimWork
try {
    & $xvlog 'dsp_u8s8_mult.v' 'dsp_signed_mult.v' 'dot25_u8s8_pipeline.v' `
        'dot25_pipeline.v' 'channel_accumulator.v' 'conv5x5_u8s8_backend.v' `
        'conv5x5_backend.v' '-sv' 'prelu_requantize.sv' 'feature_subpixel_member_a_tb.sv'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & $xelab 'feature_subpixel_member_a_tb' '-s' 'feature_subpixel_member_a_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & $xsim 'feature_subpixel_member_a_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
} finally {
    Pop-Location
}

Write-Host "XSIM_WORK=$xsimWork"
