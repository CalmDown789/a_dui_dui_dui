# Independent LAB-only wrapper. No formal host import, network or video run.
[CmdletBinding()]
param(
    [ValidateSet('Preflight', 'Capture', 'VerifyCapture', 'Pack')]
    [string]$Stage = 'Preflight',
    [string]$PackageRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskPython = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe',
    [string]$TaskVivado = 'E:\AMDTools2025\2025.2\Vivado\bin\vivado.bat',
    [string]$AttemptRoot = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$TaskRoot = (Resolve-Path -LiteralPath $PackageRoot).Path
$TaskScripts = Join-Path $TaskRoot 'scripts'
$TaskSelection = Join-Path $TaskRoot 'ROOT_CHARACTERIZATION_SELECTION.json'
$TaskTranscriptOpen = $false
if ($TaskRoot.Length -gt 140) { throw 'Use an extraction root of at most 140 characters to retain native logs' }

function Invoke-LabPython {
    param([string[]]$ArgumentList, [string]$Log)
    $TaskOldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $TaskPython -B @ArgumentList 2>&1 | Tee-Object -FilePath $Log | Out-Host
        $TaskExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $TaskOldPreference }
    if ($TaskExitCode -ne 0) { throw ('LAB tool stopped; retain ' + $Log) }
}

