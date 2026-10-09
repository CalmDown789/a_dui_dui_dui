Set-StrictMode -Version Latest
function ConvertTo-DiagnosticNativeArgument([string]$Value) {
    if ($Value.IndexOf([char]0) -ge 0) { throw 'NUL is invalid in a native argument.' }
    return '"'+[regex]::Replace([regex]::Replace($Value,'(\\*)"','$1$1\"'),'(\\+)$','$1$1')+'"'
}
function Invoke-DiagnosticPython {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Python,
        [Parameter(Mandatory=$true)][string]$Script,
        [string[]]$ScriptArgs=@(),
        [Parameter(Mandatory=$true)][string]$Log,
        [ValidateRange(0.2,120)][double]$FirstPacketDeadlineSeconds=120,
        [ValidateRange(0.1,120)][double]$StackIntervalSeconds=30,
        [ValidateRange(0,5000)][int]$OwnedDescendantDrainMilliseconds=1500
    )
    $diagPrefix=$Log+'.diag'; $stderr=$Log+'.stderr.log'; $monitor=$diagPrefix+'.monitor.jsonl'
    $statusFile=$diagPrefix+'.status.json'; $marker=$diagPrefix+'.first_packet.json'; $workerMarker=$diagPrefix+'.worker.json'; $workerAuthMarker=$diagPrefix+'.worker.auth.json'; $workerAuthPending=$workerAuthMarker+'.pending'
    foreach ($file in @($Log,$stderr,$monitor,$statusFile,$marker,$workerMarker,$workerAuthMarker,$workerAuthPending,$diagPrefix+'.stacks.log')) {
        if (Test-Path -LiteralPath $file) { throw 'Diagnostic files exist; use a fresh attempt.' }
    }
    if (!('PldDiagnosticV2.OwnedJob' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'owned_job.cs') }
    $utf8=[Text.UTF8Encoding]::new($false)
    $token=[Guid]::NewGuid().ToString('N')+[Guid]::NewGuid().ToString('N')
    $diagState=@{scope='OWNED_LAB_PYTHON_JOB_SUPERVISOR_V2';status='STARTING';
        child_pid=$null;child_start_UTC=$null;child_running_at_return=$false;
        worker_pid=$null;worker_start_UTC=$null;worker_running_at_return=$false;
        worker_identity_verified_after_exit=$false;worker_authentication_completed=$false;
        worker_authentication_before_target=$false;launcher_exited_with_owned_processes=$false;
        owned_descendants_drain_ms=$OwnedDescendantDrainMilliseconds;owned_descendants_drained_after_exit=$false;
        owned_processes_after_launcher_exit=@();
        first_packet_marker_unverified_at_exit=$false;
        owned_processes_running_at_return=$true;owned_active_pids_at_return=@();
        first_packet_confirmed=$false;deadline_seconds=$FirstPacketDeadlineSeconds;
        cpu_io_scope='WORKER_PROCESS_ACCOUNTING_INCLUDES_FILES_NETWORK_DIAGNOSTICS_NOT_DISK_ONLY';
        board_receive_or_reply_proven=$false;physical_IO_signoff=$false;complete_stage_acceptance=$false}
    [IO.File]::WriteAllText($statusFile,($diagState|ConvertTo-Json -Depth 6),$utf8)
    $nativeArgs=@($Python,'-B','-u','-X','faulthandler',(Join-Path $PSScriptRoot 'lab_bootstrap.py'),
        '--diag-prefix',$diagPrefix,'--stack-interval',$StackIntervalSeconds.ToString([Globalization.CultureInfo]::InvariantCulture),
        '--target',$Script,'--')+$ScriptArgs
    $nativeLine=($nativeArgs|ForEach-Object { ConvertTo-DiagnosticNativeArgument $_ }) -join ' '
    $clock=[Diagnostics.Stopwatch]::StartNew()
    $child=$null;$worker=$null;$job=$null;$diagExit=1;$timedOut=$false
    $workerRecordVerified=$false;$workerIdentityVerifiedAfterExit=$false
    $expectedWorkerExecutable=[IO.Path]::GetFullPath($Python)
    $expectedWorkerPrefix=[IO.Path]::GetFullPath((Split-Path -Parent $expectedWorkerExecutable))
    $expectedImagePaths=@($expectedWorkerExecutable)
    if ((Split-Path -Leaf (Split-Path -Parent $expectedWorkerExecutable)) -ieq 'Scripts') {
        $venvRoot=[IO.Path]::GetFullPath((Split-Path -Parent (Split-Path -Parent $expectedWorkerExecutable)))
        $expectedWorkerPrefix=$venvRoot
        $pyvenv=Join-Path $venvRoot 'pyvenv.cfg'
        if (!(Test-Path -LiteralPath $pyvenv -PathType Leaf)) { throw 'The selected venv has no pyvenv.cfg; interpreter origin cannot be authenticated.' }
        $homeLine=Get-Content -LiteralPath $pyvenv -Encoding UTF8 | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
        if (!$homeLine) { throw 'The selected venv pyvenv.cfg has no Python home; interpreter origin cannot be authenticated.' }
        $baseHome=($homeLine -replace '^\s*home\s*=\s*','').Trim()
        $expectedImagePaths+= [IO.Path]::GetFullPath((Join-Path $baseHome 'python.exe'))
    }
    $priorEncoding=$env:PYTHONIOENCODING;$priorToken=$env:PLD_DIAGNOSTIC_OWNER_TOKEN
    $writer=[IO.StreamWriter]::new($monitor,$false,$utf8);$writer.AutoFlush=$true
    try {
        $env:PYTHONIOENCODING='utf-8';$env:PLD_DIAGNOSTIC_OWNER_TOKEN=$token
        $job=[PldDiagnosticV2.OwnedJob]::new([IO.Path]::GetFullPath($Python),$nativeLine,$Log,$stderr)
        $child=$job.Child;$diagState.child_pid=$child.Id
        $diagState.child_start_UTC=$child.StartTime.ToUniversalTime().ToString('o');$diagState.child_running_at_return=$true
        $diagState.status='WAITING_FOR_FIRST_PACKET_OR_LOCAL_EXIT'
        [IO.File]::WriteAllText($statusFile,($diagState|ConvertTo-Json -Depth 6),$utf8)
        while ($true) {
            $child.Refresh()
            $sample=@{utc=[DateTime]::UtcNow.ToString('o');elapsed_seconds=$clock.Elapsed.TotalSeconds;
                child_pid=$child.Id;has_exited=$child.HasExited;first_packet_confirmed=$diagState.first_packet_confirmed;owned_active_pids=@($job.ActivePids())}
            $sample.owned_active_processes=@(foreach ($ownedPid in $sample.owned_active_pids) {
                $ownedProcess=$null
                try {
                    $ownedProcess=[Diagnostics.Process]::GetProcessById([int]$ownedPid)
                    @{pid=[int]$ownedPid;image_name=$ownedProcess.ProcessName;start_UTC=$ownedProcess.StartTime.ToUniversalTime().ToString('o')}
                } catch { @{pid=[int]$ownedPid;identity_error=$_.Exception.Message} }
                finally { if ($null -ne $ownedProcess) { $ownedProcess.Dispose() } }
            })
            if (!$workerRecordVerified -and (Test-Path -LiteralPath $workerMarker)) {
                $candidate=$null
                try {
                    $identity=Get-Content -LiteralPath $workerMarker -Raw -Encoding UTF8 | ConvertFrom-Json
                    $identityPid=[int]$identity.pid
                    if ($identity.scope -ne 'DIAGNOSTIC_BOOTSTRAP_WORKER_V2' -or
                        $identity.owner_token -cne $token -or $identityPid -le 0 -or
                        [IO.Path]::GetFullPath([string]$identity.executable) -ine $expectedWorkerExecutable -or
                        [IO.Path]::GetFullPath([string]$identity.prefix) -ine $expectedWorkerPrefix) {
                        throw 'Worker identity token, interpreter origin, or launch scope mismatch.'
                    }
                    $candidate=[Diagnostics.Process]::GetProcessById($identityPid)
                    $candidate.Refresh()
                    if ($candidate.HasExited) { throw 'Worker exited before the supervisor could authenticate it.' }
                    if (!$job.Owns($candidate) -or $candidate.StartTime.ToUniversalTime() -lt $child.StartTime.ToUniversalTime()) {
                        throw 'Worker is outside the owned Job or predates this launch.'
                    }
                    $actualParent=[PldDiagnosticV2.OwnedJob]::ParentPid($identityPid)
                    $expectedParent=if ($identityPid -eq $child.Id) { $PID } else { $child.Id }
                    if ([int]$identity.parent_pid -ne $actualParent -or $actualParent -ne $expectedParent) {
                        throw 'Worker parent is not the direct PowerShell child or its launched worker.'
                    }
                    $actualImage=[IO.Path]::GetFullPath([PldDiagnosticV2.OwnedJob]::ImagePath($candidate))
                    if ($actualImage -notin $expectedImagePaths) { throw 'Worker process image is outside the selected system Python/venv origin.' }

                    $workerRecordVerified=$true;$worker=$candidate;$candidate=$null
                    $diagState.worker_pid=$identityPid
                    $diagState.worker_start_UTC=$worker.StartTime.ToUniversalTime().ToString('o')
                    $diagState.worker_authentication_completed=$true
                    $diagState.worker_authentication_before_target=$true
                    $diagState.worker_identity=@{pid=$identityPid;parent_pid=$actualParent;executable=$identity.executable;process_image=$actualImage;prefix=$identity.prefix;ownership_proof='TOKEN_SCOPE_INTERPRETER_PARENT_AND_LIVE_OWNED_JOB';target_released_after_authentication=$false}
                    $auth=@{scope='DIAGNOSTIC_SUPERVISOR_AUTH_V2';owner_token=$token;pid=$identityPid;executable=$expectedWorkerExecutable;prefix=$expectedWorkerPrefix;supervisor_pid=$PID;launcher_pid=$child.Id;worker_start_UTC=$diagState.worker_start_UTC;ownership_proof='TOKEN_SCOPE_INTERPRETER_PARENT_AND_LIVE_OWNED_JOB'}
                    $authStream=[IO.File]::Open($workerAuthPending,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
                    try {
                        $authWriter=[IO.StreamWriter]::new($authStream,$utf8)
                        try { $authWriter.WriteLine(($auth|ConvertTo-Json -Compress -Depth 4));$authWriter.Flush();$authStream.Flush($true) }
                        finally { $authWriter.Dispose() }
                    } finally { $authStream.Dispose() }
                    [IO.File]::Move($workerAuthPending,$workerAuthMarker)
                    $diagState.worker_identity.target_released_after_authentication=$true
                } catch {
                    $sample.worker_identity_error=$_.Exception.Message
                    if ($null -ne $candidate) { $candidate.Dispose();$candidate=$null }
                }
            }
            $accounted=$child
            if ($null -ne $worker) { $accounted=$worker;$worker.Refresh() }
            if ($workerIdentityVerifiedAfterExit) {
                $sample.accounting_pid=$diagState.worker_pid
                $sample.accounting_role='BOOTSTRAP_WORKER_EXITED_BEFORE_SAMPLE'
                $sample.process_accounting_unavailable='Authenticated worker record; the process had exited before CPU/I/O sampling.'
            } else {
                $sample.accounting_pid=$accounted.Id
                $sample.accounting_role=if ($null -ne $worker) {'BOOTSTRAP_WORKER'} else {'LAUNCHER_PENDING_WORKER_IDENTITY'}
                try {
                    $sample.cpu_seconds=$accounted.TotalProcessorTime.TotalSeconds;$sample.working_set_bytes=$accounted.WorkingSet64
                    $counters=New-Object PldDiagnosticV2.IoCounters
                    if ([PldDiagnosticV2.OwnedJob]::GetProcessIoCounters($accounted.Handle,[ref]$counters)) { $sample.io_counters=$counters }
                    else { $sample.io_unavailable_win32_error=[Runtime.InteropServices.Marshal]::GetLastWin32Error() }
                } catch { $sample.process_accounting_error=$_.Exception.Message }
            }
            if (!$diagState.first_packet_confirmed -and $workerRecordVerified -and (Test-Path -LiteralPath $marker)) {
                try {
                    $first=Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
                    $markerUtc=[DateTimeOffset]::Parse([string]$first.utc).UtcDateTime
                    $earliest=$child.StartTime.ToUniversalTime().AddSeconds(-2)
                    $latest=[DateTime]::UtcNow.AddSeconds(2)
                    if ($first.scope -ne 'FIRST_UDP_SENDTO_RETURNED_OS_ACCEPTED_ONLY' -or
                        [int]$first.pid -ne $diagState.worker_pid -or $first.owner_token -cne $token -or
                        [int]$first.bytes -le 0 -or [long]$first.monotonic_ns -le 0 -or
                        $markerUtc -lt $earliest -or $markerUtc -gt $latest) {
                        throw 'First-send marker identity, lifetime, or send result is invalid; deadline stays armed.'
                    }
                    $diagState.first_packet_confirmed=$true
                    $diagState.first_packet_record=@{scope=$first.scope;pid=$first.pid;utc=$first.utc;monotonic_ns=$first.monotonic_ns;bytes=$first.bytes;peer=$first.peer;board_receive_or_reply_proven=$false}
                    $diagState.status='FIRST_PACKET_CONFIRMED_PRE_PACKET_DEADLINE_DISARMED'
                    [IO.File]::WriteAllText($statusFile,($diagState|ConvertTo-Json -Depth 6),$utf8)
                } catch { $sample.marker_error=$_.Exception.Message }
            }
            $sample.first_packet_confirmed=$diagState.first_packet_confirmed
            $writer.WriteLine(($sample|ConvertTo-Json -Compress -Depth 6))
            if ($child.HasExited) {
                $remaining=@($job.ActivePids() | Where-Object { $_ -ne $child.Id })
                if ($remaining.Count -gt 0) {
                    $diagState.owned_processes_after_launcher_exit=$remaining
                    $drain=[Diagnostics.Stopwatch]::StartNew()
                    while ($remaining.Count -gt 0 -and $drain.Elapsed.TotalMilliseconds -lt $OwnedDescendantDrainMilliseconds) {
                        Start-Sleep -Milliseconds 50
                        $remaining=@($job.ActivePids() | Where-Object { $_ -ne $child.Id })
                    }
                    $drain.Stop();$diagState.owned_descendant_drain_elapsed_ms=$drain.Elapsed.TotalMilliseconds
                    if ($remaining.Count -eq 0) {
                        $diagState.owned_descendants_drained_after_exit=$true
                    } else {
                        $diagState.launcher_exited_with_owned_processes=$true
                        $diagState.owned_processes_still_active_after_drain=$remaining
                        $diagState.status='LAUNCHER_EXITED_WITH_OWNED_PROCESSES'
                        $diagState.interpretation='Owned descendants remained after the bounded drain interval; terminate only this Job and reject the attempt.'
                        $diagExit=125
                    }
                }
                if ((Test-Path -LiteralPath $marker) -and (!$workerRecordVerified -or !$diagState.first_packet_confirmed)) {
                    if (!$diagState.launcher_exited_with_owned_processes) { $diagState.status='SUPERVISOR_FAILED_PRESERVE_LOGS' }
                    $diagState.first_packet_marker_unverified_at_exit=$true
                    if (!$diagState.launcher_exited_with_owned_processes) {
                        $diagState.interpretation='A first-send marker exists, but its worker identity and marker binding were not authenticated before launcher exit.'
                    }
                    $diagExit=125
                }
                break
            }
            if (!$diagState.first_packet_confirmed -and $clock.Elapsed.TotalSeconds -ge $FirstPacketDeadlineSeconds) {
                $timedOut=$true;$diagState.status='FIRST_PACKET_CONFIRMATION_DEADLINE_EXCEEDED'
                $diagState.interpretation='No owned worker sendto-return marker. Inspect stages/stacks; send attempt alone does not prove FPGA receipt.'
                $job.Stop(124)
                if (!$child.WaitForExit(5000)) { throw 'Owned launcher termination pending; preserve logs and do not Pack.' }
                break
            }
            Start-Sleep -Milliseconds 50
        }
        $jobExit=$job.ExitCode()
        if ($timedOut) { $diagExit=124 }
        elseif ($diagState.launcher_exited_with_owned_processes -or $diagState.first_packet_marker_unverified_at_exit) { $diagExit=125 }
        else { $diagExit=$jobExit;$diagState.status='CHILD_EXITED' }
    } catch {
        $diagState.supervisor_error=$_.Exception.Message;$diagState.status='SUPERVISOR_FAILED_PRESERVE_LOGS';$diagExit=125
    } finally {
        # Only terminate the pre-assigned owned job; no global name/PID kills.
        if ($null -ne $job) {
            try {
                $active=@($job.ActivePids())
                if ($active.Count -gt 0) {
                    $diagState.cleanup_pids=$active;$job.Stop([uint32]$diagExit)
                    $cleanup=[Diagnostics.Stopwatch]::StartNew()
                    do { Start-Sleep -Milliseconds 20;$active=@($job.ActivePids()) } while ($active.Count -gt 0 -and $cleanup.Elapsed.TotalSeconds -lt 5)
                }
                $diagState.owned_active_pids_at_return=$active;$diagState.owned_processes_running_at_return=($active.Count -gt 0)
                if ($active.Count -gt 0) { throw 'Owned job termination pending; Pack is prohibited.' }
            } catch { $diagState.cleanup_error=$_.Exception.Message;$diagExit=125 }
            finally { $job.Dispose() }
        } else { $diagState.owned_processes_running_at_return=$false }
        foreach ($entry in @(@{process=$child;key='child_running_at_return'},@{process=$worker;key='worker_running_at_return'})) {
            if ($null -ne $entry.process) { try { $entry.process.Refresh();$diagState[$entry.key]=!$entry.process.HasExited } catch { $diagState[$entry.key]=$false };$entry.process.Dispose() }
        }
        $env:PYTHONIOENCODING=$priorEncoding;$env:PLD_DIAGNOSTIC_OWNER_TOKEN=$priorToken
        $writer.Dispose();$clock.Stop();$diagState.elapsed_seconds=$clock.Elapsed.TotalSeconds;$diagState.exit_code=$diagExit
        [IO.File]::WriteAllText($statusFile,($diagState|ConvertTo-Json -Depth 6),$utf8)
    }
    if (Test-Path -LiteralPath $Log) { Get-Content -LiteralPath $Log -Tail 8 }
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Tail 8 }
    if ($diagExit -ne 0) { throw "Diagnostic Python failed (exit $diagExit). Preserve $statusFile and all attempt files." }
}
