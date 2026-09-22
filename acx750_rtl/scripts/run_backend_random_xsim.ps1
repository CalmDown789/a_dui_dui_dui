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

$sources = @(
    (Join-Path $taskRoot 'rtl\compute\dot9_pipeline.v'),
    (Join-Path $taskRoot 'rtl\compute\channel_accumulator.v'),
    (Join-Path $taskRoot 'rtl\compute\conv3x3_backend.v'),
    (Join-Path $taskRoot 'tb\conv3x3_backend_random_tb.sv')
)

$xvlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
$xelab = Join-Path $VivadoRoot 'bin\xelab.bat'
$xsim = Join-Path $VivadoRoot 'bin\xsim.bat'

foreach ($tool in @($xvlog, $xelab, $xsim)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "Vivado simulator tool not found: $tool"
    }
}

$cases = @(
    @{ Name = 'channels1'; Channels = 1; Groups = 64; Seed = 750201 },
    @{ Name = 'channels3'; Channels = 3; Groups = 96; Seed = 750200 }
)

foreach ($case in $cases) {
    $caseWork = Join-Path $xsimWork $case.Name
    New-Item -ItemType Directory -Path $caseWork | Out-Null
    $stimulus = Join-Path $caseWork 'backend_stimulus.txt'
    $expected = Join-Path $caseWork 'backend_expected.txt'

    & $PythonExe $generator '--stimulus' $stimulus '--expected' $expected `
        '--groups' ([string]$case.Groups) '--channels' ([string]$case.Channels) `
        '--seed' ([string]$case.Seed)
    if ($LASTEXITCODE -ne 0) { throw "vector generation failed: $($case.Name)" }

    foreach ($source in $sources) {
        Copy-Item -LiteralPath $source -Destination $caseWork
    }

    Push-Location $caseWork
    try {
        $xvlogArguments = @(
            'dot9_pipeline.v',
            'channel_accumulator.v',
            'conv3x3_backend.v',
            '-sv'
        )
        if ($case.Channels -eq 1) {
            $xvlogArguments += @('-d', 'TB_CHANNELS_ONE')
        }
        $xvlogArguments += 'conv3x3_backend_random_tb.sv'

        & $xvlog @xvlogArguments
        if ($LASTEXITCODE -ne 0) { throw "xvlog failed: $($case.Name)" }

        & $xelab 'conv3x3_backend_random_tb' '-s' 'conv3x3_backend_random_tb_sim'
        if ($LASTEXITCODE -ne 0) { throw "xelab failed: $($case.Name)" }

        & $xsim 'conv3x3_backend_random_tb_sim' '-runall'
        if ($LASTEXITCODE -ne 0) { throw "xsim failed: $($case.Name)" }
    } finally {
        Pop-Location
    }
}

Write-Host "XSIM_WORK=$xsimWork"