function Read-LabSelection {
    $TaskRelease = Get-Content -LiteralPath $TaskSelection -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($TaskRelease.scope -ne 'ROOT_CHARACTERIZATION_RELEASE_SELECTION_NOT_IMAGE' -or
        $TaskRelease.release_status -ne 'ROOT_ISSUED_CHARACTERIZATION_ONLY' -or
        $TaskRelease.issued_by_root -isnot [bool] -or
        $TaskRelease.physical_IO_signoff -isnot [bool] -or $TaskRelease.network_video_permission -isnot [bool] -or
        $TaskRelease.issued_by_root -cne $true -or
        $TaskRelease.release_stage -ne 'BOARD_CHARACTERIZATION_ONLY' -or
        $TaskRelease.physical_IO_signoff -cne $false -or $TaskRelease.network_video_permission -cne $false -or
        $TaskRelease.image_manifest_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $TaskRelease.BIT_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $TaskRelease.source_routed_DCP_sha256 -ne '2eca552b8fb00e11615904c43c46b5e1e30f190cdb6ffa0187bb85e252da4d72') {
        throw 'DRAFT_UNISSUED or incompatible LAB root selection; no external action'
    }
    $TaskRelative = [string]$TaskRelease.image_manifest_file
    $TaskManifest = [IO.Path]::GetFullPath((Join-Path $TaskRoot $TaskRelative))
    if ([IO.Path]::IsPathRooted($TaskRelative) -or ($TaskRelative -split '[\\/]') -contains '..' -or
        !$TaskManifest.StartsWith(($TaskRoot.TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Candidate manifest path escapes extraction root'
    }
    return [pscustomobject]@{release=$TaskRelease;manifest=$TaskManifest;sha256=$TaskRelease.image_manifest_sha256}
}

try {
    if (!(Test-Path -LiteralPath $TaskPython -PathType Leaf)) { throw 'Use existing C Python; do not reinstall dependencies' }
    if ($Stage -in @('Preflight', 'Capture')) {
        if ($AttemptRoot) { throw 'Preflight/Capture creates a new attempt; an old AttemptRoot is forbidden' }
        $AttemptRoot = Join-Path $TaskRoot ('attempts\lab_' + $Stage.ToLowerInvariant() + '_' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ'))
        if (Test-Path -LiteralPath $AttemptRoot) { throw 'Fresh attempt unexpectedly exists' }
        New-Item -ItemType Directory -Path $AttemptRoot | Out-Null
    } else {
        if (!$AttemptRoot) { throw 'VerifyCapture/Pack requires the actual retained AttemptRoot' }
        $AttemptRoot = (Resolve-Path -LiteralPath $AttemptRoot).Path
        $TaskPrefix = [IO.Path]::GetFullPath((Join-Path $TaskRoot 'attempts')) + '\'
        if (!$AttemptRoot.StartsWith($TaskPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Attempt is outside this package attempts' }
    }
    $TaskTranscript = Join-Path $AttemptRoot ('operation_' + $Stage + '_' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ') + '.txt')
    Start-Transcript -LiteralPath $TaskTranscript | Out-Null
    $TaskTranscriptOpen = $true
    Write-Output ('EXACT_LAB_ATTEMPT_ROOT=' + $AttemptRoot)
    if ($Stage -eq 'Pack') {
        # Failed preflight/capture is packable; do not demand a successful release/report.
        $TaskCaptureReport = Join-Path $AttemptRoot 'capture\REPORT.json'
        if (Test-Path -LiteralPath $TaskCaptureReport) {
            $TaskSavedCapture = $null
            try { $TaskSavedCapture = Get-Content -LiteralPath $TaskCaptureReport -Raw -Encoding UTF8 | ConvertFrom-Json }
            catch {
                'Capture REPORT is incomplete/unreadable; retain original raw file. Operator must confirm no programmer/log writer remains.' |
                    Set-Content -LiteralPath (Join-Path $AttemptRoot 'PACK_INCOMPLETE_REPORT_NOTE.txt') -Encoding UTF8
            }
            if ($TaskSavedCapture -and $TaskSavedCapture.PSObject.Properties.Name -contains 'JTAG_process_running_at_capture_return' -and
                $TaskSavedCapture.PSObject.Properties.Name -contains 'JTAG_process_pid' -and
                $TaskSavedCapture.JTAG_process_running_at_capture_return -eq $true -and $TaskSavedCapture.JTAG_process_pid -and
                (Get-Process -Id $TaskSavedCapture.JTAG_process_pid -ErrorAction SilentlyContinue)) {
                throw 'Recorded programmer is still running; preserve growing logs and do not start a second programmer or pack yet'
            }
        }
        Stop-Transcript | Out-Null
        $TaskTranscriptOpen = $false
        $TaskZip = Join-Path (Split-Path -Parent $AttemptRoot) ((Split-Path -Leaf $AttemptRoot) + '_raw_' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ') + '.zip')
        & $TaskPython -B (Join-Path $TaskScripts 'zip_evidence.py') --evidence-root $AttemptRoot --out-zip $TaskZip
        if ($LASTEXITCODE -ne 0) { throw 'Pack failed; retain original folder and partial ZIP' }
    } else {
        $TaskIssued = Read-LabSelection
        if ($Stage -in @('Preflight', 'Capture')) {
            Copy-Item -LiteralPath $TaskSelection -Destination (Join-Path $AttemptRoot 'ROOT_CHARACTERIZATION_SELECTION.json')
            $TaskPreflight = Join-Path $AttemptRoot 'preflight'
            $TaskPreflightArgs = @((Join-Path $TaskScripts 'preflight_board_characterization.py'),
                '--manifest', $TaskIssued.manifest, '--issued-manifest-sha256', $TaskIssued.sha256, '--out-dir', $TaskPreflight)
            if ($Stage -eq 'Capture') { $TaskPreflightArgs += '--check-com3' }
            Invoke-LabPython -ArgumentList $TaskPreflightArgs -Log (Join-Path $AttemptRoot 'preflight_cli.log')
            $TaskPreflightResult = Get-Content -LiteralPath (Join-Path $TaskPreflight 'PREFLIGHT.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($TaskPreflightResult.status -ne 'LAB_LOCAL_FILES_READY_NOT_ELECTRICAL_OR_VIDEO_PASS' -or
                $TaskPreflightResult.identity.BIT_sha256 -ne $TaskIssued.release.BIT_sha256) {
                throw 'LAB file preflight or independently selected BIT identity differs'
            }
            if ($Stage -eq 'Capture') {
                if (!(Test-Path -LiteralPath $TaskVivado -PathType Leaf)) { throw 'Existing Vivado path absent' }
                Copy-Item -LiteralPath $TaskScripts -Destination (Join-Path $AttemptRoot 'issued_scripts') -Recurse
                $TaskCapture = Join-Path $AttemptRoot 'capture'
                Write-Output 'CLOSE_OTHER_COM3_MONITORS_AND_PROGRAMMERS_KEEP_S0_RELEASED_NO_NETWORK_TEST'
                Invoke-LabPython -ArgumentList @((Join-Path $TaskScripts 'capture_board_characterization.py'),
                    '--manifest', $TaskIssued.manifest, '--issued-manifest-sha256', $TaskIssued.sha256,
                    '--port', 'COM3', '--vivado-bat', $TaskVivado,
                    '--program-tcl', (Join-Path $TaskScripts 'program_board_characterization.tcl'),
                    '--out-dir', $TaskCapture) -Log (Join-Path $AttemptRoot 'capture_cli.log')
                Invoke-LabPython -ArgumentList @((Join-Path $TaskScripts 'verify_board_characterization_capture.py'),
                    '--manifest', $TaskIssued.manifest, '--issued-manifest-sha256', $TaskIssued.sha256,
                    '--report', (Join-Path $TaskCapture 'REPORT.json'),
                    '--out-file', (Join-Path $AttemptRoot 'INDEPENDENT_LAB_CAPTURE.json')) -Log (Join-Path $AttemptRoot 'capture_audit_cli.log')
                Write-Output 'LAB_STARTUP_IDENTITY_OBSERVED_ONLY_WAVEFORM_OPTIONAL_NOT_ELECTRICAL_OR_VIDEO_PASS'
            }
        } else {
            $TaskAuditName = 'INDEPENDENT_LAB_CAPTURE_' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ') + '.json'
            Invoke-LabPython -ArgumentList @((Join-Path $TaskScripts 'verify_board_characterization_capture.py'),
                '--manifest', $TaskIssued.manifest, '--issued-manifest-sha256', $TaskIssued.sha256,
                '--report', (Join-Path $AttemptRoot 'capture\REPORT.json'),
                '--out-file', (Join-Path $AttemptRoot $TaskAuditName)) -Log (Join-Path $AttemptRoot ($TaskAuditName + '.log'))
        }
    }
} catch {
    if ($AttemptRoot -and (Test-Path -LiteralPath $AttemptRoot -PathType Container)) {
        $_ | Out-String | Set-Content -LiteralPath (Join-Path $AttemptRoot ('FAILURE_' + $Stage + '_' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ') + '.txt')) -Encoding UTF8
        Write-Output ('STOPPED_KEEP_LAB_RAW_LOGS=' + $AttemptRoot)
    }
    throw
} finally {
    if ($TaskTranscriptOpen) { Stop-Transcript | Out-Null }
}
