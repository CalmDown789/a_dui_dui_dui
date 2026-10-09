[CmdletBinding()]

param(

    [ValidateSet('Preflight','RuntimePreflight','Run','Audit','Pack')][string]$Mode='Preflight',

    [Parameter(Mandatory=$true)][string]$CommPackage,

    [string]$Python='C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe',

    [string]$StartupCaptureReport,

    [string]$RunRoot,

    [ValidateSet('torch-cuda-f64','opencv-f64')][string]$Backend='torch-cuda-f64',

    [ValidateRange(0.1,600)][double]$Seconds=300,

    [ValidateRange(0.1,60)][double]$Fps=30,

    [ValidateSet('pc4k','protocol-main','sender-no-pipeline','pipeline-no-preview','pipeline-with-preview')][string]$DiagnosticStage='pc4k',

    [ValidateRange(0,16)][int]$DiagnosticFrames=0,

    [ValidateRange(1,120)][double]$PreparationDeadlineSeconds=120,

    [ValidateRange(0.1,120)][double]$DiagnosticStackIntervalSeconds=30

)

Set-StrictMode -Version Latest

$ErrorActionPreference='Stop'

$supplementRoot=[IO.Path]::GetFullPath($PSScriptRoot)

$primaryRoot=[IO.Path]::GetFullPath($CommPackage)

