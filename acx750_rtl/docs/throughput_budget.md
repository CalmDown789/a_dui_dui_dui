# Frozen-model arithmetic budget

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
