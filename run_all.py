from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from member_a.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and export the ACX750 Member A delivery")
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data")
    parser.add_argument("--max-epochs", type=int, default=50)
    parser.add_argument("--min-epochs", type=int, default=20)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--force-train", action="store_true")
    args = parser.parse_args()
    result = run_pipeline(
        ROOT,
        args.data_dir,
        max_epochs=args.max_epochs,
        min_epochs=args.min_epochs,
        patience=args.patience,
        force_train=args.force_train,
    )
    print(result)


if __name__ == "__main__":
    main()
