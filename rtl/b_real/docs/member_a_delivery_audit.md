# Member A integer-delivery audit by member B

Source revision: `origin/main@83a9fcdd34c27fa61b478a12878d636cba99d029`.

## Independent package audit

Member B exported the revision into an isolated review directory and ran
`scripts/audit_member_a_delivery.py`, which does not use member A's PyTorch
reference implementation. It uses NumPy to recompute all integer layers.

Results:

```text
delivery files with matching byte count, CRC32, and SHA-256: 163
parameter groups equal across NPY/BIN/MEM/COE:                14
integer cases recomputed end to end:                          4/4
cases: zero, impulse, ramp, random
status: PASS
```

The audit validates OIHW weights, little-endian binary data, HWC row-major
activations, zero padding, INT32 final saturation, per-channel Q1.15 PReLU,
Q31 requantization, nearest-ties-away rounding, INT16/uint8 saturation, and the
four PixelShuffle phases.

## RTL comparisons using real parameters

The following XSim tests use member A's actual quantized weights, biases,
PReLU slopes, Q31 multipliers, and random-case activations:

| Path | Coverage | Result |
|---|---:|---|
| PReLU/requant | 96 hidden + 8 output samples | PASS |
| Feature 5x5 | 80 output groups | PASS |
| Shrink 1x1 | 40 output groups, 640 contributions | PASS |
| Mapping0 3x3 | 40 output groups, 320 contributions | PASS |
| Expand 1x1 | 80 output groups, 640 contributions | PASS |
| Subpixel 5x5 | 20 output groups, 320 contributions | PASS |

The selected convolution positions include all four corners and the center,
so the vector construction checks zero-padding orientation as well as OIHW
kernel/channel order. These are representative layer-level checks. The
line-buffer scheduler has not yet produced an entire 960x540 frame through all
five RTL layers.

## Remaining performance caveat

Member A's README still quotes `133.2 GMAC/s` and `3.02x` from the task-book
platform assumption. Member A's tensors do not validate dual-INT8 packing, and
the frozen hidden path is INT16 x INT8. Member B therefore continues to use one
MAC per DSP per cycle as the conservative baseline. At the teammate-A example
clock of 90 MHz, 30 fps requires 66.13% of the raw 740-DSP peak; 65% total
efficiency is already insufficient.
