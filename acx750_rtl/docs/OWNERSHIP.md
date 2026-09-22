# Team ownership and integration boundary

## Member B work in this subtree

Everything under `acx750_rtl/` is the member B pure-RTL workstream unless a
file explicitly says it is copied from another member. It includes:

- parameterized 1x1, 3x3, and 5x5 arithmetic backends;
- signed INT16 x INT8 and first-layer uint8 x INT8 paths;
- widened accumulation with final INT32 saturation;
- Q1.15 PReLU, signed Q31 requantization, ties-away rounding, and output
  saturation;
- 3x3/5x5 window primitives and PixelShuffle phase mapping;
- XSim testbenches, vector generators, independent delivery auditing, and
  conservative throughput/width analysis.

This attribution should remain visible when the branch is reviewed or merged.

## External inputs

- Member A owns model training, checkpoint, quantized tensors, scales,
  integer-reference semantics, quality metrics, and golden vectors.
- Member C owns the ACX750 reference project, part installation, board clocks,
  reset, pin/XDC constraints, external transport, ILA, bitstream, and board
  measurements.

Member B consumes those contracts but does not claim ownership of them or
silently decide unresolved A/C interfaces.

## Git integration warning

Member A's `origin/main@83a9fcd` contains the needed delivery assets, but its
history also deletes earlier member-B/member-C/HLS files. Do not merge or pull
that branch blindly into `acx750-rtl`. Import only the reviewed member-A
delivery paths, or perform an explicit conflict-resolved integration that
preserves all team work.
