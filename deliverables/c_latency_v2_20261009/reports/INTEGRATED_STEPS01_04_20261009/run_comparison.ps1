$ErrorActionPreference='Stop'
$comparisonLogs='C:\t6int09\comparison_launcher'
New-Item -ItemType Directory -Path $comparisonLogs | Out-Null
$comparisonOwned=$null
$comparisonExit=1
try {
    if (!(Get-NetTCPConnection -State Listen -LocalPort 3121 -ErrorAction SilentlyContinue)) {
        $comparisonOwned=Start-Process -FilePath 'E:\AMDTools2025\2025.2\Vivado\bin\unwrapped\win64.o\hw_server.exe' -WindowStyle Hidden -RedirectStandardOutput "$comparisonLogs\stdout.log" -RedirectStandardError "$comparisonLogs\stderr.log" -PassThru
        $comparisonTicks=$comparisonOwned.StartTime.Ticks
        $comparisonPath=$comparisonOwned.Path
        for ($comparisonPoll=0; $comparisonPoll -lt 30; $comparisonPoll++) {
            if (Get-NetTCPConnection -State Listen -LocalPort 3121 -ErrorAction SilentlyContinue) { break }
            Start-Sleep -Milliseconds 200
        }
        if (!(Get-NetTCPConnection -State Listen -LocalPort 3121 -ErrorAction SilentlyContinue)) { throw 'Comparison hardware server not ready' }
    }
    & 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe' -B (Join-Path $PSScriptRoot 'run_comparison.py')
    $comparisonExit=$LASTEXITCODE
} finally {
    $comparisonStopped=$false
    if ($null -ne $comparisonOwned) {
        $comparisonCurrent=Get-Process -Id $comparisonOwned.Id -ErrorAction SilentlyContinue
        if ($null -ne $comparisonCurrent -and $comparisonCurrent.Path -eq $comparisonPath -and $comparisonCurrent.StartTime.Ticks -eq $comparisonTicks) {
            Stop-Process -Id $comparisonCurrent.Id
            $comparisonStopped=$true
        }
    }
    @{child_exit_code=$comparisonExit; stopped_owned_server=$comparisonStopped} | ConvertTo-Json | Set-Content -LiteralPath "$comparisonLogs\RESULT.json" -Encoding utf8
}
exit $comparisonExit
