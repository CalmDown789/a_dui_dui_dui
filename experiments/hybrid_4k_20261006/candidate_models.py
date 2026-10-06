from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import torch
from torch import nn


@dataclass(frozen=True)
class CandidateConfig:
    name: str
    d: int
    s: int
    m: int
    c: int
    head_kernel: int
    input_width: int = 960
    input_height: int = 540
    scale: int = 2

    def __post_init__(self) -> None:
        if self.scale != 2:
            raise ValueError("This hybrid plan fixes the CNN scale at x2")
        if min(self.d, self.s, self.m, self.c) <= 0:
            raise ValueError("d, s, m and c must be positive")
        if self.head_kernel not in (3, 5):
            raise ValueError("The planned output-head kernels are 3x3 or 5x5")
        if self.input_width <= 0 or self.input_height <= 0:
            raise ValueError("Input dimensions must be positive")

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


PRESETS: dict[str, CandidateConfig] = {
    "R0": CandidateConfig("R0", d=16, s=8, m=1, c=16, head_kernel=5),
    "R1": CandidateConfig("R1", d=16, s=8, m=1, c=16, head_kernel=3),
    "R2": CandidateConfig("R2", d=16, s=8, m=1, c=8, head_kernel=5),
    "R3": CandidateConfig("R3", d=16, s=8, m=1, c=8, head_kernel=3),
    "R4": CandidateConfig("R4", d=16, s=4, m=1, c=8, head_kernel=3),
    "R5": CandidateConfig("R5", d=8, s=4, m=1, c=8, head_kernel=3),
}


class HybridFSRCNN(nn.Module):
    """Independent candidate model; never changes the released Member A class."""

    def __init__(self, config: CandidateConfig) -> None:
        super().__init__()
        self.config = config
        pad_head = config.head_kernel // 2
        self.feature = nn.Conv2d(1, config.d, kernel_size=5, padding=2)
        self.feature_act = nn.PReLU(config.d)
        self.shrink = nn.Conv2d(config.d, config.s, kernel_size=1)
        self.shrink_act = nn.PReLU(config.s)
        self.mapping = nn.ModuleList(
            [nn.Conv2d(config.s, config.s, kernel_size=3, padding=1) for _ in range(config.m)]
        )
        self.mapping_act = nn.ModuleList([nn.PReLU(config.s) for _ in range(config.m)])
        self.expand = nn.Conv2d(config.s, config.c, kernel_size=1)
        self.expand_act = nn.PReLU(config.c)
        self.subpixel = nn.Conv2d(config.c, 4, kernel_size=config.head_kernel, padding=pad_head)
        self.shuffle = nn.PixelShuffle(config.scale)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        for layer in [self.feature, self.shrink, *self.mapping, self.expand]:
            nn.init.normal_(
                layer.weight,
                mean=0.0,
                std=math.sqrt(2.0 / (layer.out_channels * layer.kernel_size[0] ** 2)),
            )
            nn.init.zeros_(layer.bias)
        nn.init.normal_(self.subpixel.weight, mean=0.0, std=0.001)
        nn.init.zeros_(self.subpixel.bias)

    def forward_with_intermediates(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        stages: dict[str, torch.Tensor] = {}
        x = self.feature_act(self.feature(x))
        stages["feature"] = x
        x = self.shrink_act(self.shrink(x))
        stages["shrink"] = x
        for index, (conv, act) in enumerate(zip(self.mapping, self.mapping_act, strict=True)):
            x = act(conv(x))
            stages[f"mapping{index}"] = x
        x = self.expand_act(self.expand(x))
        stages["expand"] = x
        phases = self.subpixel(x)
        stages["subpixel_phases"] = phases
        stages["output"] = self.shuffle(phases)
        return stages

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.forward_with_intermediates(x)["output"]


def mac_breakdown(config: CandidateConfig) -> dict[str, int | float | str]:
    pixels = config.input_width * config.input_height
    per_pixel = {
        "feature": 1 * config.d * 5 * 5,
        "shrink": config.d * config.s,
        "mapping": config.m * config.s * config.s * 3 * 3,
        "expand": config.s * config.c,
        "subpixel": config.c * (config.scale**2) * config.head_kernel**2,
    }
    total_per_pixel = sum(per_pixel.values())
    total_per_frame = pixels * total_per_pixel
    return {
        "name": config.name,
        "input_pixels": pixels,
        "mac_per_input_pixel": total_per_pixel,
        **{f"{name}_mac_per_frame": count * pixels for name, count in per_pixel.items()},
        "mac_per_frame": total_per_frame,
        "gmac_per_frame": total_per_frame / 1.0e9,
        "gmac_per_second_60fps": total_per_frame * 60 / 1.0e9,
        "output_width": config.input_width * config.scale,
        "output_height": config.input_height * config.scale,
    }
