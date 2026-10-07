import json
from copy import deepcopy
from pathlib import Path

import pytest
import numpy as np

from experiments.hybrid_4k_20261006.candidate_bundle_paths import (
    resolve_candidate_bundle_root,
)
from experiments.hybrid_4k_20261006.verify_candidate_bundle import (
    _coe_words,
    _hex_words,
    _verify_manifest_coverage,
    _verify_model_contract,
)


def test_candidate_bundle_path_allows_data_directory_by_default(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    bundle = repo / ".data" / "run" / "candidate"
    bundle.mkdir(parents=True)

    assert resolve_candidate_bundle_root(bundle, repo) == bundle.resolve()


def test_candidate_bundle_path_requires_flag_for_published_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    bundle = (
        repo
        / "experiments"
        / "hybrid_4k_20261006"
        / "candidate_delivery"
        / "candidate"
    )
    bundle.mkdir(parents=True)

    with pytest.raises(ValueError, match="Candidate bundle must be under"):
        resolve_candidate_bundle_root(bundle, repo)
    assert resolve_candidate_bundle_root(bundle, repo, allow_published=True) == bundle.resolve()


def test_candidate_bundle_path_rejects_arbitrary_external_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    external = tmp_path / "external" / "candidate"
    external.mkdir(parents=True)

    with pytest.raises(ValueError, match="Candidate bundle must be under"):
        resolve_candidate_bundle_root(external, repo, allow_published=True)


def test_mem_and_coe_signed_hex_words_use_twos_complement(tmp_path: Path) -> None:
    values = np.array([-32768, -1, 0, 1, 32767], dtype=np.int16)
    expected = ["8000", "FFFF", "0000", "0001", "7FFF"]
    assert _hex_words(values, 16) == expected

    coe_path = tmp_path / "values.coe"
    coe_path.write_text(
        "memory_initialization_radix=16;\n"
        "memory_initialization_vector=\n"
        + ",\n".join(expected)
        + ";\n",
        encoding="ascii",
    )
    assert _coe_words(coe_path) == expected


def test_manifest_rejects_unlisted_files(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "declared.bin").write_bytes(b"listed")
    (bundle / "unexpected.bin").write_bytes(b"not in manifest")

    with pytest.raises(AssertionError, match=r"unlisted=\['unexpected.bin'\]"):
        _verify_manifest_coverage(bundle, {"files": {"declared.bin": {}}})


def test_published_candidate_matches_frozen_architecture_contract() -> None:
    repo = Path(__file__).resolve().parents[3]
    spec_path = (
        repo
        / "experiments"
        / "hybrid_4k_20261006"
        / "candidate_delivery"
        / "R0_QAT456_seed456_20261007"
        / "quant"
        / "quant_params.json"
    )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    _verify_model_contract(spec)

    changed = deepcopy(spec)
    changed["layers"][0]["padding"] = [0, 0]
    with pytest.raises(AssertionError, match="Candidate layer contract mismatch for feature"):
        _verify_model_contract(changed)
