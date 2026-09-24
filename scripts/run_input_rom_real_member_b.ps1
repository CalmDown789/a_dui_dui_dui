# 成员B工作：在 Vivado 2025.2 XSim 中核对真实 A 输入的 bank16 ROM。
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$vivadoBin = 'F:\Xilinx\2025.2\Vivado\bin'
$work = Join-Path $root 'member_b_evidence\rom_tb'
$banks = Join-Path $root 'member_b_evidence\real_banks'
$source = Join-Path $root 'ref\a_full_integer_golden\input_rom_2p19_u8.mem'
if (-not (Test-Path -LiteralPath $source)) { throw "Missing frozen A ROM: $source" }
$bankFiles = @(Get-ChildItem -LiteralPath $banks -Filter 'rom_bank_*.mem' -File)
if ($bankFiles.Count -ne 16) { throw "Expected 16 banks, got $($bankFiles.Count)" }
New-Item -ItemType Directory -Force -Path $work | Out-Null
Copy-Item -LiteralPath $source -Destination (Join-Path $work 'input_rom_2p19_u8.mem') -Force
foreach ($f in $bankFiles) { Copy-Item -LiteralPath $f.FullName -Destination $work -Force }
Push-Location $work
try {
    & (Join-Path $vivadoBin 'xvlog.bat') -sv --include (Join-Path $root 'rtl') `
        (Join-Path $root 'experiments\l5_splitmem_20260924\rtl\c\input_rom.v') `
        (Join-Path $root 'tb\tb_input_rom_real_member_b.sv') *> 'xvlog_console.log'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed; see xvlog_console.log' }
    & (Join-Path $vivadoBin 'xelab.bat') work.tb_input_rom_real_member_b -O0 `
        -s tb_input_rom_real_member_b *> 'xelab_console.log'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed; see xelab_console.log' }
    & (Join-Path $vivadoBin 'xsim.bat') tb_input_rom_real_member_b -runall *> 'xsim_console.log'
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed; see xsim_console.log' }
    $log = Get-Content -LiteralPath 'xsim_console.log' -Raw
    if ($log -notmatch 'MEMBER_B_REAL_BANKED_ROM_PASS reads=137') {
        throw 'ROM scoreboard did not pass; see xsim_console.log'
    }
    Write-Output 'MEMBER_B_REAL_BANKED_ROM_PASS reads=137 banks=16 depth=32768'
} finally {
    Pop-Location
}
