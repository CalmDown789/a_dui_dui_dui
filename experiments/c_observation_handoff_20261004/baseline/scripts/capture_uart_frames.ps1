param(
    [string]$PortName,
    [string[]]$InputFrame,
    [string]$OutputDirectory,
    [string[]]$ExpectedFrame,
    [int]$BaudRate = 921600,
    [int]$Width = 960,
    [int]$Height = 540,
    [int]$ReadTimeoutMilliseconds = 600000,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
$script:Crc32Polynomial = [uint32]::Parse('EDB88320', [Globalization.NumberStyles]::HexNumber)

function Get-Crc32([byte[]]$Bytes) {
    [uint32]$crc = [uint32]::MaxValue
    foreach ($byteValue in $Bytes) {
        $crc = [uint32]($crc -bxor [uint32]$byteValue)
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($crc -band [uint32]1) -ne 0) {
                $crc = [uint32](($crc -shr 1) -bxor $script:Crc32Polynomial)
            } else {
                $crc = [uint32]($crc -shr 1)
            }
        }
    }
    return [uint32]($crc -bxor [uint32]::MaxValue)
}

function ConvertTo-UInt32LittleEndian([uint32]$Value) {
    $bytes = [byte[]]::new(4)
    $bytes[0] = [byte]($Value -band 255)
    $bytes[1] = [byte](($Value -shr 8) -band 255)
    $bytes[2] = [byte](($Value -shr 16) -band 255)
    $bytes[3] = [byte](($Value -shr 24) -band 255)
    return ,$bytes
}

