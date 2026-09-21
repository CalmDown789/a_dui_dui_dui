$ErrorActionPreference = 'Stop'

$checks = @(
    'run_python_reference.ps1',
    'run_python_network.ps1',
    'run_driver_layout.ps1',
    'run_hls_summary.ps1'
)

foreach ($check in $checks) {
    $path = Join-Path $PSScriptRoot $check
    Write-Host "==> $check"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $path
    if ($LASTEXITCODE -ne 0) {
        throw "$check failed with exit code $LASTEXITCODE"
    }
}

Write-Host "QUICK_REGRESSION_PASS checks=$($checks.Count)"
