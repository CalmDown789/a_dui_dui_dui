# ACX750 interface freeze status

Status: open. This file records blockers; it does not decide them.

## Member A model contract

- Exact layer sequence and tensor shapes, including the task-book expansion
  and final-layer channel-count contradictions.
- Per-layer padding, activation, bias, quantization, rounding, saturation, and
  PReLU rules.
- Weight layout, kernel orientation, byte order, and authoritative vectors.
- Verified conversion of the stride-2 9x9 transposed convolution into four
  phase convolutions, including crop, padding, kernel sizes, and phase order.

## Member C board contract

- ACX750 revision, target part, Vivado version, reference project, and XDC.
- Clock, reset, top-level transport, backpressure, frame markers, and data
  width.
- Input/output storage, DDR or streaming responsibility, weight loading, ILA
  probes, and board-result capture method.

## Member B internal baseline

The arithmetic micro-kernel may use parameterized widths and channel counts
for verification. These parameters are test settings only and do not freeze
the deployed network.
