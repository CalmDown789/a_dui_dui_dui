# Verification status

## 2026-09-23 member B streaming-control checks

Full-network XSim markers after those control checks:

```text
ACX750_MEMBER_B_FIVE_LAYER_CONTINUOUS_BIT_EXACT_PASS size=96x54 values=269568
ACX750_MEMBER_B_FULL_STREAM_BIT_EXACT_PASS size=96x54 layer_values=269568 output_bytes=20736
ACX750_MEMBER_B_NETWORK_CORE_BIT_EXACT_PASS size=96x54 output_bytes=20736
ACX750_MEMBER_B_ROM_TOP_BIT_EXACT_PASS size=96x54 output_bytes=20736
```

The same complete flow passed at 6x5. Each layer uses A's actual exported
integers; four 32-token FIFOs carry **RTL-produced** HWC activations between
concurrently active layers. PixelShuffle produces row-major uint8 Y. The
top-level test checks input and output handshakes, stalls, sideband stability,
`start` while busy, `busy`, and `done`. This is a functional simulation result,
not synthesis or board evidence.

Observed XSim markers:

```text
ACX750_MEMBER_B_STREAM_CONTROL_PASS pad=0/1/2 fifo=3
ACX750_MEMBER_B_PADDED_WINDOW_PASS k3/k5 size=6x5
ACX750_MEMBER_B_EIGHT_PHASE_PASS windows=13 transfers=104
ACX750_MEMBER_B_WINDOW_STREAM_PASS k3/k5 size=6x5 frames=2 depth=3
ACX750_MEMBER_B_LANE_MAP_PASS total_mac_per_pixel=2832 lanes=354
ACX750_MEMBER_B_PHASE_ACCUM_PASS layers=5 frames=2
```

These establish padding, ordering, backpressure, two-frame window reset,
eight-phase OIHW address coverage, and eight-phase INT32 result assembly.
They do not establish full-network RTL
bit-exact output, 354 instantiated MACs, or a target-device timing result.
See `stream_integration_status.md`.

## 2026-09-21 arithmetic backend smoke test

Vivado XSim 2025.2 compiled, elaborated, and simulated:

- `dot9_pipeline.v`
- `channel_accumulator.v`
- `conv3x3_backend.v`
- `conv3x3_backend_tb.v`

Observed terminal marker:

```text
ACX750_CONV3X3_BACKEND_TEST_PASS
```

The test covers two input channels, signed positive and negative products,
bias addition, two consecutive output groups, and bias alignment through the
dot-product pipeline.

Not yet covered:

- accumulator overflow limits;
- padding, requantization, PReLU, or weight storage;
- target-device synthesis and DSP48E1 mapping;
- throughput or frame-rate claims.

## 2026-09-22 deterministic random regression

Python generated 96 output groups with three channel contributions per group
(288 signed 3x3 dot products). The XSim test includes:

- full-range random signed INT8 activations and weights;
- explicit `-128` and `127` edge patterns;
- zero to three idle cycles between valid samples;
- signed INT32 bias values, with deliberately unrelated bias values on later
  channels to verify that only the first channel's bias starts a group;
- an independent integer expected-result file consumed by the testbench.

Observed terminal marker:

```text
ACX750_CONV3X3_BACKEND_RANDOM_TEST_PASS groups=96 samples=288
```

The original two-channel directed smoke test was rerun after this addition and
also passed. This establishes arithmetic agreement for the tested widths and
values only; it does not validate a network quantization contract, accumulator
overflow policy, or target-device throughput.

## 2026-09-22 reusable layer primitives

The following XSim markers passed after DSP mapping attributes were added:

```text
ACX750_CONV1X1_BACKEND_TEST_PASS results=2
ACX750_WINDOW3X3_BRAM_TEST_PASS windows=4
ACX750_WINDOW5X5_BRAM_TEST_PASS windows=2
ACX750_DOT25_PIPELINE_TEST_PASS results=3
ACX750_CONV5X5_BACKEND_TEST_PASS results=2
ACX750_WINDOW5_BACKEND_INTEGRATION_TEST_PASS results=2
ACX750_ALL_XSIM_REGRESSIONS_PASS
```

The 3x3 and 5x5 BRAM-window tests include idle cycles. The 5x5 arithmetic test
includes continuous samples, an idle cycle, negative products, and the signed
INT8 `-128 * -128` edge. These are primitive-level checks; padding and full
network scheduling are intentionally absent.

