param(
    [Parameter(Mandatory=$true)]
    [string]$DeliveryRoot,
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado',
    [string]$PythonExe = 'C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork = Join-Path $env:TEMP "acx750_member_a_mapping0_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null

$sources = @(
    (Join-Path $taskRoot 'rtl\compute\dot9_pipeline.v'),
    (Join-Path $taskRoot 'rtl\compute\channel_accumulator.v'),
    (Join-Path $taskRoot 'rtl\compute\conv3x3_backend.v'),
    (Join-Path $taskRoot 'rtl\postprocess\prelu_requantize.sv'),
    (Join-Path $taskRoot 'tb\mapping0_member_a_integration_tb.sv')
)
foreach ($source in $sources) {
    Copy-Item -LiteralPath $source -Destination $xsimWork
}

& $PythonExe (Join-Path $PSScriptRoot 'generate_mapping0_vectors.py') `
    --delivery-root $DeliveryRoot --output-dir $xsimWork
if ($LASTEXITCODE -ne 0) { throw 'mapping0 vector generation failed' }

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

Push-Location $xsimWork
try {
    & $xvlog 'dot9_pipeline.v' 'channel_accumulator.v' 'conv3x3_backend.v' `
        '-sv' 'prelu_requantize.sv' 'mapping0_member_a_integration_tb.sv'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & $xelab 'mapping0_member_a_integration_tb' '-s' 'mapping0_member_a_integration_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & $xsim 'mapping0_member_a_integration_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
} finally {
    Pop-Location
}

Write-Host "XSIM_WORK=$xsimWork"
