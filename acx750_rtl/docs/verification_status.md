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

- random or file-driven vectors;
- accumulator overflow limits;
- line/window generation;
- padding, requantization, PReLU, or weight storage;
- target-device synthesis and DSP48E1 mapping;
- throughput or frame-rate claims.
