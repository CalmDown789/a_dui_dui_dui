# Synthesis status

## Direct ACX750 attempt

Vivado 2025.2 stopped before RTL synthesis with:

```text
No parts matched 'xc7a200tfbg484-2'
```

The current installation therefore lacks the required Artix-7 part data. This
is a tool installation blocker, not an RTL failure.

## DSP48E1 fallback checks

To verify structural inference only, the same RTL was synthesized out of
context for the installed `xc7z020clg400-1`, which also uses DSP48E1. The
constraint was 5.000 ns (200 MHz), but all timing numbers below are synthesis
estimates without placement, routing, board XDC, or clock-source modeling.

| Core | LUT | FF | DSP48E1 | Synth WNS |
|---|---:|---:|---:|---:|
| 3x3 before `use_dsp` | 766 | 470 | 0 | +2.150 ns |
| 3x3 DSP-directed | 217 | 310 | 9 | +2.150 ns |
| 5x5 DSP-directed | 488 | 598 | 25 | +2.150 ns |

This proves only conservative one-multiply-per-DSP inference. It neither
implements nor validates dual-INT8 packing.

## Row-buffer fallback checks

Window tests used `DATA_W=16` and `IMG_W=960`.

| Window | LUT | LUTRAM | FF | RAMB18E1 | Synth WNS |
|---|---:|---:|---:|---:|---:|
| 3x3 cascade baseline | 308 | 240 | 163 | 1 | +0.330 ns |
| 3x3 rotating banks | 42 | 0 | 217 | 3 | +0.717 ns |
| 5x5 cascade baseline | 878 | 720 | 445 | 1 | +0.326 ns |
| 5x5 rotating banks | 126 | 0 | 474 | 5 | +1.042 ns |

The rotating-bank versions remove distributed line-buffer RAM. Vivado warns
that optional BRAM output registers were not absorbed, so target-device
place-and-route may still require one more pipeline stage.

None of these tables is an ACX750 resource or timing sign-off. They are saved
as reproducible fallback evidence until member C supplies target device support,
clock/reset constraints, and the board reference project.

## Postprocess synthesis attempt

Member B added a reproducible OOC script for the Q1.15/Q31 postprocess, with
separate hidden-INT16 and final-uint8 configurations. On 2026-09-22 Vivado
failed during program startup with `Failed to install all user apps` before it
read any RTL. No LUT/FF/DSP/timing number was produced, so this is recorded as
a tool-startup blocker rather than a synthesis result. The script remains for
rerun after the Vivado environment or member C's target setup is available.
