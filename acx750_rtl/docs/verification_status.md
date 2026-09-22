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
- line/window generation;
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
