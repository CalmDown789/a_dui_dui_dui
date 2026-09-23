# Accumulator width audit

This note supplies a conservative arithmetic bound. It does not choose the
network widths, bias format, saturation rule, or requantization point.

For signed two's-complement activation width `A`, weight width `W`, `K` kernel
taps, and `C` accumulated input channels, the bound used here is:

```text
max_abs <= 2^(A-1) * 2^(W-1) * K * C + bias_abs_bound
```

The smallest signed result width is then `bit_length(max_abs) + 1`. This is
deliberately conservative because it must cover worst-case signed values; real
trained tensors may have a smaller observed range, but that requires evidence
from member A's exported tensors.

Run from the repository root, for example:

```powershell
& 'C:\path\to\python.exe' `
  .\acx750_rtl\scripts\accumulator_width.py `
  --act-width 16 --weight-width 8 --taps 25 --channels 32 --acc-width 32
```

Important consequences for the now-confirmed `d16/s8/m1/c16` topology:

- signed INT8 x INT8 with ordinary 3x3 channel counts fits comfortably in a
  32-bit accumulator under this bound;
- the largest confirmed reduction is signed INT16 x INT8 over 25 taps and 16
  input channels. Its conservative convolution-only bound is 1,677,721,600,
  which fits signed INT32;
- a full-range INT32 bias plus convolution sum generally needs more than 32
  bits internally unless the bias/tensor ranges or an earlier scaling point are
  constrained.

The old 32-input-channel warning was useful while the topology was unresolved,
but it is not the frozen model. The remaining risk is addition of the real
bias, plus the wider intermediate products needed by Q1.15 PReLU and Q31
requantization.

Therefore `INT32 bias/accumulator` is not yet a complete bit-exact contract.
Member A still needs to provide per-layer scales, observed/exported ranges,
bias scaling, rounding, saturation, and requantization order.
