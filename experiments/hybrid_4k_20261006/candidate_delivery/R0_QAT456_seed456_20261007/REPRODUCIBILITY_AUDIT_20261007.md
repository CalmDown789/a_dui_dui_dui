# R0 QAT seed456 reproducibility audit

Date: 2026-10-07

Published candidate branch: `codex/member-a-r0qat456-bundle-20261007`

Audited published commit: `25802062ae500e3d5e33cd9f0e25cdaeefb0b1ed`

## Scope

Reran the five-epoch seed456 QAT training and regenerated its candidate quantization package from the same initial checkpoint, training/validation manifests, calibration set, and test sets. All rerun outputs were written under the ignored `.data/` directory; the published candidate weights and package were not overwritten.

This is an A-side software reproducibility check. It is not a B-RTL bit-exact result, FPGA implementation, board test, or real-time performance claim.

## Training reproduction

- Initial checkpoint SHA-256: `956a6916d7fe059b4f0d2493a7196c3c2db03d72906e9f832b6ca33fde3363bf`
- Training manifest SHA-256 values: Beauty `b7813d27…`, HoneyBee `a73b3d0a…`, YachtRide `721c42b2…`.
- Validation manifest SHA-256: `9d2cab2d…`.
- The published and rerun `qat_training_log.csv` files are byte-identical; SHA-256: `54458b4a5729b2cd75a2130794f0a494788d7778869a0bb98330c7435b141bc4`.
- All 14 `state_dict` tensors and all activation scales match exactly.
- The serialized checkpoint files have different SHA-256 values (`123ba381…` published; `a8333d98…` rerun) because their `config` metadata dictionaries differ: the rerun additionally records the R0 name and `head_kernel=5`. The tensor state and quantized exports are identical; do not use the container-file hash alone to infer a weight mismatch.
- Exact `source_sha256` overlap across the 180 training manifest rows, 10 validation rows, and 50 test-pair rows is zero. The test manifests contain 25 unique source/HR frames: each reference frame appears in two test pairs with the same HR hash but a different LR hash. Thus the test count is 50 LR/HR pairs, not 50 independent HR images.

| Epoch | Training MSE | Validation fake-quant MSE |
|---:|---:|---:|
| 1 | 5.4189448989442704e-05 | 2.7927185874432327e-05 |
| 2 | 6.535333319435368e-05 | 2.6988439640263095e-05 |
| 3 | 6.055927556695274e-05 | 2.7773793044616467e-05 |
| 4 | 5.275005618791005e-05 | 2.720201628108043e-05 |
| 5 | 8.054430668885794e-05 | 2.7751006564358248e-05 |

Best validation epoch: 2.

## Quantization and vector reproduction

- Calibration manifest SHA-256: `721c42b2c7cdb2422b9ca06bee09b0c34b3a2b7ae694672edda637c0616173be` (60 samples).
- All 57 quantized export files are byte-identical to the published package. `quant_params.json` SHA-256: `f2d6c4865b295f6a02c67a43ab2fb00cd36ede723ee8743575f6746f52d924ac`.
- All 64 files in the four fixed-vector sets (zero, impulse, ramp, random) are byte-identical.

## 50-frame quality reproduction

The regenerated evaluation covers the same 50 paired frames and six test manifests as the published candidate report. All mean metrics reproduce at the reported precision. Across per-image rows, every shared numeric value matches within `1e-12`; the only non-identical fields are bicubic SSIM and full-frame bicubic SSIM, with maximum absolute difference `2.22e-16` from floating-point accumulation.

The 50-pair mean gives equal weight to the two LR variants for each of the 25 HR references. Per-manifest PSNR means (8-pixel shave) are:

| Test manifest | Pairs | Bicubic (dB) | FP32 (dB) | Integer (dB) |
|---|---:|---:|---:|---:|
| `ffmpeg_Bosphorus_test_pairs` | 10 | 43.16 | 44.03 | 45.20 |
| `ffmpeg_ReadySetGo_test_pairs` | 10 | 38.40 | 40.51 | 40.85 |
| `ffmpeg_ShakeNDry_test_pairs` | 5 | 43.26 | 44.82 | 45.28 |
| `uvg_Bosphorus_pairs` | 10 | 43.01 | 44.06 | 45.23 |
| `uvg_ReadySetGo_pairs` | 10 | 38.23 | 40.48 | 40.84 |
| `uvg_ShakeNDry_pairs` | 5 | 43.04 | 44.80 | 45.29 |

| Metric | 8-pixel shave | Full frame |
|---|---:|---:|
| Bicubic PSNR (dB) | 41.18858 | 41.19072 |
| FP32 PSNR (dB) | 42.77793 | 42.75955 |
| Integer PSNR (dB) | 43.48220 | 43.45919 |
| Integer gain over bicubic (dB) | 2.29362 | 2.26847 |
| Bicubic SSIM | 0.974176 | 0.974222 |
| FP32 SSIM | 0.974408 | 0.974387 |
| Integer SSIM | 0.979736 | 0.979688 |

The integer result is about 0.70 dB higher than the FP32 result on these test pairs; this is an observed metric, not a general guarantee. The dataset contains synthetically degraded Y-channel frames, including lossy-video-derived material, and is not camera-original ground truth.

## Acceptance boundary

This audit confirms reproducibility of the A-side training log, model tensors, quantization exports, fixed vectors, and reported software metrics. It does not change the candidate's experimental status or establish equivalence with B RTL, hardware timing, FPGA image quality, or sustained video throughput.
