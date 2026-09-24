# 2026-09-24 L5 FIFO split timing handoff

This folder freezes the source overlay used by the local Vivado 2022.2 timing trials. It does not replace the project RTL under `rtl/`; use the Tcl script here to select the overlay explicitly.

## Contents

- `rtl/c/` holds the banked input ROM, the registered C request path, and the C core used in the measured bank16 candidate.
- `rtl/b/elastic_fifo.sv` is the L5 wide-FIFO read-pointer and storage-slice experiment.
- `rtl/b/mac_issue_stage.sv`, `rtl/b/fsrcnn_stream_layer.sv`, and `rtl/b/fsrcnn_network_core.sv` freeze the B integration variants used by the matching bank16 baseline. The other B closure files and normal C RTL come from the repository checkout.
- The B patch files `phase_mac_pipeline.sv` and `prelu_requantize.sv` are also the exact versions used by the route; the 48-bit `phase_accumulator.sv` and shared postprocess file match the formal C-side patches.
- `rtl/b/phase_accumulator.sv` is the 48-bit reference used by the completed route.
- `rtl/b/phase_accumulator_36.sv` is the later 36-bit width-reduction candidate. It passed a targeted saturation probe, C+B smoke simulation, and synthesis, but has not been placed or routed.
- `fixtures/rom_bank_*.mem` are synthetic marker banks from the measured topology benchmark. They are not the A image, an acceptance image, or production input data. Their hashes are listed in `fixtures/SHA256SUMS.txt`.
- `tb/` contains the C+B smoke bench and the 36-bit accumulator reference bench.
- `synth_bc_trial.tcl` runs synthesis and optionally place-and-route for either overlay.
- `SOURCE_SHA256SUMS.txt` records the copied RTL overlay hashes.

The raw Vivado reports are in [`report/bc_real_synth/l5splitmem_trial_20260924`](../../report/bc_real_synth/l5splitmem_trial_20260924) and [`report/bc_real_synth/acc36_trial_20260924`](../../report/bc_real_synth/acc36_trial_20260924).

## Reproduce on a Vivado machine

Use Vivado 2022.2 with a license for `xc7a200tfbg484-2`, from the repository root. The 19 packed B parameter ROMs are tracked under `rom/member_a_d16_s8_m1_c16/`. Generate the ignored input pattern first because the Tcl stages it:

```powershell
python scripts/gen_input_mem.py pattern-full
vivado -mode batch -source experiments/l5_splitmem_20260924/synth_bc_trial.tcl -tclargs impl
vivado -mode batch -source experiments/l5_splitmem_20260924/synth_bc_trial.tcl -tclargs impl acc36
```

The first command routes the measured 48-bit L5-split overlay. The second routes the same overlay with the un-routed 36-bit accumulator candidate. Omit `impl` to run synthesis only; pass `acc36` alone to synthesize the width-reduced version. Reports and staged files are written under the ignored `_synth_bc/<variant>/` tree.

Run each variant separately. Confirm the Tcl self-check reports `b_core_real` present, `b_core_stub=0`, five stream layers, and the expected FIFO / PixelShuffle hierarchy before using any numbers. Preserve the new Vivado logs and reports with the rerun commit.

## Evidence boundary

The completed route's `tb_c_b_smoke` PASS is a smoke/protocol result, not an image Golden comparison. The synthetic marker banks preserve ROM topology for implementation; they do not prove output pixels, image quality, board behavior, or frame rate. No bitstream or board test was produced. The 200 MHz target still fails timing.
