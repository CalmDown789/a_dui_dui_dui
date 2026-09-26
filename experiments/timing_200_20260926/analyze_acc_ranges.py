#!/usr/bin/env python3
"""Reproduce frozen-model integer ranges; no RTL edit, simulation, or Vivado.

Checks all 19 packed ROMs against the release hashes, reconstructs all 10
original weight/bias binaries and verifies their A-source hashes, then checks
52 output channels, 416 global phase prefixes, and every MAC reduction node.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ROM = ROOT / "rom/member_a_d16_s8_m1_c16"
RELEASE_HASHES = ROOT / "experiments/timing_margin_20260926/release_source_hashes.json"
# name, K, CIN, COUT, IN_PAR, OUT_PAR, activation minimum, activation maximum
SETTINGS = [
    ("feature", 5, 1, 16, 1, 2, 0, 255),
    ("shrink", 1, 16, 8, 2, 8, -32768, 32767),
    ("mapping0", 3, 8, 8, 1, 8, -32768, 32767),
    ("expand", 1, 8, 16, 1, 16, -32768, 32767),
    ("subpixel", 5, 16, 4, 2, 4, -32768, 32767),
]
RTL_PATHS = [
    "rtl/b_real_ae29515/stream/fsrcnn_network_mem_top.sv",
    "experiments/l5_splitmem_20260924/rtl/b/fsrcnn_network_core.sv",
    "experiments/l5_splitmem_20260924/rtl/b/phase_mac_pipeline.sv",
    "experiments/l5_splitmem_20260924/rtl/b/phase_accumulator_36.sv",
    "experiments/l5_splitmem_20260924/rtl/b/prelu_requantize.sv",
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def width(lo, hi):
    return next(n for n in range(1, 65) if -(1 << (n - 1)) <= lo and hi < (1 << (n - 1)))


def bounds(lo, hi):
    return dict(minimum=lo, maximum=hi, required_signed_bits=width(lo, hi))


def aggregate(intervals):
    return bounds(min(v[0] for v in intervals), max(v[1] for v in intervals))


def unpack(name, bits, count):
    raw = (ROM / name).read_bytes()
    words = re.sub(r"//[^\n]*", "", raw.decode("utf-8")).split()
    if (len(words) != 1 or not re.fullmatch("[0-9a-fA-F]+", words[0])
            or len(words[0]) != bits * count // 4):
        raise ValueError(f"Unexpected packed ROM format: {name}")
    packed, mask = int(words[0], 16), (1 << bits) - 1
    values = [(packed >> (i * bits)) & mask for i in range(count)]
    return [v - (1 << bits) if v & (1 << (bits - 1)) else v for v in values]


def check_roms():
    packing = json.loads((ROM / "manifest.json").read_text(encoding="utf-8"))
    entries = {item["name"]: item for item in packing["files"]}
    release = json.loads(RELEASE_HASHES.read_text(encoding="utf-8"))
    released = {item["path"]: item for item in release["files"]}
    if len(entries) != 19:
        raise ValueError("Expected 19 packed ROM entries")
    audits = []
    for name, entry in entries.items():
        raw = (ROM / name).read_bytes()
        canonical = raw.replace(b"\r\n", b"\n")
        relative = (ROM / name).relative_to(ROOT).as_posix()
        if sha(canonical) != released[relative]["canonical_sha256"]:
            raise ValueError(f"ROM differs from the frozen release: {name}")
        audits.append(dict(
            path=relative, raw_sha256=sha(raw), canonical_sha256=sha(canonical),
            release_canonical_match=True, packing_manifest_sha256=entry["sha256"],
            packing_manifest_matches_raw=sha(raw) == entry["sha256"],
            packing_manifest_matches_canonical=sha(canonical) == entry["sha256"],
        ))
    # The arithmetic layout was read from these frozen files. Refuse silently
    # applying the hard-coded layer table after its RTL contract changes.
    for path in RTL_PATHS:
        canonical = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        if sha(canonical) != released[path]["canonical_sha256"]:
            raise ValueError(f"Reference RTL differs from the frozen layout: {path}")
    return entries, audits


def analyze_layer(index, setting, rom_entries):
    name, k, cin, cout, ip, op, xlo, xhi = setting
    taps, ing = k * k, cin // ip
    if ing * (cout // op) != 8:
        raise ValueError(f"Layer is not an eight-phase configuration: {name}")
    weights = unpack(name + "_weights_packed.mem", 8, cout * cin * taps)
    biases = unpack(name + "_bias_packed.mem", 32, cout)
    decoded_hashes = {}
    for kind, values, bits in [("weights", weights, 8), ("bias", biases, 32)]:
        raw = b"".join(v.to_bytes(bits // 8, "little", signed=True) for v in values)
        actual = sha(raw)
        expected = rom_entries[name + "_" + kind + "_packed.mem"]["source_sha256"]
        if actual != expected:
            raise ValueError(f"Decoded A-source binary SHA mismatch: {name}/{kind}")
        decoded_hashes[kind] = dict(source_sha256=actual, matches_member_a_original_binary=True)

    channels, all_tree, all_partial, all_prefix, all_final = [], [], [], [], []
    for oc in range(cout):
        ws = weights[oc * cin * taps:(oc + 1) * cin * taps]
        prefixes, phase_contributions = [], []
        alo = ahi = 0
        for phase in range(8):
            assigned = oc // op == phase // ing
            if assigned:
                ig = phase % ing
                selected = ws[ig * ip * taps:(ig + 1) * ip * taps]
                nodes = [(min(w * xlo, w * xhi), max(w * xlo, w * xhi)) for w in selected]
                plo, phi = sum(p[0] for p in nodes), sum(p[1] for p in nodes)
                tree, level = [], 0
                while True:
                    tree.append(dict(level=level, node_count=len(nodes), range=aggregate(nodes)))
                    all_tree.extend(nodes)
                    if any(width(*node) > 32 for node in nodes):
                        raise ValueError(f"MAC node exceeds signed32: {name}, oc={oc}, phase={phase}")
                    if len(nodes) == 1:
                        break
                    nodes = [
                        (sum(v[0] for v in nodes[j:j + 2]), sum(v[1] for v in nodes[j:j + 2]))
                        for j in range(0, len(nodes), 2)
                    ]
                    level += 1
                if nodes[0] != (plo, phi):
                    raise ValueError("Reduction tree and direct phase sum disagree")
                all_partial.append((plo, phi))
                phase_contributions.append(dict(
                    phase=phase, input_channels=list(range(ig * ip, (ig + 1) * ip)),
                    partial=bounds(plo, phi), tree_levels=tree,
                ))
                alo, ahi = alo + plo, ahi + phi
            prefixes.append(dict(phase=phase, contributes=assigned, range=bounds(alo, ahi)))
            all_prefix.append((alo, ahi))
        positive, negative = sum(w for w in ws if w > 0), sum(w for w in ws if w < 0)
        direct_lo, direct_hi = xlo * positive + xhi * negative, xhi * positive + xlo * negative
        if (alo, ahi) != (direct_lo, direct_hi):
            raise ValueError(f"Phase sums and positive/negative weight formula disagree: {name}/{oc}")
        final = alo + biases[oc], ahi + biases[oc]
        all_final.append(final)
        if any(p["range"]["minimum"] < alo or p["range"]["maximum"] > ahi for p in prefixes):
            raise ValueError(f"Prefix exceeds complete unbiased interval: {name}/{oc}")
        channels.append(dict(
            output_channel=oc, bias=biases[oc], sum_positive_weights=positive,
            sum_negative_weights=negative, sum_abs_weights=sum(abs(w) for w in ws),
            convolution_before_bias=bounds(alo, ahi), final_with_bias=bounds(*final),
            accumulator_and_bias_union=bounds(min(0, alo, final[0]), max(0, ahi, final[1])),
            prefix_outside_final_biased_interval=any(
                p["range"]["minimum"] < final[0] or p["range"]["maximum"] > final[1]
                for p in prefixes
            ),
            prefix_after_each_global_phase=prefixes, assigned_phase_details=phase_contributions,
        ))
    summary = dict(
        before_bias_all_prefixes=aggregate(all_prefix), final_with_bias=aggregate(all_final),
        partial_sums=aggregate(all_partial), multiply_and_reduction_tree_nodes=aggregate(all_tree),
        all_arithmetic=aggregate(all_prefix + all_final + all_tree + [(0, 0)]),
        prefixes_within_unbiased_complete_sum=True,
        channels_with_prefix_outside_final_biased_interval=sum(
            c["prefix_outside_final_biased_interval"] for c in channels
        ),
    )
    if summary["all_arithmetic"]["required_signed_bits"] > 32:
        raise ValueError(f"Frozen layer arithmetic exceeds signed32: {name}")
    return dict(
        layer=index, name=name, K=k, CIN=cin, COUT=cout, IN_PAR=ip, OUT_PAR=op,
        IN_GROUPS=ing, ACT_UNSIGNED=int(xlo == 0), input_range=[xlo, xhi],
        decoded_source_binary_checks=decoded_hashes, summary=summary, channels=channels,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=HERE / "acc_range_analysis.json",
                        help="Write the reproducible report to this path")
    args = parser.parse_args()
    entries, audits = check_roms()
    layers = [analyze_layer(i, setting, entries) for i, setting in enumerate(SETTINGS, 1)]
    channel_count = sum(len(layer["channels"]) for layer in layers)
    prefix_count = sum(len(c["prefix_after_each_global_phase"]) for l in layers for c in l["channels"])
    if (channel_count, prefix_count) != (52, 416):
        raise ValueError("Unexpected number of output channels or phase prefixes")
    try:
        git_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        git_head = "unavailable"
    data = dict(
        schema_version=1, date="2026-09-26", git_head=git_head,
        method="Exact signed-weight interval bounds for independent full-range activations; eight global phase prefixes and all multiply/reduction-tree nodes checked; no tensor samples or simulation.",
        scope="Frozen ROM model and legal eight-phase pipeline transactions only. Does not preserve arbitrary unconstrained signed32 partial_sums as a generic module contract.",
        packing=dict(
            weight_flat="LSB element index = (output_channel*CIN+input_channel)*K*K+tap; signed int8 two-complement.",
            bias_flat="LSB element index = output_channel; signed int32 two-complement.",
            phase="output_channel=(phase//IN_GROUPS)*OUT_PAR+lane; input_channel=(phase%IN_GROUPS)*IN_PAR+input_lane; IN_GROUPS=CIN//IN_PAR.",
            activation="window_flat index = tap*CIN+input_channel; L1 zero extends uint8; L2-L5 sign extend int16.",
        ),
        rom_audit=audits,
        rtl_sources=[dict(
            path=p, sha256=sha((ROOT / p).read_bytes()),
            canonical_sha256=sha((ROOT / p).read_bytes().replace(b"\r\n", b"\n")),
        ) for p in RTL_PATHS],
        layers=layers,
        conclusion=dict(
            all_frozen_model_accumulation_fits_signed32=True,
            all_frozen_model_accumulation_fits_signed33=True,
            maximum_required_signed_bits=max(l["summary"]["all_arithmetic"]["required_signed_bits"] for l in layers),
            recommended_bias_addition="Even with signed32 accum/sum_stage, explicitly sign-extend both operands to signed33 for the bias addition before signed32 saturation; preserve latency and handshake. RTL changes require regression.",
            not_proven=["Timing benefit of shrinking accumulator", "Arbitrary signed32 partial input behavior",
                        "Any retrained/replaced ROM without reanalysis", "RTL equivalence after a future implementation edit"],
        ),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    for layer in layers:
        print(layer["name"], json.dumps(layer["summary"]))
    print("ROM_19_RELEASE_CANONICAL_PASS; WEIGHT_BIAS_10_DECODED_A_BINARY_SHA_PASS")
    print("ACC_FROZEN_MODEL_RANGE_PASS: output_channels=52 phase_prefixes=416 maximum_signed_bits=29")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"ACC_RANGE_ANALYSIS_ERROR: {error}") from error
