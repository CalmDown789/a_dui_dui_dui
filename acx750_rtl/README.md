# ACX750 FSRCNN pure RTL workspace

This subtree contains member B's pure RTL work for the ACX750 board and
`XC7A200TFBG484-2` target.

The current checkpoint intentionally does not freeze the FSRCNN channel
counts, padding, fixed-point scales, phase order, weight layout, board I/O, or
clock frequency. Those values remain external contracts owned by members A
and C.

## Current independent baseline

- `rtl/compute/dot9_pipeline.v`: parameterized signed 3x3 dot product.
- `rtl/compute/channel_accumulator.v`: parameterized accumulation across input
  channels with bias sampled at the first contribution of each group.
- `rtl/compute/conv3x3_backend.v`: connects the two arithmetic blocks and
  pipelines bias metadata with the dot-product result.
- `rtl/compute/conv1x1_backend.v`: one-product-per-cycle channel accumulator
  for shrink/expand layers.
- `rtl/compute/dot25_pipeline.v` and `conv5x5_backend.v`: parameterized signed
  5x5 arithmetic path using 25 conservative one-multiply-per-DSP stages.
- `rtl/window/window3x3_bram.v` and `window5x5_bram.v`: rotating row-bank
  windows that infer three and five BRAMs respectively at 960x16-bit settings.
- `tb/conv3x3_backend_tb.v`: self-checking signed arithmetic smoke test with
  two input channels and two consecutive output groups.
- `scripts/generate_backend_vectors.py` and
  `tb/conv3x3_backend_random_tb.sv`: deterministic file-driven integer
  regression. The current test configuration uses 96 groups and three input
  channels, inserts idle cycles, exercises signed INT8 limits, and poisons
  later-channel bias values to check first-channel bias sampling.

This is a correctness micro-kernel, not a 30 fps architecture. Parallelism,
DSP packing, memory scheduling, and the full network top remain to be derived
after the model and board interfaces are frozen.

## Interface rule

All data ports are plain synchronous RTL signals. A future board wrapper may
map them to the protocol selected by member C. No AXI, video timing, DDR, or
frame-boundary semantics are assumed here.

## Reproduce the current arithmetic checks

From `F:\FPGA预选\10h冲刺` in PowerShell:

```powershell
.\acx750_rtl\scripts\run_backend_xsim.ps1
.\acx750_rtl\scripts\run_backend_random_xsim.ps1
```

The random script uses a fixed seed and creates vectors in an ASCII temporary
directory. Its 8-bit activation/weight widths and three-channel grouping are
verification settings, not a model-format decision.

Additional regressions:

```powershell
.\acx750_rtl\scripts\run_conv1x1_xsim.ps1
.\acx750_rtl\scripts\run_window3x3_bram_xsim.ps1
.\acx750_rtl\scripts\run_window5x5_bram_xsim.ps1
.\acx750_rtl\scripts\run_conv5x5_xsim.ps1
```

Run the complete simulation set with:

```powershell
.\acx750_rtl\scripts\run_all_xsim.ps1
```

The installed Vivado currently lacks `xc7a200tfbg484-2` device data. Reports
under `results/fallback_xc7z020_*` are same-generation DSP48E1 structural
checks only, not ACX750 timing or utilization sign-off.
