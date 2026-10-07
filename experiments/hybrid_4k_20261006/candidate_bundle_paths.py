from __future__ import annotations

from pathlib import Path


def resolve_candidate_bundle_root(
    bundle_dir: Path,
    repo_root: Path,
    *,
    allow_published: bool = False,
) -> Path:
    """Accept ignored experiment data, or an explicitly allowed published A bundle."""
    root = bundle_dir.resolve()
    repository = repo_root.resolve()
    allowed_roots = [repository / ".data"]
    if allow_published:
        allowed_roots.append(
            repository / "experiments" / "hybrid_4k_20261006" / "candidate_delivery"
        )
    for allowed_root in allowed_roots:
        try:
            root.relative_to(allowed_root.resolve())
            return root
        except ValueError:
            continue
    allowed_text = ", ".join(str(path) for path in allowed_roots)
    raise ValueError(f"Candidate bundle must be under one of: {allowed_text}; got {root}")
