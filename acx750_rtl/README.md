# ACX750 FSRCNN pure RTL workspace

## 2026-09-23 member B streaming-control increment

Team member B added `rtl/stream/` with parameterized SAME-padding, K-1
row-bank arrays, eight-phase MAC scheduling and INT32 assembly, four interlayer
FIFOs, time-shared per-channel PReLU/Q31, and two PixelShuffle row banks. The
`fsrcnn_network_mem_top.sv` port list follows C-B v0.2. XSim compares all five
streaming layers and the final Y output at both 6x5 and 96x54 against
independently computed values from member A's audited integer assets. The
96x54 run checks 269,568 layer values and 20,736 output bytes. This is a
functional baseline; the 370-DSP, 271-RAMB36, 200-MHz and 30-fps budgets
still need architectural optimization and target synthesis/implementation.
See `docs/stream_integration_status.md`.

The later member-B increment adds `rtl/stream/b_core_real.sv` for C's named
interface, a stallable balanced MAC tree, and synchronous PixelShuffle bank
reads. The C-side ZIP integration check is `scripts/run_member_b_c_core_real_xsim.ps1`;
it copies C files into a temporary test directory and leaves C's source intact.
See `docs/member_b_backpressure_contract.md` for B-ARCH-10 capacity and stall
details. No target-device utilization or timing result is implied by XSim.

**Owner: team member B.** This subtree is member B's pure-RTL implementation,
integer bit-exact verification, and synthesis-analysis work for the ACX750
board and `XC7A200TFBG484-2` target. Member A owns the model/quantized tensors;
member C owns the board project, constraints, and on-board integration.

The model topology, convolution padding, activation locations, numeric types,
serialization, rounding, saturation, and PixelShuffle phase order were
confirmed by member A and independently audited on 2026-09-22. Board I/O and
clock frequency remain external contracts owned by member C.

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
- `rtl/compute/dot25_u8s8_pipeline.v` and `conv5x5_u8s8_backend.v`: dedicated
  first-layer path for uint8 input times signed INT8 weights.
- `rtl/postprocess/pixel_shuffle2x_coord_map.v`: verified four-phase coordinate
  convention without assuming the eventual board memory/streaming transport.
- `rtl/window/window3x3_bram.v` and `window5x5_bram.v`: rotating row-bank
  windows that infer three and five BRAMs respectively at 960x16-bit settings.
- `tb/conv3x3_backend_tb.v`: self-checking signed arithmetic smoke test with
  two input channels and two consecutive output groups.
- `scripts/generate_backend_vectors.py` and
  `tb/conv3x3_backend_random_tb.sv`: deterministic file-driven integer
  regression. The current test configuration uses 96 groups and three input
  channels, inserts idle cycles, exercises signed INT8 limits, and poisons
  later-channel bias values to check first-channel bias sampling.

The primitives above remain useful independent checks. The newer five-engine
network top is described in `docs/stream_integration_status.md`; its target
resource mapping, timing and frame rate remain open.

## Member A delivery audit

Member B's independent NumPy audit verified 163 delivery-file digests, all 14
weight/bias/PReLU format groups across `.npy/.bin/.mem/.coe`, and all stages of
the zero, impulse, ramp, and random integer references. Representative real
member-A tensors then passed XSim through every arithmetic layer:

```text
ACX750_MEMBER_A_POSTPROCESS_BIT_EXACT_PASS i16=96 u8=8
ACX750_MAPPING0_MEMBER_A_BIT_EXACT_PASS groups=40 contributions=320
ACX750_FEATURE_SUBPIXEL_MEMBER_A_BIT_EXACT_PASS feature=80 subpixel=20
ACX750_CONV1X1_MEMBER_A_BIT_EXACT_PASS shrink=40 expand=80
```

See `docs/member_a_delivery_audit.md`. These checks establish representative
layer arithmetic equivalence, not full-frame RTL scheduling or board speed.

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
.\acx750_rtl\scripts\run_conv5x5_u8s8_xsim.ps1
.\acx750_rtl\scripts\run_pixel_shuffle_map_xsim.ps1
```

Run the complete simulation set with:

```powershell
.\acx750_rtl\scripts\run_all_xsim.ps1
```

The installed Vivado currently lacks `xc7a200tfbg484-2` device data. Reports
under `results/fallback_xc7z020_*` are same-generation DSP48E1 structural
checks only, not ACX750 timing or utilization sign-off.
