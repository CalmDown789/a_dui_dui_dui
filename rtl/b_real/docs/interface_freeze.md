# ACX750 interface freeze status

Status: partially frozen. This file separates team-confirmed facts from open
blockers; it does not invent missing contracts.

## Member A model contract

Confirmed by the user on 2026-09-22, with the teammate-A response as the model
source of truth instead of the contradictory task-book tables:

- native PixelShuffle model `FSRCNNSubpixel(d=16, s=8, m=1, c=16, scale=2)`;
- layer sequence `5x5 1->16`, `1x1 16->8`, `3x3 8->8`, `1x1 8->16`,
  `5x5 16->4`, then PixelShuffle x2;
- all convolution outputs remain 960x540: zero padding 2, 0, 1, 0, 2;
- per-output-channel PReLU after the first four convolutions, none after the
  final subpixel convolution;
- input uint8 with scale 1/255 and zero point 0; signed per-output-channel INT8
  weights; signed INT16 intermediate activations; signed INT32 bias and stated
  accumulator; per-channel signed Q1.15 PReLU slopes;
- PixelShuffle phases `C0=top-left`, `C1=top-right`, `C2=bottom-left`,
  `C3=bottom-right`;
- this is not a converted 9x9 transposed convolution, so the former conversion
  question is closed;
- workload 1.4681088 GMAC/frame and about 44.043 GMAC/s at 30 fps.

Delivered and independently checked on `origin/main@83a9fcd`:

- checkpoint, `quant_params.json`, INT8/INT32/Q1.15 tensors, full-reference
  outputs, Set5 evidence, and zero/impulse/ramp/random per-layer vectors;
- OIHW cross-correlation ordering, little-endian `.bin`, two's-complement
  `.mem/.coe`, and HWC row-major activations;
- Q1.15 PReLU before Q31 requantization, nearest rounding with ties away from
  zero, final INT32 saturation, and INT16/uint8 output saturation;
- actual biases are small relative to INT32 in this delivery, while the RTL
  still uses widened internal accumulation before final saturation.

Still open before full-network RTL verification:

- full-frame line-buffer/scheduler integration for every layer;
- storage/loading integration for the delivered parameter files;
- the reported 34.02 dB is QDQ simulation, not an integer-reference or RTL
  bit-exact result.

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

The first layer uses a dedicated unsigned-activation path. Feeding the frozen
uint8 input directly into a signed-INT8 backend would corrupt values 128..255.
