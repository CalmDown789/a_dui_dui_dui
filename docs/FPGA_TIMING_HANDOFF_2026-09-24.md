# FSRCNN FPGA timing handoff — 2026-09-24

This handoff records the work completed on the local Vivado 2022.2 machine and moves the next synthesis/implementation runs to another Vivado-equipped runner. **Do not start more Vivado, XSim, or implementation runs on C's machine.** The measured source overlay, marker fixtures, Tcl command, and reports are committed alongside this document.

## Results

| Candidate | Verification completed | Result at 200 MHz | Status |
|---|---|---|---|
| L5 split-memory overlay, 48-bit accumulator | Real B+C `tb_c_b_smoke` PASS; synthesis and full route completed | Post-route WNS/TNS `-0.738 ns / -3,137.469 ns`; RAMB36/RAMB18 `174/8`; DSP48E1 `394`; LUT `31,313`; FF `50,025`; LUTRAM `5,867`; implementation peak memory `4,201 MB` | Best completed route in this experimental source family; still fails timing |
| Same overlay with 36-bit phase accumulator | Boundary/random 48-bit-reference probe PASS; C+B smoke PASS; synthesis completed | LUT `29,644`; FF `48,358`; RAMB36/RAMB18 `174/8`; DSP48E1 `394`; synth WNS/TNS `-0.855 ns / -409.801 ns` | Not placed or routed; do not treat synth slack as final timing |

The 48-bit split-memory run synthesized in about 3:47 with peak Vivado memory about 3.19 GB; `route_design` took 10:59 and reported peak memory about 4.20 GB. The full synth/opt/place/phys-opt/route flow took about 21 minutes. These values are from the local Vivado logs. They show this run completed with ordinary single-digit-GB memory use; they do not imply every machine or candidate will use the same amount. Two sequential reruns should budget roughly 40–50 minutes on a similar host, plus verification and review.

Against the **matching temporary bank16 baseline** (not against the current official branch in isolation), the split-memory run improved WNS from `-1.097 ns` to `-0.738 ns` (+359 ps) and TNS from `-8,358.673 ns` to `-3,137.469 ns`. Post-route LUT increased from `31,034` to `31,313`; FF increased from `49,862` to `50,025`. The experiment's worst path moved to L2 phase accumulation and bias saturation: `sum_stage_reg[3][5]` to `out_data_reg[97]`, 5.607 ns data delay with 12 CARRY4 stages.

The DRC report lists 1,144 violations, all warnings (including DSP pipeline advice and one unspecified I/O standard / unconstrained logical port); route status lists 78,989 of 78,989 routable nets fully routed and zero routing errors. This is not a clean board-ready DRC/timing result.

## Important comparison limit

The completed route used a combined experimental overlay, not only the new FIFO. It also uses the banked C input ROM, C request/stream changes, C core changes, and the B issue/layer/network-core and MAC/requantization variants captured in `experiments/l5_splitmem_20260924/`. The +359 ps comparison isolates the FIFO split only relative to the matching bank16 trial. It must not be reported as a +359 ps improvement over the current official `c-side-latest` RTL, nor as a closed 200 MHz design.

The 36-bit accumulator candidate is based on the same combined overlay and split FIFO. It narrows the sum of eight signed 32-bit partials plus one signed 32-bit bias; that range fits in signed 36 bits. Its probe checks extrema, clipping boundaries, cancellation, and 256 randomized cases against a 48-bit reference. It still needs full place-and-route, followed by the project's bit-exact verification before any RTL promotion.

The `acc36cs` carry-select experiment was neither simulated nor synthesized. It is deliberately not included in the handoff package.

## Next run for another member

The repository currently has no configured Vivado GitHub Actions runner. A GitHub collaborator can review and commit the results, but must use a separate Windows machine with Vivado 2022.2 and a valid `xc7a200tfbg484-2` license to run the Tcl below. The source package and exact command are documented in [`experiments/l5_splitmem_20260924/README.md`](../experiments/l5_splitmem_20260924/README.md).

1. Reproduce the completed 48-bit route using `synth_bc_trial.tcl -tclargs impl` and compare resource, DRC, route status, critical path, and peak memory with the attached report.
2. Run the 36-bit candidate with `-tclargs impl acc36`. It must first pass the self-check; then compare post-route WNS/TNS and the new critical path against the 48-bit run.
3. If the 36-bit route improves timing, rerun the full real-B functional/bit-exact regression with that exact source overlay. Do not copy its accumulator into formal RTL before this gate passes.
4. Commit raw Vivado logs, new reports, exact tool/license/part information, and the comparison to the same experiment folder. Keep these trial results separate from official acceptance status.

The baseline `c-side-latest` branch remains the formal RTL. The board is still required for image/UART/HDMI acceptance; GitHub access alone cannot substitute for a physical ACX750 board. Neither candidate has produced a bitstream or passed board testing.

## Reports

- [`l5splitmem_trial_20260924`](../report/bc_real_synth/l5splitmem_trial_20260924/): complete synthesis and post-route report set, including utilization, timing, RAM mapping, DRC, and route status.
- [`acc36_trial_20260924`](../report/bc_real_synth/acc36_trial_20260924/): synthesis reports and the recorded real-B smoke result. The separate accumulator testbench is in the experiment package.
- [`vivado_run_metrics_excerpt.txt`](../report/bc_real_synth/l5splitmem_trial_20260924/vivado_run_metrics_excerpt.txt): sanitized synthesis/implementation runtime and peak-memory lines.
- [`CURRENT_PROJECT_STATUS.md`](CURRENT_PROJECT_STATUS.md): project-level status and board-test boundary.
