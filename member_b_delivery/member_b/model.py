from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class TinySR(nn.Module):
    """Three-layer x2 luminance super-resolution network.

    The two PReLU slopes are scalar trainable parameters.  This keeps the
    hardware contract small while still satisfying the task requirement to
    export PReLU parameters.
    """

    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(1, 8, kernel_size=3, stride=1, padding=1, bias=True)
        self.prelu1 = nn.PReLU(num_parameters=1, init=0.25)
        self.conv2 = nn.Conv2d(8, 16, kernel_size=3, stride=1, padding=1, bias=True)
        self.prelu2 = nn.PReLU(num_parameters=1, init=0.25)
        self.conv3 = nn.Conv2d(16, 4, kernel_size=3, stride=1, padding=1, bias=True)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        for layer in (self.conv1, self.conv2, self.conv3):
            nn.init.kaiming_normal_(layer.weight, a=0.25, mode="fan_in", nonlinearity="leaky_relu")
            nn.init.zeros_(layer.bias)

    def forward_features(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        l1 = self.prelu1(self.conv1(x))
        l2 = self.prelu2(self.conv2(l1))
        l3 = self.conv3(l2)
        return l1, l2, l3

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.clamp(self.forward_raw(x), 0.0, 1.0)

    def forward_raw(self, x: torch.Tensor) -> torch.Tensor:
        _, _, l3 = self.forward_features(x)
        return F.pixel_shuffle(l3, upscale_factor=2)


def model_contract() -> dict:
    return {
        "name": "TinySR-1x8x16x4-PS2",
        "input": {"shape_nchw": [1, 1, 360, 640], "color": "Y", "range": [0.0, 1.0]},
        "layers": [
            {"name": "conv1", "type": "conv2d", "in_channels": 1, "out_channels": 8, "kernel": 3, "stride": 1, "padding": 1},
            {"name": "prelu1", "type": "prelu", "parameters": 1},
            {"name": "conv2", "type": "conv2d", "in_channels": 8, "out_channels": 16, "kernel": 3, "stride": 1, "padding": 1},
            {"name": "prelu2", "type": "prelu", "parameters": 1},
            {"name": "conv3", "type": "conv2d", "in_channels": 16, "out_channels": 4, "kernel": 3, "stride": 1, "padding": 1},
            {"name": "pixel_shuffle", "type": "pixel_shuffle", "scale": 2},
        ],
        "output": {"shape_nchw": [1, 1, 720, 1280], "color": "Y", "range": [0.0, 1.0]},
        "weight_layout": "OIHW",
        "feature_dump_layout": "HWC_row_major",
        "convolution_semantics": "cross_correlation_zero_padding",
        "pixel_shuffle_channel_mapping": {"0": "top_left", "1": "top_right", "2": "bottom_left", "3": "bottom_right"},
    }
