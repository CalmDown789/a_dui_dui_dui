[CmdletBinding()]
param(
    [ValidateSet('Preflight','Run')][string]$Mode='Run',
    [string]$Python='C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe',
    [string]$Vivado='E:\AMDTools2025\2025.2\Vivado\bin\vivado.bat',
    [string]$HardwareServer='E:\AMDTools2025\2025.2\Vivado\bin\unwrapped\win64.o\hw_server.exe'
)
$ErrorActionPreference='Stop'
$taskOwnedServer=$null
$taskExit=1
$taskPackage=[IO.Path]::GetFullPath($PSScriptRoot)
$taskLogs=Join-Path $taskPackage ('attempts\launcher_'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
try {
    if ($Mode -eq 'Run') {
        $taskListener=@(Get-NetTCPConnection -State Listen -LocalPort 3121 -ErrorAction SilentlyContinue)
        if (!$taskListener.Count) {
            $taskOwnedServer=Start-Process -FilePath $HardwareServer -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskLogs 'hw_server_stdout.log') -RedirectStandardError (Join-Path $taskLogs 'hw_server_stderr.log') -PassThru
            $taskServerStartTicks=$taskOwnedServer.StartTime.Ticks
            $taskServerPath=$taskOwnedServer.Path
            @{pid=$taskOwnedServer.Id; start_ticks=$taskServerStartTicks; executable=$taskServerPath} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskLogs 'owned_server.json') -Encoding utf8
            for ($taskPoll=0; $taskPoll -lt 30; $taskPoll++) {
                if (Get-NetTCPConnection -State Listen -LocalPort 3121 -ErrorAction SilentlyContinue) { break }
                if ($taskOwnedServer.HasExited) { throw 'Owned hardware server exited; inspect launcher logs.' }
                Start-Sleep -Milliseconds 200
            }
            if (!(Get-NetTCPConnection -State Listen -LocalPort 3121 -ErrorAction SilentlyContinue)) { throw 'Hardware server did not listen on port 3121.' }
        }
    }
    $taskShell=(Get-Process -Id $PID).Path
    & $taskShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $taskPackage 'lab\run_c_streaming.ps1') -Mode $Mode -Python $Python -Vivado $Vivado -OutputWindow 128
    $taskExit=$LASTEXITCODE
} finally {
    $taskStopped=$false
    if ($null -ne $taskOwnedServer) {
        $taskCurrent=Get-Process -Id $taskOwnedServer.Id -ErrorAction SilentlyContinue
        if ($null -ne $taskCurrent -and $taskCurrent.Path -eq $taskServerPath -and $taskCurrent.StartTime.Ticks -eq $taskServerStartTicks) {
            Stop-Process -Id $taskCurrent.Id
            $taskStopped=$true
        }
    }
    @{mode=$Mode; child_exit_code=$taskExit; stopped_owned_server=$taskStopped; reused_server_left_running=($null -eq $taskOwnedServer)} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskLogs 'LAUNCHER_RESULT.json') -Encoding utf8
}
exit $taskExit
