from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out = repo_root / ".data" / "hybrid_4k_20261006" / "synthetic_source"
    out.mkdir(parents=True, exist_ok=True)
    y, x = np.ogrid[:2160, :3840]
    checker = ((x // 40 + y // 36) & 1) * 37
    luminance = (x * 3 + y * 5 + checker) % 256
    rgb = np.empty((2160, 3840, 3), dtype=np.uint8)
    rgb[..., 0] = luminance.astype(np.uint8)
    rgb[..., 1] = ((x * 5 + y * 2) % 256).astype(np.uint8)
    rgb[..., 2] = ((x + y * 7 + checker) % 256).astype(np.uint8)
    path = out / "synthetic_pattern_3840x2160.png"
    Image.fromarray(rgb, mode="RGB").save(path, optimize=False)
    print(path)


if __name__ == "__main__":
    main()
