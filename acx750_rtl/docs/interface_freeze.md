# ACX750 interface freeze status

Status: open. This file records blockers; it does not decide them.

## Member A model contract

- The newly supplied `d16/s8/m1/c16` PixelShuffle description is a candidate,
  not yet a frozen replacement for the task-book topology; the team is still
  reconciling the two sources.
- Exact layer sequence and tensor shapes, including the task-book expansion
  and final-layer channel-count contradictions.
- Per-layer padding, activation, bias, quantization, rounding, saturation, and
  PReLU rules.
- Resolve whether intermediate activations presented to multipliers are INT8
  or INT16. The conservative width audit shows that INT16 x INT8, 25 taps, 32
  channels can require 33 signed accumulator bits before bias.
- Exact bias numerical range/scale and the point at which requantization occurs;
  saying both "bias INT32" and "accumulator INT32" does not by itself prevent
  overflow.
- Weight layout, kernel orientation, byte order, and authoritative vectors.
- Verified conversion of the stride-2 9x9 transposed convolution into four
  phase convolutions, including crop, padding, kernel sizes, and phase order.

## Member C board contract

- ACX750 revision, target part, Vivado version, reference project, and XDC.
- Install or provide Vivado device data that recognizes
  `xc7a200tfbg484-2`; the current 2025.2 installation returns `No parts
  matched` for that exact part.
- Clock, reset, top-level transport, backpressure, frame markers, and data
  width.
- Input/output storage, DDR or streaming responsibility, weight loading, ILA
  probes, and board-result capture method.

## Member B internal baseline

The arithmetic micro-kernel may use parameterized widths and channel counts
for verification. These parameters are test settings only and do not freeze
the deployed network.
