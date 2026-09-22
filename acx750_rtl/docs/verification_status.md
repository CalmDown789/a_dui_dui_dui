# Verification status

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

## Synthesis boundary

See `synthesis_status.md`. In brief, direct XC7A200T synthesis is blocked
because this Vivado installation has no matching part data. Same-generation
XC7Z020 fallback synthesis verified DSP48E1 and BRAM inference, but cannot be
used as ACX750 timing closure evidence.
