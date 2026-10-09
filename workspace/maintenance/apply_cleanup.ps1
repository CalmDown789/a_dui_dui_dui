$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath 'C:\Users\Administrator\WorkBuddy\srtp').Path
$taskPlan = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $taskRoot 'docs\CLEANUP_PLAN.json') | ConvertFrom-Json
if ($taskPlan.workspace -ne $taskRoot) { throw 'Workspace differs from reviewed plan' }
if ((Get-FileHash -LiteralPath $taskPlan.backup -Algorithm SHA256).Hash.ToLower() -ne $taskPlan.backup_sha256) { throw 'Backup hash mismatch' }
if ((Get-FileHash -LiteralPath $taskPlan.diagnostic_backup.path -Algorithm SHA256).Hash.ToLower() -ne $taskPlan.diagnostic_backup.sha256) { throw 'Diagnostic backup hash mismatch' }

# Validate the entire plan before the first deletion.
foreach ($taskRow in @($taskPlan.files) + @($taskPlan.directories)) {
    $taskPath = [IO.Path]::GetFullPath($taskRow.path)
    if (-not $taskPath.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Outside workspace: $taskPath" }
    if ($taskPath -match '\\.git(?:\\|$)' -or $taskPath -match '\\output\\C_TO_B_LATENCY_HANDOFF') { throw "Protected path: $taskPath" }
    if (-not (Test-Path -LiteralPath $taskPath)) { throw "Plan target missing: $taskPath" }
    $taskItem = Get-Item -Force -LiteralPath $taskPath
    if ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked target: $taskPath" }
}
foreach ($taskRow in $taskPlan.files) {
    if ((Get-FileHash -LiteralPath $taskRow.path -Algorithm SHA256).Hash.ToLower() -ne $taskRow.sha256) { throw "Changed after backup: $($taskRow.path)" }
}
foreach ($taskRow in $taskPlan.directories) {
    $taskLinked = Get-ChildItem -LiteralPath $taskRow.path -Recurse -Force -Attributes ReparsePoint
    if ($taskLinked) { throw "Linked content: $($taskRow.path)" }
}
foreach ($taskRow in $taskPlan.files) { Remove-Item -LiteralPath $taskRow.path -Force }
foreach ($taskRow in $taskPlan.directories) { Remove-Item -LiteralPath $taskRow.path -Recurse -Force }
[pscustomobject]@{Status='CLEANUP_APPLIED';Files=$taskPlan.delete_file_count;Bytes=$taskPlan.delete_bytes} | ConvertTo-Json