function Get-Sha256([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Get-ByteMismatchCount([byte[]]$Actual, [byte[]]$Expected) {
    $mismatches = [Math]::Abs($Actual.Length - $Expected.Length)
    $limit = [Math]::Min($Actual.Length, $Expected.Length)
    for ($index = 0; $index -lt $limit; $index++) {
        if ($Actual[$index] -ne $Expected[$index]) { $mismatches++ }
    }
    return $mismatches
}

if ($SelfTest) {
    $selfTestBytes = [Text.Encoding]::ASCII.GetBytes('123456789')
    $actualCrc = '{0:x8}' -f (Get-Crc32 $selfTestBytes)
    $expectedCrc = 'cbf43926'
    if ($actualCrc -ne $expectedCrc) { throw "CRC32 self-test failed: $actualCrc != $expectedCrc" }
    $u32 = ConvertTo-UInt32LittleEndian ([uint32]::Parse('12345678', [Globalization.NumberStyles]::HexNumber))
    if (($u32 -join ',') -ne '120,86,52,18') { throw "Little-endian self-test failed: $($u32 -join ',')" }
    [byte[]]$testHeaderFields = @(0,0,0,0,0x40,0x14,0,0,0xa5,0x63,0x3e,0x27)
    $testHeaderCrc = '{0:x8}' -f (Get-Crc32 $testHeaderFields)
    if ($testHeaderCrc -ne '15328e07') { throw "Protocol header CRC self-test failed: $testHeaderCrc" }
    Write-Output 'PASS CRC32 IEEE vector, uint32 little-endian encoding, and SRTP header CRC fixture.'
    exit 0
}

if ([string]::IsNullOrWhiteSpace($PortName)) { throw 'Specify -PortName (for example COM3, after checking the current device list).' }
if (-not $InputFrame -or $InputFrame.Count -lt 1) { throw 'Specify one or more -InputFrame raw Y files.' }
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { throw 'Specify -OutputDirectory.' }
if ($ExpectedFrame -and $ExpectedFrame.Count -ne $InputFrame.Count) { throw 'ExpectedFrame count must equal InputFrame count.' }
if ($BaudRate -lt 1 -or $Width -lt 1 -or $Height -lt 1) { throw 'BaudRate, Width, and Height must be positive.' }
if ($InputFrame.Count -gt 4294967295) { throw 'Frame count exceeds the protocol frame_id range.' }

$inputBytesRequired = [long]$Width * [long]$Height
$outputBytesRequired = [long]($Width * 2) * [long]($Height * 2)
if ($inputBytesRequired -gt 2147483647 -or $outputBytesRequired -gt 2147483647) { throw 'Frame is too large for this PowerShell capture buffer.' }
$inputBytesRequired = [int]$inputBytesRequired
$outputBytesRequired = [int]$outputBytesRequired
if(Test-Path -LiteralPath $OutputDirectory) {throw 'Capture directory exists; evidence preserved'}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$outDir = (Resolve-Path -LiteralPath $OutputDirectory).Path
$inputPaths = @()
$expectedPaths = @()
for ($index = 0; $index -lt $InputFrame.Count; $index++) {
    $inputPath = (Resolve-Path -LiteralPath $InputFrame[$index]).Path
    if ((Get-Item -LiteralPath $inputPath).Length -ne $inputBytesRequired) {
        throw "Frame $index input size mismatch; expected $inputBytesRequired bytes ($Width x $Height)."
    }
    $inputPaths += $inputPath
    if ($ExpectedFrame) {
        $expectedPath = (Resolve-Path -LiteralPath $ExpectedFrame[$index]).Path
        if ((Get-Item -LiteralPath $expectedPath).Length -ne $outputBytesRequired) {
            throw "Frame $index Golden size mismatch; expected $outputBytesRequired bytes ($($Width*2) x $($Height*2))."
        }
        $expectedPaths += $expectedPath
    }
    $targetPath = Join-Path $outDir ("frame_{0:d4}_y.bin" -f $index)
    if (Test-Path -LiteralPath $targetPath) { throw "Output already exists, preserving prior capture: $targetPath" }
}
if (Test-Path -LiteralPath (Join-Path $outDir 'session.json')) {
    throw "session.json already exists; choose a new output directory to preserve the prior run."
}

$session = [ordered]@{
    protocol = 'SRTP stop-and-wait v1'
    status = 'RUNNING'
    port = $PortName
    nominal_baud = $BaudRate
    uart_format = '8N1, LSB first'
    geometry_in = "${Width}x${Height} uint8 Y row-major"
    geometry_out = "$($Width*2)x$($Height*2) uint8 Y row-major"
    reset_requirement = 'The FPGA loader expected_frame_id must be 0. Reset the board once before this script; the host cannot query or assert the board reset.'
    frame_count = $InputFrame.Count
    frames = @()
}
$port = $null
$currentOut = $null
$received = 0
$frameOutputPath = $null
$allCompared = [bool]$ExpectedFrame
$allExact = $true
$sessionTimer = [Diagnostics.Stopwatch]::StartNew()

try {
    Add-Type -AssemblyName System.IO.Ports
    $port = [IO.Ports.SerialPort]::new($PortName, $BaudRate, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $port.Handshake = [IO.Ports.Handshake]::None
    $port.ReadTimeout = $ReadTimeoutMilliseconds
    $port.WriteTimeout = 60000
    $port.DtrEnable = $false
    $port.RtsEnable = $false
    $port.ReadBufferSize = 65536
    $port.WriteBufferSize = 65536
    $port.Open()
    $port.DiscardInBuffer()
    $port.DiscardOutBuffer()

    for ($frameId = 0; $frameId -lt $InputFrame.Count; $frameId++) {
        $inputPath = $inputPaths[$frameId]
        $input = [IO.File]::ReadAllBytes($inputPath)
        $payloadCrc = Get-Crc32 $input
        $header = [byte[]]::new(16)
        $header[0] = 0x53; $header[1] = 0x52; $header[2] = 0x54; $header[3] = 0x50 # SRTP
        [Array]::Copy((ConvertTo-UInt32LittleEndian ([uint32]$frameId)), 0, $header, 4, 4)
        [Array]::Copy((ConvertTo-UInt32LittleEndian ([uint32]$input.Length)), 0, $header, 8, 4)
        [Array]::Copy((ConvertTo-UInt32LittleEndian ([uint32]$payloadCrc)), 0, $header, 12, 4)
        $headerFields = [byte[]]::new(12)
        [Array]::Copy($header, 4, $headerFields, 0, 12)
        $headerCrc = Get-Crc32 $headerFields
        $headerCrcBytes = ConvertTo-UInt32LittleEndian ([uint32]$headerCrc)
        $packetHeader = [byte[]]::new(20)
        [Array]::Copy($header, 0, $packetHeader, 0, 16)
        [Array]::Copy($headerCrcBytes, 0, $packetHeader, 16, 4)

        Write-Output ("SEND frame_id={0} bytes={1} input_crc32={2:x8} header_crc32={3:x8}" -f $frameId,$input.Length,$payloadCrc,$headerCrc)
        $frameTimer = [Diagnostics.Stopwatch]::StartNew()
        $writeTimer = [Diagnostics.Stopwatch]::StartNew()
        $port.Write($packetHeader, 0, $packetHeader.Length)
        $chunkBytes = 4096
        for ($offset = 0; $offset -lt $input.Length; $offset += $chunkBytes) {
            $count = [Math]::Min($chunkBytes, $input.Length - $offset)
            $port.Write($input, $offset, $count)
        }
        $writeTimer.Stop()
        $estimatedInputWireSeconds = (($packetHeader.Length + $input.Length) * 10.0) / $BaudRate

        $currentOut = [byte[]]::new($outputBytesRequired)
        $received = 0
        $frameOutputPath = Join-Path $outDir ("frame_{0:d4}_y.bin" -f $frameId)
        $firstByteTimer = [Diagnostics.Stopwatch]::StartNew()
        $firstByteSeconds = $null
        $outputTimer = [Diagnostics.Stopwatch]::StartNew()
        while ($received -lt $currentOut.Length) {
            $request = [Math]::Min(32768, $currentOut.Length - $received)
            $count = $port.Read($currentOut, $received, $request)
            if ($count -le 0) { continue }
            if ($null -eq $firstByteSeconds) {
                $firstByteTimer.Stop()
                $firstByteSeconds = $firstByteTimer.Elapsed.TotalSeconds
            }
            $received += $count
        }
        $outputTimer.Stop()
        $frameTimer.Stop()
        [IO.File]::WriteAllBytes($frameOutputPath, $currentOut)

        $frameRecord = [ordered]@{
            frame_id = $frameId
            input_path = $inputPath
            input_bytes = $input.Length
            input_sha256 = Get-Sha256 $input
            input_crc32 = ('{0:x8}' -f $payloadCrc)
            output_path = $frameOutputPath
            output_bytes = $received
            output_sha256 = Get-Sha256 $currentOut
            expected_path = $null
            expected_sha256 = $null
            mismatch_bytes = $null
            bit_exact = $null
            host_write_call_seconds = [Math]::Round($writeTimer.Elapsed.TotalSeconds, 6)
            estimated_input_wire_seconds_at_nominal_baud = [Math]::Round($estimatedInputWireSeconds, 6)
            first_output_byte_latency_after_host_write_seconds = [Math]::Round($firstByteSeconds, 6)
            output_receive_seconds = [Math]::Round($outputTimer.Elapsed.TotalSeconds, 6)
            host_frame_elapsed_seconds = [Math]::Round($frameTimer.Elapsed.TotalSeconds, 6)
        }

        if ($ExpectedFrame) {
            $expectedPath = $expectedPaths[$frameId]
            $expected = [IO.File]::ReadAllBytes($expectedPath)
            $mismatchCount = Get-ByteMismatchCount $currentOut $expected
            $frameRecord.expected_path = $expectedPath
            $frameRecord.expected_sha256 = Get-Sha256 $expected
            $frameRecord.mismatch_bytes = $mismatchCount
            $frameRecord.bit_exact = ($mismatchCount -eq 0)
            if ($mismatchCount -ne 0) { $allExact = $false }
        } else {
            $allExact = $false
        }
        $session.frames += [pscustomobject]$frameRecord
        $session | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outDir 'session.json') -Encoding UTF8
        Write-Output ("RECEIVED frame_id={0} bytes={1} sha256={2}" -f $frameId,$received,$frameRecord.output_sha256)
        if ($frameRecord.bit_exact -eq $true) { Write-Output "BIT_EXACT frame_id=$frameId" }
        elseif ($frameRecord.bit_exact -eq $false) { Write-Output "MISMATCH frame_id=$frameId count=$($frameRecord.mismatch_bytes)" }

        if ($frameId -lt ($InputFrame.Count - 1)) {
            # Let the FPGA leave its final UART stop bit and return to the frame-ID seek state.
            Start-Sleep -Milliseconds 20
        }
    }

    $sessionTimer.Stop()
    if ($allCompared) { $session.status = if ($allExact) { 'PASS_BIT_EXACT' } else { 'FAIL_GOLDEN_MISMATCH' } }
    else { $session.status = 'CAPTURED_UNVERIFIED' }
    $session.total_host_elapsed_seconds = [Math]::Round($sessionTimer.Elapsed.TotalSeconds, 6)
    $session | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outDir 'session.json') -Encoding UTF8
    Write-Output "SESSION_STATUS=$($session.status)"
}
catch {
    if ($null -ne $currentOut -and $received -gt 0) {
        $partial = [byte[]]::new($received)
        [Array]::Copy($currentOut, 0, $partial, 0, $received)
        $partialPath = Join-Path $outDir ("frame_{0:d4}_partial_{1:d8}_bytes.bin" -f $session.frames.Count,$received)
        [IO.File]::WriteAllBytes($partialPath, $partial)
        $session.partial_capture = @{path=$partialPath; bytes=$received; sha256=(Get-Sha256 $partial)}
    }
    $sessionTimer.Stop()
    $session.status = 'FAILED'
    $session.error = $_.Exception.Message
    $session | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outDir 'session.json') -Encoding UTF8
    throw
}
finally {
    if ($port -and $port.IsOpen) { $port.Close() }
    if ($port) { $port.Dispose() }
}

if ($session.status -eq 'FAIL_GOLDEN_MISMATCH') { throw 'One or more frames differ from the supplied Golden files; see session.json and captured frame files.' }
if ($session.status -eq 'CAPTURED_UNVERIFIED') { Write-Warning 'Output was captured, but not every frame had an expected Golden for exact comparison.' }
