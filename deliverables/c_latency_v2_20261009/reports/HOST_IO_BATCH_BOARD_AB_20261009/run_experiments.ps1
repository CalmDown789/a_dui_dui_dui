$ErrorActionPreference='Stop'
$batchLogs=Join-Path $PSScriptRoot 'launcher'
New-Item -ItemType Directory -Path $batchLogs | Out-Null
$batchOwned=$null
$batchExit=1
try {
    $batchAdapter=Get-NetAdapter -Name '以太网 3'
    if ($batchAdapter.Status -ne 'Up' -or $batchAdapter.LinkSpeed -notmatch '^1\s*Gbps$') { throw 'Selected adapter is not Up at 1 Gbps' }
    if (Get-NetUDPEndpoint -LocalPort 6102 -ErrorAction SilentlyContinue) { throw 'UDP6102 occupied' }
    $batchAdapter | Select-Object Name,Status,LinkSpeed,MacAddress,DriverVersion | ConvertTo-Json | Set-Content -LiteralPath "$batchLogs\NETWORK_BEFORE.json" -Encoding utf8
    if (!(Get-NetTCPConnection -State Listen -LocalPort 3121 -ErrorAction SilentlyContinue)) {
        $batchOwned=Start-Process -FilePath 'E:\AMDTools2025\2025.2\Vivado\bin\unwrapped\win64.o\hw_server.exe' -WindowStyle Hidden -RedirectStandardOutput "$batchLogs\stdout.log" -RedirectStandardError "$batchLogs\stderr.log" -PassThru
        $batchTicks=$batchOwned.StartTime.Ticks
        $batchPath=$batchOwned.Path
        for ($batchPoll=0; $batchPoll -lt 30; $batchPoll++) {
            if (Get-NetTCPConnection -State Listen -LocalPort 3121 -ErrorAction SilentlyContinue) { break }
            Start-Sleep -Milliseconds 200
        }
        if (!(Get-NetTCPConnection -State Listen -LocalPort 3121 -ErrorAction SilentlyContinue)) { throw 'Hardware server not ready' }
    }
    & 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe' -B (Join-Path $PSScriptRoot 'run_experiments.py')
    $batchExit=$LASTEXITCODE
} finally {
    $batchStopped=$false
    if ($null -ne $batchOwned) {
        $batchCurrent=Get-Process -Id $batchOwned.Id -ErrorAction SilentlyContinue
        if ($null -ne $batchCurrent -and $batchCurrent.Path -eq $batchPath -and $batchCurrent.StartTime.Ticks -eq $batchTicks) {
            Stop-Process -Id $batchCurrent.Id
            $batchStopped=$true
        }
    }
    @{child_exit_code=$batchExit; stopped_owned_server=$batchStopped} | ConvertTo-Json | Set-Content -LiteralPath "$batchLogs\RESULT.json" -Encoding utf8
}
exit $batchExit
