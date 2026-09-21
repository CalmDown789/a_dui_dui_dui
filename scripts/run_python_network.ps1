param(
    [string]$PythonExe = 'C:\Users\24889\miniforge3\envs\srtp-fsrcnn\python.exe'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$testScript = Join-Path $repoRoot 'python\test_network_reference.py'

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python interpreter not found: $PythonExe"
}

& $PythonExe $testScript
if ($LASTEXITCODE -ne 0) {
    throw "Python network tests failed with exit code $LASTEXITCODE"
}
