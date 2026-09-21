param(
    [string]$PythonExe = 'C:\Users\24889\miniforge3\envs\srtp-fsrcnn\python.exe'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$summaryScript = Join-Path $PSScriptRoot 'summarize_hls_reports.py'
$resultRoot = Join-Path $repoRoot 'results'
$outputPath = Join-Path $resultRoot 'HLS_SUMMARY.md'

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python interpreter not found: $PythonExe"
}

& $PythonExe $summaryScript --results $resultRoot --output $outputPath
if ($LASTEXITCODE -ne 0) {
    throw "HLS summary failed with exit code $LASTEXITCODE"
}
