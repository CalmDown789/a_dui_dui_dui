param(
    [string]$PythonExe = 'C:\Users\24889\miniforge3\envs\srtp-fsrcnn\python.exe'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$testScript = Join-Path $repoRoot 'driver\test_data_layout.py'

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python interpreter not found: $PythonExe"
}

& $PythonExe $testScript
if ($LASTEXITCODE -ne 0) {
    throw "Driver layout test failed with exit code $LASTEXITCODE"
}
