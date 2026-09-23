# Frozen-model arithmetic budget

## 2026-09-23 member B architecture baseline v1.1

The frozen five-engine schedule allocates 50/16/72/16/200 lanes, 354 one-DSP
MAC lanes in total, and provisionally 16 more DSPs for postprocessing: 370
DSPs is a theoretical budget. The current shared postprocess RTL has 13 multiplier lanes in
total (4/2/2/4/1 across L1..L5), within the provisional 16-lane allocation
structurally; this is not a verified DSP48E1 count. Each engine takes 8 accepted phase transfers
per LR pixel. At an *assumed* 200 MHz and no stalls, 518,400 LR positions take
4,147,200 cycles, or 48.23 frames/s before pipeline fill, borders, stalls,
output buffering, and implementation losses. At 150 MHz the same arithmetic
upper bound is 36.17 frames/s. Neither is a realized frame rate. The earlier
90 MHz/740-DSP calculation below remains a separate raw-device scenario, not
the current instantiated-architecture budget.

The confirmed 960x540 `d16/s8/m1/c16` topology contains exactly 1,468,108,800
MAC per frame. At 30 fps it therefore requires 44.043264 GMAC/s.

Run the parameterized calculation from the repository root, for example:

```powershell
& python .\acx750_rtl\scripts\throughput_budget.py --clock-mhz 90
```

With 740 DSPs, one MAC per DSP per cycle, and 90 MHz, the arithmetic-only
figures are:

```text
raw peak                         66.600 GMAC/s
required raw-peak fraction       66.13%
required average active DSPs     489.37 of 740
ideal compute cycles/frame       1,983,930.81
90 MHz / 30 fps deadline         3,000,000 cycles/frame
```

This agrees with teammate A's corrected 1.51x raw arithmetic margin. It is not
a 30 fps implementation claim. The design must sustain roughly 490 useful MACs
per clock on average at 90 MHz after layer transitions, window borders,
padding, memory traffic, PReLU, requantization, and PixelShuffle scheduling are
included. The subpixel 5x5 layer alone accounts for 829,440,000 MAC/frame, or
56.50% of the model.

The 90 MHz value is a scenario, not a frozen clock. Member C still owns the
board clock/reset/XDC contract, and target-device synthesis is required before
using any clock value in the final feasibility claim.
