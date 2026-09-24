from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from member_a.data import download_datasets


if __name__ == "__main__":
    print(download_datasets(ROOT / ".data"))
