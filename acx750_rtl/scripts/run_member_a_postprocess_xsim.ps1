param(
    [Parameter(Mandatory=$true)]
    [string]$DeliveryRoot,
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado',
    [string]$PythonExe = 'C:\Users\24889\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork = Join-Path $env:TEMP "acx750_member_a_postprocess_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null

Copy-Item -LiteralPath (Join-Path $taskRoot 'rtl\postprocess\prelu_requantize.sv') -Destination $xsimWork
Copy-Item -LiteralPath (Join-Path $taskRoot 'tb\prelu_requantize_member_a_tb.sv') -Destination $xsimWork

& $PythonExe (Join-Path $PSScriptRoot 'generate_postprocess_vectors.py') `
    --delivery-root $DeliveryRoot --output-dir $xsimWork
if ($LASTEXITCODE -ne 0) { throw 'vector generation failed' }

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

Push-Location $xsimWork
try {
    & $xvlog '-sv' 'prelu_requantize.sv' 'prelu_requantize_member_a_tb.sv'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & $xelab 'prelu_requantize_member_a_tb' '-s' 'prelu_requantize_member_a_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & $xsim 'prelu_requantize_member_a_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
} finally {
    Pop-Location
}

Write-Host "XSIM_WORK=$xsimWork"
