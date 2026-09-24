# 150 MHz implementation status

Date: 2026-09-24

## Status

**Implementation completed; timing is not met. The 150 MHz bitstream was generated but was not programmed onto the board, and no 150 MHz UART/Golden comparison was run.** Board programming and capture were stopped at the user's request so placement/routing optimization can continue elsewhere.

The 100 MHz board test passed and its report is already on this branch: [100 MHz board test report](../c_board_100mhz/BOARD_TEST_REPORT_2026-09-24.md).

## Build basis

- FPGA: ACX750, xc7a200tfbg484-2
- Tool: Vivado 2022.2
- RTL baseline: commit 6218c5eb09a09e7a7d63c12ae163f7dd29baf0f8
- C clock configuration: 50 MHz input, MMCM CLKOUT0_DIVIDE_F=8.0, C_CLK_HZ=150000000
- Full board XDC was used, including UART TX on M21.
- Functional RTL was not changed for this run; the implementation used the recommended phys_opt_design AggressiveFanoutOpt and route_design Explore directives.
- Real B implementation self-check passed: b_core_real=1, b_core_stub=0, five stream layers present.

## Timing and routing

| Metric | Synthesis | Post-route |
| --- | ---: | ---: |
| WNS | +0.495 ns | -0.210 ns |
| TNS | 0.000 ns | -36.940 ns |
| WHS | +0.029 ns | +0.026 ns |
| THS | 0.000 ns | 0.000 ns |

Post-route setup timing fails at 729 of 162,932 endpoints. The worst path is from l3/mac/issue/out_window_reg[527] to l3/mac/mac/out_lane[7].mult_lane[4].sums_q_reg[0][7][4]/A[20]. Its data path is 3.453 ns, including 2.737 ns of routing delay and two logic levels. The timing summary also reports nine output ports without output delay constraints; verify constraint coverage when continuing optimization.

Routing completed with 71,755 of 71,755 routable nets fully routed and zero routing errors. Bitstream generation completed successfully despite the setup timing violation.

## Resources and DRC

- Post-route: RAMB36/FIFO 230, RAMB18 8, DSP48E1 394, Slice LUTs 30,417, Slice Registers 42,197, MMCM 1, BUFG 1.
- DRC: 0 errors, 1,098 warnings. Warnings are primarily DSP pipeline advisories and RAM block asynchronous-control checks.
- The bitstream was generated locally at report/c_board_150mhz/c_board_150MHz.bit; size 9,730,760 bytes; SHA-256 55e9e219bee3838f6cf932b6ede6e4d571d9fc862c78abc8aaf bcd60a6afd8e4 (remove the space before sharing).

## Next handoff

Continue place/route optimization against the 150 MHz timing constraint. Re-run the full post-route timing checks; do not treat the current bitstream as timing-closed. After optimization, program the board and capture the full UART frame on COM3, then compare against the Golden output before claiming 150 MHz functional pass.