param(
    [string]$VivadoRoot = 'F:\Xilinx\2025.2\Vivado',
    [string]$PythonExe = ''
)

$ErrorActionPreference = 'Stop'

$taskRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$xsimWork = Join-Path $env:TEMP "acx750_backend_random_xsim_$stamp"
New-Item -ItemType Directory -Path $xsimWork | Out-Null

$generator = Join-Path $PSScriptRoot 'generate_backend_vectors.py'
$stimulus = Join-Path $xsimWork 'backend_stimulus.txt'
$expected = Join-Path $xsimWork 'backend_expected.txt'

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $pythonCommand = Get-Command 'python' -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        $PythonExe = $pythonCommand.Source
    } else {
        $bundledPython = Join-Path $env:USERPROFILE `
            '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $bundledPython) {
            $PythonExe = $bundledPython
        } else {
            throw 'Python not found. Pass -PythonExe with an explicit python.exe path.'
        }
    }
}

& $PythonExe $generator '--stimulus' $stimulus '--expected' $expected `
    '--groups' '96' '--channels' '3' '--seed' '750200'
if ($LASTEXITCODE -ne 0) { throw 'vector generation failed' }

$sources = @(
    (Join-Path $taskRoot 'rtl\compute\dot9_pipeline.v'),
    (Join-Path $taskRoot 'rtl\compute\channel_accumulator.v'),
    (Join-Path $taskRoot 'rtl\compute\conv3x3_backend.v'),
    (Join-Path $taskRoot 'tb\conv3x3_backend_random_tb.sv')
)

foreach ($source in $sources) {
    Copy-Item -LiteralPath $source -Destination $xsimWork
}

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

foreach ($tool in @($xvlog, $xelab, $xsim)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "Vivado simulator tool not found: $tool"
    }
}

Push-Location $xsimWork
try {
    & $xvlog 'dot9_pipeline.v' 'channel_accumulator.v' `
        'conv3x3_backend.v' '-sv' 'conv3x3_backend_random_tb.sv'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }

    & $xelab 'conv3x3_backend_random_tb' '-s' 'conv3x3_backend_random_tb_sim'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }

    & $xsim 'conv3x3_backend_random_tb_sim' '-runall'
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
} finally {
    Pop-Location
}

Write-Host "XSIM_WORK=$xsimWork"
