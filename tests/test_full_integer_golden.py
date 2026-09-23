from pathlib import Path
import hashlib
import json
import zlib

import numpy as np

from member_a.fixed_reference import FixedReference


ROOT = Path(__file__).resolve().parents[1]


def test_iter_outputs_matches_run():
    reference = FixedReference(ROOT / "artifacts" / "quant")
    image = np.arange(6 * 8, dtype=np.uint8).reshape(6, 8)
    streamed = dict(reference.iter_outputs(image))
    collected = reference.run(image)
    assert list(streamed) == list(collected)
    for name in streamed:
        assert np.array_equal(streamed[name], collected[name])


def test_full_integer_golden_contract_and_hashes():
    golden_dir = ROOT / "artifacts" / "full_integer_golden"
    manifest = json.loads((golden_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "A_CONFIRMED_INTEGER_GOLDEN"
    assert manifest["golden_class"] == "full_frame_integer_bit_exact"
    assert manifest["stage_digests"]["output"]["shape_hwc"] == [1080, 1920, 1]
    assert manifest["stage_digests"]["output"]["dtype"] == "uint8"

    for filename, expected in manifest["files"].items():
        data = (golden_dir / filename).read_bytes()
        assert len(data) == expected["bytes"]
        assert f"{zlib.crc32(data) & 0xFFFFFFFF:08x}" == expected["crc32"]
        assert hashlib.sha256(data).hexdigest() == expected["sha256"]

    raw_input = (golden_dir / "input_960x540_y_u8.bin").read_bytes()
    rom = (golden_dir / "input_rom_2p19_u8.bin").read_bytes()
    assert len(raw_input) == 960 * 540
    assert len(rom) == 1 << 19
    assert rom[: len(raw_input)] == raw_input
    assert set(rom[len(raw_input) :]) <= {0}
    assert (golden_dir / manifest["authoritative_output"]).stat().st_size == 1920 * 1080