if (!(Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Use an existing Python environment; no package installation is performed.' }

function Save-LabJson([string]$Path,$Object) {

    [IO.File]::WriteAllText($Path,($Object | ConvertTo-Json -Depth 18),[Text.UTF8Encoding]::new($false))

}

function Check-LabNetwork([string]$File) {

    $wantedMac='00E04C194B88'

    $inventoryErrors=@()

    $allAdapters=@(Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue -ErrorVariable +inventoryErrors)

    $allIps=@(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue -ErrorVariable +inventoryErrors)

    $allNeighbors=@(Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue -ErrorVariable +inventoryErrors)

    $udpEndpoints=@(Get-NetUDPEndpoint -ErrorAction SilentlyContinue -ErrorVariable +inventoryErrors | Where-Object { [int]$_.LocalPort -eq 6102 })

    $adapterMatches=@($allAdapters | Where-Object { ($_.MacAddress -replace '[-:]','').ToUpperInvariant() -eq $wantedMac })
    $adapterStats=@()
    if ($adapterMatches.Count -eq 1) { $adapterStats=@(Get-NetAdapterStatistics -Name $adapterMatches[0].Name -ErrorAction SilentlyContinue -ErrorVariable +inventoryErrors | Select-Object Name,ReceivedUnicastBytes,ReceivedUnicastPackets,ReceivedDiscardedPackets,ReceivedPacketErrors,SentUnicastBytes,SentUnicastPackets,OutboundDiscardedPackets,OutboundPacketErrors) }
    $udpRaw=@(& "$env:SystemRoot\System32\netstat.exe" -s -p udp 2>&1 | ForEach-Object { [string]$_ })
    $activeLine=@($udpRaw | Select-String -Pattern '^\s*Active Connections' | Select-Object -First 1)
    $udpStatistics=if($activeLine.Count){@($udpRaw | Select-Object -First ([int]$activeLine[0].LineNumber-1))}else{$udpRaw}

    Save-LabJson $File @{scope='ACTUAL_READ_ONLY_NETWORK_INVENTORY'; captured_UTC=[DateTime]::UtcNow.ToString('o'); adapters=@($allAdapters | Select-Object Name,ifIndex,MacAddress,Status,LinkSpeed); selected_adapter_statistics=@($adapterStats); selected_adapter_counter_scope='One physical USB Ethernet adapter matched by its actual MAC'; system_udp_netstat_summary=@($udpStatistics); system_udp_counter_scope='Host-wide Windows UDP counters; cannot be attributed to this session'; ipv4=@($allIps | Select-Object InterfaceIndex,IPAddress,PrefixLength,AddressState); neighbors=@($allNeighbors | Select-Object InterfaceIndex,IPAddress,LinkLayerAddress,State); udp6102=@($udpEndpoints | Select-Object LocalAddress,LocalPort,OwningProcess); query_errors=@($inventoryErrors | ForEach-Object { $_.ToString() }); mutation_performed=$false}

    $matches=@($allAdapters | Where-Object { ($_.MacAddress -replace '[-:]','').ToUpperInvariant() -eq $wantedMac })

    if ($matches.Count -ne 1) { throw 'Expected exactly one actual C USB Ethernet MAC 00-E0-4C-19-4B-88. Preserve the snapshot and report changed hardware.' }

    $adapter=$matches[0]

    if ($adapter.Status -ne 'Up' -or [string]$adapter.LinkSpeed -notmatch '^1\s*Gbps$') { throw 'The selected USB Ethernet must be Up at 1 Gbps.' }

    $labIndex=[int]$adapter.ifIndex

    $ips=@($allIps | Where-Object { [int]$_.InterfaceIndex -eq $labIndex -and $_.IPAddress -eq '192.168.0.3' -and $_.PrefixLength -eq 24 -and [string]$_.AddressState -eq 'Preferred' })

    if ($ips.Count -ne 1) { throw 'Use the documented static 192.168.0.3/24 on this actual adapter.' }

    $allTargetIps=@($allIps | Where-Object { $_.IPAddress -eq '192.168.0.3' -and [string]$_.AddressState -eq 'Preferred' })

    if ($allTargetIps.Count -ne 1 -or [int]$allTargetIps[0].InterfaceIndex -ne $labIndex) { throw '192.168.0.3 must be unique on the selected adapter.' }

    $neighbors=@($allNeighbors | Where-Object { [int]$_.InterfaceIndex -eq $labIndex -and $_.IPAddress -eq '192.168.0.2' -and [string]$_.State -eq 'Permanent' -and ($_.LinkLayerAddress -replace '[-:]','').ToUpperInvariant() -eq '000A3501FEC0' })

    if ($neighbors.Count -ne 1) { throw 'Exact Permanent neighbor 192.168.0.2 -> 00-0A-35-01-FE-C0 is required on this adapter.' }

    if ($udpEndpoints.Count -ne 0) { throw 'UDP 6102 is occupied. Close its identified application; this script never kills it.' }

    if ($inventoryErrors.Count -ne 0) { throw 'Network inventory query errors were saved; resolve them before running.' }

}





$attempts=Join-Path $supplementRoot 'attempts'

if (!$RunRoot) {

    if ($Mode -in @('Audit','Pack')) { throw 'Use the printed original run directory.' }

    $RunRoot=Join-Path $attempts ($Mode+'_'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))

}

$attempt=[IO.Path]::GetFullPath($RunRoot)

if (!$attempt.StartsWith($attempts+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Use a fresh attempt inside this supplement attempts directory.' }

if ($Mode -in @('Preflight','RuntimePreflight','Run')) {

    if (Test-Path -LiteralPath $attempt) { throw 'Never overwrite an old attempt.' }

    New-Item -ItemType Directory -Path $attempt | Out-Null

} elseif (!(Test-Path -LiteralPath $attempt -PathType Container)) { throw 'Original attempt is missing.' }

$selection=Get-Content -LiteralPath (Join-Path $primaryRoot 'STREAMING_SELECTION.json') -Raw -Encoding UTF8 | ConvertFrom-Json

foreach ($name in @('lab_bootstrap.py','lab_diagnostics.py','Invoke-DiagnosticPython.ps1','owned_job.cs')) {

    $file=Join-Path $primaryRoot ('diagnostics\'+$name)

    $hasher=[Security.Cryptography.SHA256]::Create()

    try { $digest=[BitConverter]::ToString($hasher.ComputeHash([IO.File]::ReadAllBytes($file))).Replace('-','').ToLowerInvariant() }

    finally { $hasher.Dispose() }

    if ($digest -ne $selection.files.PSObject.Properties['diagnostics/'+$name].Value) { throw ('Diagnostic source mismatch: '+$name) }

}

. (Join-Path $primaryRoot 'diagnostics\Invoke-DiagnosticPython.ps1')

$precheck=Join-Path $attempt ('supplement_precheck_'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))

Invoke-DiagnosticPython -Python $Python -Script (Join-Path $supplementRoot 'live4k.py') -ScriptArgs @('--package',$primaryRoot,'--files-only','--out-dir',$precheck) -Log ($precheck+'.log') -FirstPacketDeadlineSeconds $PreparationDeadlineSeconds -StackIntervalSeconds $DiagnosticStackIntervalSeconds

if ($Mode -eq 'Preflight') { Write-Host "Files-only preflight complete: $attempt"; exit 0 }
if ($Mode -eq 'RuntimePreflight') {
    Invoke-DiagnosticPython -Python $Python -Script (Join-Path $supplementRoot 'live4k.py') -ScriptArgs @('--package',$primaryRoot,'--files-only','--runtime-preflight','--backend',$Backend,'--out-dir',(Join-Path $attempt 'runtime')) -Log (Join-Path $attempt 'runtime.log') -FirstPacketDeadlineSeconds $PreparationDeadlineSeconds -StackIntervalSeconds $DiagnosticStackIntervalSeconds
    Write-Host "Runtime backend/Golden/Tk preflight complete without board IO: $attempt"
    exit 0
}

if ($Mode -eq 'Run') {

    if (!$StartupCaptureReport) { throw 'Actual post-JTAG startup capture from this exact COMM BIT is required.' }

    Check-LabNetwork (Join-Path $attempt 'network_before.json')

    $isDiagnostic=$DiagnosticStage -ne 'pc4k'
    $state=@{scope=$(if($isDiagnostic){'ONE_VARIABLE_COMM_4K_DIAGNOSTIC_NOT_FORMAL_PC4K_MEASUREMENT'}else{'CONTINUOUS_COMM_4K_APP_MEASUREMENT_NOT_PANEL_REFRESH'});status='RUNNING';attempt=$attempt;diagnostic_stage=$DiagnosticStage;UART_JTAG_requested=$false;Flash_written=$false;whole_system_4K30_achieved=$false}

    try {

        $liveArgs=@('--package',$primaryRoot,'--startup-capture-report',$StartupCaptureReport,'--backend',$Backend,'--seconds',$Seconds.ToString([Globalization.CultureInfo]::InvariantCulture),'--fps',$Fps.ToString([Globalization.CultureInfo]::InvariantCulture),'--out-dir',(Join-Path $attempt 'live'))
        if ($isDiagnostic) {
            if ($DiagnosticFrames -lt 1) { throw 'DiagnosticStage requires DiagnosticFrames in the range 1..16.' }
            $liveArgs+=@('--diagnostic-stage',$DiagnosticStage,'--diagnostic-frames',([string]$DiagnosticFrames))
        }
        Invoke-DiagnosticPython -Python $Python -Script (Join-Path $supplementRoot 'live4k.py') -ScriptArgs $liveArgs -Log (Join-Path $attempt 'live.log') -FirstPacketDeadlineSeconds $PreparationDeadlineSeconds -StackIntervalSeconds $DiagnosticStackIntervalSeconds

        Check-LabNetwork (Join-Path $attempt 'network_after.json')

        if ($isDiagnostic) { $state.status='DIAGNOSTIC_COMPARISON_PENDING_REVIEW' }
        else { $state.status='COMPLETE_MEASUREMENT_PENDING_INDEPENDENT_AUDIT' }

    } catch { $state.status='FAIL_PRESERVE_ALL_EVIDENCE'; $state.error=$_.Exception.Message; throw }

    finally { Save-LabJson (Join-Path $attempt 'RUN_STATUS.json') $state; Write-Host "Attempt: $attempt" }

} elseif ($Mode -eq 'Audit') {

    $savedState=Join-Path $attempt 'RUN_STATUS.json'
    if (Test-Path -LiteralPath $savedState) {
        $saved=Get-Content -LiteralPath $savedState -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($saved.PSObject.Properties.Name -contains 'diagnostic_stage' -and $saved.diagnostic_stage -and $saved.diagnostic_stage -ne 'pc4k') { throw 'Diagnostic comparisons are not eligible for the official complete PC4K audit.' }
    }

    $audit=Join-Path $attempt ('audit_'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))

    & $Python -B (Join-Path $supplementRoot 'audit_live4k.py') --package $primaryRoot --run (Join-Path $attempt 'live') --out-dir $audit

    if ($LASTEXITCODE -ne 0) { throw 'Independent audit failed; preserve its failure and all raw evidence.' }

} else {

    foreach ($file in @(Get-ChildItem -LiteralPath $attempt -Filter '*.diag.status.json' -File)) {

        $owned=Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json

        $names=$owned.PSObject.Properties.Name
        if ($owned.scope -ne 'OWNED_LAB_PYTHON_JOB_SUPERVISOR_V2' -or
            $names -notcontains 'owned_processes_running_at_return' -or
            $names -notcontains 'launcher_exited_with_owned_processes' -or
            $owned.status -notin @('CHILD_EXITED','FIRST_PACKET_CONFIRMATION_DEADLINE_EXCEEDED','SUPERVISOR_FAILED_PRESERVE_LOGS','LAUNCHER_EXITED_WITH_OWNED_PROCESSES') -or
            ($owned.status -eq 'LAUNCHER_EXITED_WITH_OWNED_PROCESSES' -and $owned.launcher_exited_with_owned_processes -ne $true) -or
            ($owned.status -ne 'LAUNCHER_EXITED_WITH_OWNED_PROCESSES' -and $owned.launcher_exited_with_owned_processes -ne $false) -or
            $owned.owned_processes_running_at_return -ne $false -or
            $owned.child_running_at_return -ne $false -or $owned.worker_running_at_return -ne $false -or
            @($owned.owned_active_pids_at_return).Count -ne 0) {
            throw 'Diagnostic launcher/worker shutdown is not confirmed; preserve growing files and do not Pack.'
        }
    }

    $archive=$attempt+'_evidence_'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')+'.zip'

    & $Python -B (Join-Path $primaryRoot 'scripts\zip_evidence.py') --evidence-root $attempt --out-zip $archive

    if ($LASTEXITCODE -ne 0) { throw 'Evidence packaging failed; preserve original files.' }

    Write-Host "Evidence archive: $archive"

}