## 2026-09-22 first-layer unsigned activation path

The confirmed model input is uint8 with zero point 0, so a dedicated
`uint8 x signed-INT8` 5x5 backend was added instead of reinterpreting input
bytes as signed activations. XSim covered `128` and `255`, both weight signs,
the `-128` weight edge, continuous samples, an idle cycle, and bias addition.

Observed terminal marker:

```text
ACX750_CONV5X5_U8S8_BACKEND_TEST_PASS results=3
ACX750_ALL_XSIM_REGRESSIONS_PASS
```

This validates first-layer primitive arithmetic only. It does not yet validate
zero padding, exported real weights, PReLU, or requantization.

## Synthesis boundary

See `synthesis_status.md`. In brief, direct XC7A200T synthesis is blocked
because this Vivado installation has no matching part data. Same-generation
XC7Z020 fallback synthesis verified DSP48E1 and BRAM inference, but cannot be
used as ACX750 timing closure evidence.

## 2026-09-22 member A delivery and real-tensor bit-exact checks

An independent NumPy audit verified all 163 manifest entries, 14 parameter
format groups, and four complete integer reference cases. RTL tests then used
member A's actual random-case activations and parameters across all five
arithmetic layers. Observed markers:

```text
ACX750_MEMBER_A_POSTPROCESS_BIT_EXACT_PASS i16=96 u8=8
ACX750_MAPPING0_MEMBER_A_BIT_EXACT_PASS groups=40 contributions=320
ACX750_FEATURE_SUBPIXEL_MEMBER_A_BIT_EXACT_PASS feature=80 subpixel=20
ACX750_CONV1X1_MEMBER_A_BIT_EXACT_PASS shrink=40 expand=80
ACX750_ALL_XSIM_REGRESSIONS_PASS
```

The accumulator now keeps a widened internal sum and saturates only at the
final INT32 boundary, matching member A's reference instead of wrapping at
each channel contribution. A dedicated test proves the distinction between
final-only and premature intermediate saturation.

These results validate representative arithmetic and postprocess paths. They
do not yet validate full-frame line-buffer scheduling, parameter-loading
control, target-device timing, or 30 fps.

## 2026-09-23 member B five-layer streaming regression

The new five-engine ready/valid RTL and packed-parameter ROM top passed XSim
bit-exact checks against member A's audited integer parameters at 6x5 and
96x54. The 96x54 run compared 269,568 intermediate channel values and all
20,736 final uint8 Y bytes. The top-level test also checked start/busy/done,
input and output stalls, and output sideband stability. After replacing the
parallel postprocess with the 13-lane time-shared implementation, both sizes
passed again; the latest 96x54 marker was:

```text
ACX750_MEMBER_B_ROM_TOP_BIT_EXACT_PASS size=96x54 output_bytes=20736
```

This is a functional result. XC7A200T resource mapping, 200 MHz timing, and
30 fps remain unverified.

After adding the named `b_core_real` adapter, an elastic balanced MAC tree,
and synchronous PixelShuffle reads, the 6x5 and 96x54 ROM-top checks passed
again. Member B also connected an isolated copy of C's actual `c_core` modules
to the real five-layer B engine at 6x5, with A's audited integer parameters.
The integration test compared 240 output Y bytes over two frames, checked C's protocol and
overflow flags and stripe count, and observed 16,111 consecutive output stall
cycles while output data and sidebands remained stable:

```text
ACX750_MEMBER_B_C_CORE_REAL_PASS size=6x5 frames=2 bytes=240 max_stall=16111
```

C's supplied stub testbenches use nearest-neighbor expected bytes. They are
not evidence for the real FSRCNN until their scoreboards are adapted.

The full-size `b_core_real` parameterization elaborated at 960x540, without
running a frame. Member B also serialized member A's audited 518,400-byte
input into C's 524,288-address ROM format and checked first/last image bytes
and both padding endpoints through C's original synchronous `input_rom.v`:

```text
ACX750_MEMBER_B_C_INPUT_ROM_PASS pixels=518400 padding=5888
```

With `out_ready=1` throughout the 96x54 B-only run, all 20,736 bytes still
matched and completion occurred after 44,915 simulated cycles, including
start and pipeline fill/drain. This is a small-frame schedule observation,
not a realized full-size frame rate or clock-frequency result.
