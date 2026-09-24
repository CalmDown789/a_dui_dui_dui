from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import torch
from torch import nn


@dataclass(frozen=True)
class ModelConfig:
    scale: int = 2
    d: int = 16
    s: int = 8
    m: int = 1
    c: int = 16
    input_width: int = 960
    input_height: int = 540

    def __post_init__(self) -> None:
        if self.scale != 2:
            raise ValueError("This delivery freezes scale=2")
        if self.c != self.d:
            raise ValueError("This delivery freezes c=d for the expanding layer")
        if min(self.d, self.s, self.m, self.c) <= 0:
            raise ValueError("Channel counts and mapping depth must be positive")

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class FSRCNNSubpixel(nn.Module):
    """FSRCNN trunk with a native dense 5x5 subpixel x2 output head.

    This is deliberately not represented as a decomposed 9x9 transposed
    convolution.  The dense 16->4 head is trained directly and its four output
    channels map to the 2x2 pixel-shuffle phases TL, TR, BL and BR.
    """

    def __init__(self, config: ModelConfig | None = None) -> None:
        super().__init__()
        self.config = config or ModelConfig()
        cfg = self.config
        self.feature = nn.Conv2d(1, cfg.d, kernel_size=5, padding=2)
        self.feature_act = nn.PReLU(cfg.d)
        self.shrink = nn.Conv2d(cfg.d, cfg.s, kernel_size=1)
        self.shrink_act = nn.PReLU(cfg.s)
        self.mapping = nn.ModuleList(
            [nn.Conv2d(cfg.s, cfg.s, kernel_size=3, padding=1) for _ in range(cfg.m)]
        )
        self.mapping_act = nn.ModuleList([nn.PReLU(cfg.s) for _ in range(cfg.m)])
        self.expand = nn.Conv2d(cfg.s, cfg.c, kernel_size=1)
        self.expand_act = nn.PReLU(cfg.c)
        self.subpixel = nn.Conv2d(cfg.c, cfg.scale**2, kernel_size=5, padding=2)
        self.shuffle = nn.PixelShuffle(cfg.scale)
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


def mac_breakdown(config: ModelConfig | None = None) -> dict[str, int | float]:
    cfg = config or ModelConfig()
    pixels = cfg.input_width * cfg.input_height
    values: dict[str, int | float] = {
        "feature": pixels * 1 * cfg.d * 5 * 5,
        "shrink": pixels * cfg.d * cfg.s,
        "mapping": pixels * cfg.m * cfg.s * cfg.s * 3 * 3,
        "expand": pixels * cfg.s * cfg.c,
        "subpixel": pixels * cfg.c * (cfg.scale**2) * 5 * 5,
    }
    total = int(sum(int(value) for value in values.values()))
    values["total"] = total
    values["gmac_per_frame"] = total / 1.0e9
    values["gmac_per_second_30fps"] = total * 30 / 1.0e9
    values["margin_vs_133_2_gmac_s"] = 133.2 / (total * 30 / 1.0e9)
    return values
