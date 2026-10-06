# Member A R0 color-pipeline quality evaluation

Date: 2026-10-07

Status: Evaluation in progress; numerical conclusions will be added after the full 90-frame run.

## Scope

This evaluation checks the frozen R0 grayscale super-resolution path inside a software color-video pipeline. It does not retrain or replace the released model, and it does not modify Member B or Member C files. The chroma path is software interpolation only; the result is not FPGA, HDMI, throughput, or board-validation evidence.

The test uses 30 uniformly sampled frames from each of the existing five-second, 10 fps UVG clips for Beauty, Jockey, and Bosphorus. This gives 90 paired frames and includes the previously noted Jockey sample ordinals 17 and 35. Source videos remain local under the ignored `.data/` directory and are not redistributed.

## Compared paths

For each source frame, the decoded 4K Y plane and 4:2:0 Cb/Cr planes are the software reference. A synthetic 960x540 Y input is generated with the frozen Pillow bicubic downsampling convention. The existing full-resolution integer evaluation is reused and its Y, low-resolution input, and output hashes must match exactly.

The four candidate paths combine two luma choices with two chroma interpolation choices:

| Luma | Chroma at 1920x1080 4:2:0 | Purpose |
| --- | --- | --- |
| Direct Pillow bicubic x4 | Bicubic | Baseline |
| Frozen integer R0 FSRCNN x2, then frozen Q14 Keys bicubic x2 | Bicubic | R0 luma path |
| Direct Pillow bicubic x4 | Bilinear | Chroma-method comparison |
| Frozen integer R0 FSRCNN x2, then frozen Q14 Keys bicubic x2 | Bilinear | R0 with alternate chroma |

Both chroma alternatives use the same 480x270 synthetic input derived from the decoded source chroma. For RGB evaluation, each candidate 1920x1080 chroma plane is enlarged to the 3840x2160 luma grid with the same Pillow bicubic conversion.

## Fixed metric and color conventions

- FFmpeg decodes 8-bit 4:2:0 and expands the stream's limited range to full range. The source tags do not explicitly identify a matrix; BT.709 is therefore a fixed evaluation assumption, not a recovered source fact.
- YCbCr-to-RGB uses the existing fixed-point full-range BT.709 coefficients, centers Cb/Cr at 128, rounds as the current software demo does, and clips to uint8.
- RGB PSNR uses joint three-channel MSE with peak 255. RGB SSIM is the arithmetic mean of channel-wise SSIM, using an 11x11 Gaussian window (sigma 1.5) and zero padding. Both full-frame and shave-8 values are reported.
- Cb and Cr are separately scored at the 1920x1080 4:2:0 output grid against the decoded source chroma, with full-frame and shave-4 PSNR/SSIM.
- Reported means are arithmetic means across frames. Negative per-frame R0-minus-baseline differences are counted explicitly; frames are not treated as statistically independent observations.

## Reproduction and outputs

The evaluator is `experiments/r0_4k_quality_20261006/evaluate_color_quality.py`. It validates the source video hashes, frozen grayscale-evaluation hashes, and quantized artifact-tree hash. Per-frame progress, metrics, and selected contact-row images are checkpointed under ignored `.data/r0_color_quality_20261007_checkpoint/`; `--resume` continues only when the source, model, sampling schedule, and evaluator hash match the checkpoint contract.

Run from the repository root after the local UVG sources are present:

```powershell
.\.venv\Scripts\python.exe -m experiments.r0_4k_quality_20261006.evaluate_color_quality --resume
```

The intended published outputs are:

- `results/r0_color_quality_20261007/per_frame_color_metrics.csv` — all 90 frame-level metrics and luma/chroma hashes;
- `results/r0_color_quality_20261007/summary.json` — overall and per-sequence means and regression counts;
- `results/r0_color_quality_20261007/visuals/` — three labeled contact sheets;
- `results/r0_color_quality_20261007/evaluation_manifest.json` — source, model, software, metric, hash, and limitation metadata.

Only derived metrics and contact sheets are committed. The licensed raw UVG sources and resumable intermediate checkpoint remain local and ignored.

## Interpretation boundary

The synthetic low-resolution input is generated from decoded 4K source frames; this is not a native camera 540p capture. Color scores depend on the stated range expansion, BT.709 assumption, and interpolation conventions. The experiment compares software pipelines under that contract. It cannot establish board image quality, camera/HDMI correctness, or real-time performance.
