[CmdletBinding()]
param(
    [ValidateSet('Preflight','Run','Pack')][string]$Mode='Preflight',
    [string]$Python='C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe',
    [string]$Vivado='E:\AMDTools2025\2025.2\Vivado\bin\vivado.bat',
    [string]$AttemptRoot
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$labPackage=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ($labPackage.Length -gt 140) { throw 'Extract to a short path (for example E:\acx_lab) before running.' }
if (!(Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Use the existing C Python executable.' }

function Save-LabJson([string]$Path,$Object) {
    [IO.File]::WriteAllText($Path,($Object | ConvertTo-Json -Depth 18),[Text.UTF8Encoding]::new($false))
}
function Invoke-LabPython([string[]]$ArgumentList,[string]$Log) {
    if (Test-Path -LiteralPath $Log) { throw 'A previous log exists; choose a fresh attempt.' }
    $savedPreference=$ErrorActionPreference
    try {
        $ErrorActionPreference='Continue'
        & $Python -B @ArgumentList *> $Log
        $labExit=$LASTEXITCODE
    } finally { $ErrorActionPreference=$savedPreference }
    Get-Content -LiteralPath $Log -Tail 12
    if ($labExit -ne 0) { throw "Python stage failed with exit $labExit; preserve all files." }
}
function Check-LabNetwork([string]$File) {
    $wantedMac='00E04C194B88'
    $inventoryErrors=@()
    $allAdapters=@(Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue -ErrorVariable +inventoryErrors)
    $allIps=@(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue -ErrorVariable +inventoryErrors)
    $allNeighbors=@(Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue -ErrorVariable +inventoryErrors)
    $udpEndpoints=@(Get-NetUDPEndpoint -ErrorAction SilentlyContinue -ErrorVariable +inventoryErrors | Where-Object { [int]$_.LocalPort -eq 6102 })
    Save-LabJson $File @{scope='ACTUAL_READ_ONLY_NETWORK_INVENTORY'; captured_UTC=[DateTime]::UtcNow.ToString('o'); adapters=@($allAdapters | Select-Object Name,ifIndex,MacAddress,Status,LinkSpeed); ipv4=@($allIps | Select-Object InterfaceIndex,IPAddress,PrefixLength,AddressState); neighbors=@($allNeighbors | Select-Object InterfaceIndex,IPAddress,LinkLayerAddress,State); udp6102=@($udpEndpoints | Select-Object LocalAddress,LocalPort,OwningProcess); query_errors=@($inventoryErrors | ForEach-Object { $_.ToString() }); mutation_performed=$false}
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

function Assert-LabCaptureWritersStopped([string]$Directory) {
    foreach ($name in @('startup_for_2','startup_for_16')) {
        $captureDir=Join-Path $Directory $name
        $captureReport=Join-Path $captureDir 'REPORT.json'
        if (Test-Path -LiteralPath $captureReport) {
            try { $savedCapture=Get-Content -LiteralPath $captureReport -Raw -Encoding UTF8 | ConvertFrom-Json }
            catch { throw "Unreadable $name report; preserve it and confirm the programmer has ended before Pack." }
            if ($savedCapture.PSObject.Properties.Name -contains 'JTAG_process_running_at_capture_return' -and $savedCapture.JTAG_process_running_at_capture_return -eq $true) {
                if (!($savedCapture.PSObject.Properties.Name -contains 'JTAG_process_pid') -or !$savedCapture.JTAG_process_pid) { throw "Running programmer without PID in $name; preserve all logs." }
                if (Get-Process -Id $savedCapture.JTAG_process_pid -ErrorAction SilentlyContinue) { throw "Recorded programmer for $name is still running; wait, preserve growing logs, do not Pack or launch another programmer." }
            }
        } elseif (Test-Path -LiteralPath (Join-Path $captureDir 'events.jsonl')) {
            throw "Missing $name report after capture began; preserve growing logs and check the original programmer before Pack."
        }
    }
}

function Update-LabObservedActions($State,[string]$Directory) {
    $jtagObserved=$false
    $networkObserved=$false
    foreach ($name in @('startup_for_2','startup_for_16')) {
        $report=Join-Path $Directory ($name+'\REPORT.json')
        if (Test-Path -LiteralPath $report) {
            try {
                $capture=Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($capture.PSObject.Properties.Name -contains 'JTAG_process_pid' -and $capture.JTAG_process_pid) { $jtagObserved=$true }
            } catch { }
        }
    }
    foreach ($name in @('Smoke','Probe','Natural2','Natural16')) {
        foreach ($leaf in @('REPORT.json','SUMMARY.json')) {
            $report=Join-Path $Directory ($name+'\'+$leaf)
            if (Test-Path -LiteralPath $report) {
                try {
                    $operation=Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($operation.PSObject.Properties.Name -contains 'network_traffic_started' -and $operation.network_traffic_started -eq $true) { $networkObserved=$true }
                } catch { }
            }
        }
        $events=Join-Path $Directory ($name+'\events.jsonl')
        if (Test-Path -LiteralPath $events) {
            foreach ($line in (Get-Content -LiteralPath $events -Encoding UTF8)) {
                try {
                    $event=$line | ConvertFrom-Json
                    if ($event.PSObject.Properties.Name -contains 'event' -and $event.event -eq 'SEND') { $networkObserved=$true }
                } catch { }
            }
        }
    }
    $State.JTAG_started_observed_in_child_report=$jtagObserved
    $State.network_traffic_observed_in_child_report=$networkObserved
    $State.observation_note='False means no confirming child report; interrupted or incomplete captures remain unknown. Requested actions do not prove execution.'
}

$labAttempts=Join-Path $labPackage 'attempts'
if ($Mode -eq 'Pack') {
    if (!$AttemptRoot) { throw 'Pack requires the printed attempt path, including a failed attempt.' }
    $labAttempt=[IO.Path]::GetFullPath($AttemptRoot)
    if (!$labAttempt.StartsWith($labAttempts+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or !(Test-Path -LiteralPath $labAttempt -PathType Container)) { throw 'Pack only a real attempt inside this package attempts directory.' }
    Assert-LabCaptureWritersStopped $labAttempt
    $labArchive=$labAttempt+'_evidence_'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')+'.zip'
    Invoke-LabPython @((Join-Path $labPackage 'scripts\zip_evidence.py'),'--evidence-root',$labAttempt,'--out-zip',$labArchive) ($labArchive+'.log')
    Write-Host "Evidence archive (observations only, including failures): $labArchive"
    exit 0
}
if (!$AttemptRoot) { $AttemptRoot=Join-Path $labAttempts ('lab_'+$Mode+'_'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')) }
$labAttempt=[IO.Path]::GetFullPath($AttemptRoot)
if (!$labAttempt.StartsWith($labAttempts+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'A lab attempt must stay inside this package attempts directory.' }
if (Test-Path -LiteralPath $labAttempt) { throw 'Use a fresh attempt; never resume or overwrite old evidence.' }
New-Item -ItemType Directory -Path $labAttempt | Out-Null
$labState=@{scope='BOARD_LAB_FUNCTIONAL_OBSERVATIONS_ONLY'; mode=$Mode; status='RUNNING'; physical_IO_signoff=$false; complete_stage_acceptance=$false; network_attempt_requested=$false; JTAG_attempt_requested=$false; attempt=$labAttempt}
try {
    $labSelection=Get-Content -LiteralPath (Join-Path $labPackage 'LAB_FUNCTIONAL_SELECTION.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Invoke-LabPython @((Join-Path $PSScriptRoot 'board_lab_functional.py'),'--mode','Smoke','--files-only','--out-dir',(Join-Path $labAttempt 'file_precheck')) (Join-Path $labAttempt 'file_precheck.log')
    Invoke-LabPython @('-c','import serial; print(serial.__version__)') (Join-Path $labAttempt 'existing_pyserial.log')
    if (!(Test-Path -LiteralPath $Vivado -PathType Leaf)) { throw 'Use the existing C Vivado executable.' }
    if ($Mode -eq 'Preflight') {
        $labState.status='PASS_LOCAL_FILES_ONLY_NO_UART_JTAG_OR_NETWORK'
    } else {
        Check-LabNetwork (Join-Path $labAttempt 'network_before.json')
        $labManifest=Join-Path $labPackage $labSelection.characterization_manifest.file
        $labProgram=Join-Path $labPackage 'scripts\program_board_characterization.tcl'
        $labCapture=Join-Path $labPackage 'scripts\capture_board_characterization.py'
        $labCapture2=Join-Path $labAttempt 'startup_for_2'
        $labState.JTAG_attempt_requested=$true
        Invoke-LabPython @($labCapture,'--manifest',$labManifest,'--issued-manifest-sha256',$labSelection.characterization_manifest.sha256,'--port','COM3','--vivado-bat',$Vivado,'--program-tcl',$labProgram,'--out-dir',$labCapture2) (Join-Path $labAttempt 'startup_for_2.log')
        foreach ($labStep in @('Smoke','Probe','Natural2')) {
            Check-LabNetwork (Join-Path $labAttempt ('network_before_'+$labStep+'.json'))
            $labOut=Join-Path $labAttempt $labStep
            $labState.network_attempt_requested=$true
            Invoke-LabPython @((Join-Path $PSScriptRoot 'board_lab_functional.py'),'--mode',$labStep,'--startup-capture-report',(Join-Path $labCapture2 'REPORT.json'),'--out-dir',$labOut) (Join-Path $labAttempt ($labStep+'.log'))
            if ($labStep -eq 'Natural2') {
                $labAuditArgs=@((Join-Path $labPackage 'host\audit_ethernet_video_run.py'),'--run',$labOut,'--source-manifest',(Join-Path $labPackage $labSelection.sequence_manifests.Natural2.file),'--out-dir',(Join-Path $labAttempt ($labStep+'_raw_audit')))
            } else {
                $labAuditArgs=@((Join-Path $labPackage 'host\audit_input_protocol_probe.py'),'--run',$labOut,'--out-dir',(Join-Path $labAttempt ($labStep+'_raw_audit')))
                if ($labStep -eq 'Smoke') { $labAuditArgs+=@('--smoke-only') }
            }
            Invoke-LabPython $labAuditArgs (Join-Path $labAttempt ($labStep+'_raw_audit.log'))
        }
        $labCapture16=Join-Path $labAttempt 'startup_for_16'
        Invoke-LabPython @($labCapture,'--manifest',$labManifest,'--issued-manifest-sha256',$labSelection.characterization_manifest.sha256,'--port','COM3','--vivado-bat',$Vivado,'--program-tcl',$labProgram,'--out-dir',$labCapture16) (Join-Path $labAttempt 'startup_for_16.log')
        Check-LabNetwork (Join-Path $labAttempt 'network_before_Natural16.json')
        Invoke-LabPython @((Join-Path $PSScriptRoot 'board_lab_functional.py'),'--mode','Natural16','--startup-capture-report',(Join-Path $labCapture16 'REPORT.json'),'--out-dir',(Join-Path $labAttempt 'Natural16')) (Join-Path $labAttempt 'Natural16.log')
        Invoke-LabPython @((Join-Path $labPackage 'host\audit_ethernet_video_run.py'),'--run',(Join-Path $labAttempt 'Natural16'),'--source-manifest',(Join-Path $labPackage $labSelection.sequence_manifests.Natural16.file),'--out-dir',(Join-Path $labAttempt 'Natural16_raw_audit')) (Join-Path $labAttempt 'Natural16_raw_audit.log')
        Check-LabNetwork (Join-Path $labAttempt 'network_after.json')
        $labState.status='COMPLETE_LAB_RAW_OBSERVATIONS_PENDING_ROOT_REVIEW_AND_MANUAL_VIEWING'
        Write-Host ('Open returned playback, record viewing, then Pack: '+(Join-Path $labAttempt 'Natural16\playback.html'))
    }
    Update-LabObservedActions $labState $labAttempt
    Save-LabJson (Join-Path $labAttempt 'LAB_RUN_STATUS.json') $labState
    Write-Host "Attempt: $labAttempt"
    exit 0
} catch {
    $labState.status='FAILED_LAB_ATTEMPT_PRESERVE_RAW_FILES'
    $labState.error=$_.Exception.Message
    Update-LabObservedActions $labState $labAttempt
    Save-LabJson (Join-Path $labAttempt 'LAB_RUN_STATUS.json') $labState
    [IO.File]::WriteAllText((Join-Path $labAttempt 'FAILURE.txt'),($_ | Out-String),[Text.UTF8Encoding]::new($false))
    Write-Host "Stopped. Preserve and Pack failed attempt: $labAttempt"
    Write-Error $_ -ErrorAction Continue
    exit 1
}
