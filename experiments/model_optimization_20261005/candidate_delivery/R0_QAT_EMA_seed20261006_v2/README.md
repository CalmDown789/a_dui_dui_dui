# R0 QAT/EMA v2 — experimental candidate only

This is a portable Member A handoff for a quantization-aware fine-tuning experiment. It is **not** the formal A R0 release and must not replace the frozen production weights or ROMs.

## Contents

- `quant/`: candidate INT8 weights, INT32 biases, Q1.15 PReLU values, quantization parameters, and `.bin`/`.mem`/`.coe` exports.
- `test_vectors_96x54/`: six small inputs with per-layer accumulators and activations.
- `full_integer_golden/`: full 960×540 to 1920×1080 input/output and per-stage hashes.
- `full_reference/`: QDQ/FP32 software references used to audit the candidate conversion.
- `training/`: selected checkpoint, training log, and run manifest.
- `bundle_manifest.json`: SHA-256 and byte count for every packaged file except the manifest itself.

## Identity and measured scope

- Candidate checkpoint SHA-256: `10867199deba770b8903e268bb4aa6775f0ad2036bab695790b6593cc01eeb6a`.
- Candidate `quant_params.json` SHA-256: `12e6e26ea9770c7bf57ab3cc048328d845f2a6cbb6764441df0d7c74e50c2809`.
- On the one-time held-out DIV2K official validation-HR set (100 images), the integer candidate measured +0.0664 dB mean PSNR over frozen R0; the paired bootstrap 95% interval was [+0.0445, +0.0987] dB.
- This is a modest PC software quality result. MAC count is unchanged, and it does not establish FPGA resource, timing, throughput, or image quality.

## Verify

From the repository root, using the project Python environment:

```powershell
$env:PYTHONPATH = 'src'
python experiments/model_optimization_20261005/verify_candidate_delivery.py `
  --delivery-dir experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2 `
  --quant-dir experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2/quant `
  --checkpoint experiments/model_optimization_20261005/candidate_delivery/R0_QAT_EMA_seed20261006_v2/training/candidate_ema_qat_fp32.pth `
  --recompute-full
```

The report is only an A-side integer-reference verification. B must run candidate-specific RTL vector and full-frame comparison; C/team must separately evaluate candidate resources/timing and the physical board before discussing promotion. The official R0 assets remain unchanged.
