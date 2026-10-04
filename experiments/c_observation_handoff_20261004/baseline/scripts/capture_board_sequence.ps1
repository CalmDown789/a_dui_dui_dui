param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$fixture=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../audit/board_sequence_fixtures.json') | ConvertFrom-Json
$inputFiles=@($fixture.frames | ForEach-Object {$_.input_path})
$expectedFiles=@($fixture.frames | ForEach-Object {$_.expected_path})
& (Join-Path $PSScriptRoot 'capture_uart_frames.ps1') -PortName COM3 -InputFrame $inputFiles -ExpectedFrame $expectedFiles -OutputDirectory $OutputDirectory -ReadTimeoutMilliseconds 120000
