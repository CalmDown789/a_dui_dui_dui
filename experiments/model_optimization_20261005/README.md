# Member A quantized-model optimization

This experiment keeps the released network shape `d16/s8/m1/c16` and its MAC count unchanged. The frozen checkpoint and official quantization package remain read-only. Candidate checkpoints, downloaded datasets, generated vectors, and full-frame references are local under ignored `.data/model_optimization/`.

## Result

Detailed measurements, hashes, methodology and the adoption boundary are in [REPORT.md](REPORT.md).

The current candidate is an integer-oriented QAT checkpoint. It was selected at epoch 8 of a 15-epoch mixed-data QAT run, then refined from that checkpoint for 10 lower-rate EMA-QAT epochs; epoch 7 was selected on the predeclared 20-image selection subset. Training used T91 plus DIV2K training-HR IDs 0001–0720. IDs 0721–0800 were held out from training; 20 were used for checkpoint selection and 60 remained untouched by selection. Activation calibration uses 32 deterministic patches from training images only. Official DIV2K validation-HR IDs 0801–0900 were reserved for final paired evaluation and were not used for training or checkpoint selection.

| Exact integer comparison | Frozen model | Candidate | Candidate gain |
| --- | ---: | ---: | ---: |
| Official DIV2K validation-HR, exact integer, 100 images | 32.404 dB | 32.471 dB | +0.066 dB |
| Set5, 5 images | 34.018 dB | 34.082 dB | +0.064 dB |
| Sintel, 8 frames | 43.916 dB | 45.034 dB | +1.118 dB |
| Big Buck Bunny development set, 8 frames | 46.366 dB | 48.132 dB | +1.766 dB |
| DIV2K internal reserved subset, exact integer, 20 images | 31.651 dB | 31.695 dB | +0.044 dB |

The official 100-image paired gain has a per-image bootstrap 95% confidence interval of +0.044 to +0.099 dB. Its x2 LR input was generated from the official validation HR using the project's Pillow bicubic Y-channel preprocessing; this is not the official MATLAB-bicubic LR track. Candidate QDQ and exact integer scores are close on this evaluation (32.4705 vs 32.4707 dB). For a synthetic 960×540 full-frame input, 2,032,785 of 2,073,600 output bytes match QDQ byte-for-byte; all remaining bytes differ by at most 1 (MAE 0.01968).

The candidate improves the intended quantized path on the measured sets, with a modest +0.066 dB mean gain on the independent 100-image validation set. Its FP32 PSNR is not uniformly better, so this is not a claim of general floating-point quality improvement. Video-set gains are source-specific and should not be generalized to all content. MAC count and throughput estimate are unchanged.

## Reproduction

Use the project Python runtime and local ignored dependencies. `prepare_div2k_hr.py` retrieves/verifies DIV2K once; that 3.5 GB academic-use dataset is kept outside Git. For an exact rerun, point training to a fresh output directory because scripts refuse to overwrite prior results:

```powershell
$env:PYTHONPATH = '.;src;.data\model_optimization\site-packages'
python experiments\model_optimization_20261005\prepare_div2k_hr.py
python experiments\model_optimization_20261005\train_div2k_qat.py --epochs 15 --output-dir .data\model_optimization\div2k_qat_mix_rerun
python experiments\model_optimization_20261005\evaluate_div2k_qat.py --run-dir .data\model_optimization\div2k_qat_mix_rerun --output-dir .data\model_optimization\div2k_qat_mix_rerun\evaluation
python experiments\model_optimization_20261005\summarize_div2k_qat.py --run-dir .data\model_optimization\div2k_qat_mix_rerun --evaluation-dir .data\model_optimization\div2k_qat_mix_rerun\evaluation
python experiments\model_optimization_20261005\evaluate_independent_sources.py --candidate-run .data\model_optimization\div2k_qat_mix_rerun --candidate-quant .data\model_optimization\div2k_qat_mix_rerun\evaluation\candidate_quantized --frozen-train-quant .data\model_optimization\div2k_qat_mix_rerun\evaluation\frozen_train_calibrated_quantized --output-dir .data\model_optimization\div2k_qat_mix_rerun\independent_eval
python experiments\model_optimization_20261005\generate_candidate_delivery.py --run-dir .data\model_optimization\div2k_qat_mix_rerun --quant-dir .data\model_optimization\div2k_qat_mix_rerun\evaluation\candidate_quantized --output-dir .data\model_optimization\div2k_qat_mix_rerun\candidate_delivery
python experiments\model_optimization_20261005\verify_candidate_delivery.py --delivery-dir .data\model_optimization\div2k_qat_mix_rerun\candidate_delivery --quant-dir .data\model_optimization\div2k_qat_mix_rerun\evaluation\candidate_quantized --recompute-full
```

