"""Member A software deliverable for the ACX750-200T FSRCNN project."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .model import FSRCNNSubpixel, ModelConfig, mac_breakdown

__all__ = ["FSRCNNSubpixel", "ModelConfig", "mac_breakdown"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from . import model

        return getattr(model, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
