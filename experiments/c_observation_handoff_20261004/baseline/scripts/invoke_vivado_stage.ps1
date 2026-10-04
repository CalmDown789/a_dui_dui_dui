param([Parameter(Mandatory=$true)][ValidateSet('build100','build150','route150','gate100','gate150')][string]$Stage)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$config=Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'toolchain.json') | ConvertFrom-Json
$tool=Join-Path $config.vivado_root 'bin/vivado.bat'
& py (Join-Path $PSScriptRoot 'verify_frozen_inputs.py')
if($LASTEXITCODE -ne 0){throw 'Frozen input check failed; preserve evidence and diagnose before continuing'}
$toolVersion=(& $tool -version 2>&1 | Out-String)
if($toolVersion -notmatch 'vivado v2025\.2 '){throw 'Unexpected runtime version'}
$script=''
$tclArgs=@()
$required=@()
switch($Stage){
 'build100' {$script='synth_multiframe_board_100.tcl';$tclArgs=@('impl','acc36','ascii','ramdecomp')}
 'build150' {$script='synth_multiframe_board_150.tcl';$tclArgs=@('impl','acc36','ascii','ramdecomp')}
 'route150' {$script='route_multiframe_board_150.tcl';$required=@('runs/multiframe_board150_attempt01/placed_setup030.dcp')}
 'gate100' {$script='gated_bitgen.tcl';$required=@('runs/multiframe_board100_attempt01/postroute.dcp');$tclArgs=@((Join-Path $taskRoot $required[0]),'100',(Join-Path $taskRoot 'runs/multiframe_board100_bitgen01'))}
 'gate150' {$script='gated_bitgen.tcl';$required=@('runs/multiframe_board150_route_pressure01/postroute.dcp');$tclArgs=@((Join-Path $taskRoot $required[0]),'150',(Join-Path $taskRoot 'runs/multiframe_board150_bitgen01'))}
}
if($Stage -like 'build*'){
 foreach($rel in @('sim/bank16_v2025_2_probe01/result.json','sim/multiframe_attempt01/result.json','sim/fullframe_attempt01/result.json')){
  $p=Join-Path $taskRoot $rel
  if(-not(Test-Path -LiteralPath $p)){throw "New-tool simulation prerequisite missing: $rel"}
  $r=Get-Content -Raw -LiteralPath $p | ConvertFrom-Json
  if($r.status -ne 'PASS' -or $r.tool_version -ne '2025.2'){throw "New-tool simulation prerequisite failed: $rel"}
 }
}
foreach($rel in $required){if(-not(Test-Path -LiteralPath (Join-Path $taskRoot $rel))){throw "Required new-tool checkpoint missing: $rel"}}
$log=Join-Path $taskRoot "runs/${Stage}.log"
$journal=Join-Path $taskRoot "runs/${Stage}.jou"
$console=Join-Path $taskRoot "runs/${Stage}_console.txt"
$resultPath=Join-Path $taskRoot "audit/${Stage}_execution.json"
foreach($p in @($log,$journal,$console,$resultPath)){if(Test-Path -LiteralPath $p){throw "Attempt exists; retain evidence and create a new workspace for retry: $p"}}
$argsList=@('-mode','batch','-source',(Join-Path $PSScriptRoot $script),'-log',$log,'-journal',$journal)
if($tclArgs.Count){$argsList+=@('-tclargs')+$tclArgs}
$result=[ordered]@{stage=$Stage;status='RUNNING';tool=$tool;tool_version='2025.2';source_script=$script;arguments=$argsList;board_programming='NOT_PERFORMED'}
$result | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 -LiteralPath $resultPath
Push-Location $taskRoot
try{
 & $tool @argsList 2>&1 | Tee-Object -FilePath $console
 $code=$LASTEXITCODE
 $result['exit_code']=$code
 $result['status']=if($code -eq 0){'COMMAND_COMPLETED_NOT_BOARD_SIGNOFF'}else{'FAIL_TOOL_STAGE'}
 if($Stage -like 'gate*' -and $code -eq 0){
  $mhz=$Stage.Substring(4)
  $bit=Join-Path $taskRoot "runs/multiframe_board${mhz}_bitgen01/c_board_${mhz}mhz.bit"
  if(-not(Test-Path -LiteralPath $bit)){throw 'Expected gated bitstream missing'}
  $result['bit_sha256']=(Get-FileHash -Algorithm SHA256 -LiteralPath $bit).Hash.ToLowerInvariant()
 }
}catch{
 $result['status']='FAIL_TOOL_STAGE';$result['error']=$_.Exception.Message
 throw
}finally{
 Pop-Location
 $result | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 -LiteralPath $resultPath
}
if($code -ne 0){throw "Stage $Stage failed; retain raw logs and determine impact before retry"}