The official [DIV2K page](https://data.vision.ee.ethz.ch/cvl/DIV2K/) limits use to academic research and notes that the images retain their original copyrights. The raw archive is kept locally and is not redistributed. Sintel is [CC BY 3.0](https://durian.blender.org/sharing/); preserve the Blender Foundation attribution if evaluation material is redistributed.

## Low-rate refinement and final holdout

The parent checkpoint's 20-image selection curve was noisy after epoch 8. A second pass starts from that selected checkpoint, uses a lower learning rate with per-batch EMA, and chooses a checkpoint only on the same predeclared 20-image selection split. The official DIV2K validation-HR IDs 0801-0900 are reserved for one final paired evaluation and must not be used to tune or reselect the candidate.

```powershell
New-Item -ItemType Directory -Force .data\model_optimization\datasets\div2k_official_valid\archives | Out-Null
curl.exe --location --fail --retry 5 --retry-all-errors --retry-delay 2 --continue-at - --output '.data\model_optimization\datasets\div2k_official_valid\archives\DIV2K_valid_HR.zip' 'https://data.vision.ee.ethz.ch/cvl/DIV2K/DIV2K_valid_HR.zip'
python experiments\model_optimization_20261005\prepare_div2k_official_valid.py
python experiments\model_optimization_20261005\train_ema_qat_refine.py --epochs 10 --learning-rate 0.000001 --ema-decay 0.99
python experiments\model_optimization_20261005\export_candidate_quant.py --checkpoint '.data\model_optimization\qat_ema_refine_20261006\candidate_ema_qat_fp32.pth' --scales '.data\model_optimization\qat_ema_refine_20261006\quant_calibration_scales.json' --output-dir '.data\model_optimization\qat_ema_refine_20261006\candidate_quantized'
python experiments\model_optimization_20261005\evaluate_official_div2k_valid.py --candidate-run '.data\model_optimization\qat_ema_refine_20261006' --candidate-checkpoint-name 'candidate_ema_qat_fp32.pth' --candidate-quant '.data\model_optimization\qat_ema_refine_20261006\candidate_quantized' --output-dir '.data\model_optimization\qat_ema_refine_20261006\official_valid_eval'
```

The evaluation constructs its x2 low-resolution input from official validation HR using the project's stated Pillow bicubic Y-channel preprocessing; this is deliberately not labeled as the official MATLAB-bicubic LR track. The archive is kept under ignored `.data/` and is not committed.

The final selected checkpoint is `qat_ema_refine_20261006/candidate_ema_qat_fp32.pth` (SHA-256 `10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a`). Its exported candidate quantization parameters have SHA-256 `12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809`. The full-size candidate integer output is 2,073,600 bytes, SHA-256 `d1d9a6fb09d3fe84a6538df2a68107a216d79586ae3c296fa5d8706c616dbef1`. `verify_candidate_delivery.py --recompute-full` passed for the packaged layer vectors and recomputed full-frame hashes. The delivery remains marked `EXPERIMENTAL_NOT_RELEASED`.

## Acceptance boundary

This is PC software evidence only. The frozen A artifacts were not replaced, and no B/C RTL or files were changed. The isolated experimental candidate package is under:

`.data\model_optimization\qat_ema_refine_20261006\candidate_delivery`

Before any adoption, regenerate the candidate’s A delivery from its recorded hashes, rerun B’s bit-exact suite with the candidate ROM/Golden, and obtain the relevant C-side synthesis, implementation, and board evidence. Nothing in this experiment claims FPGA timing, video throughput, or board acceptance.
