from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from member_a.verify import verify_delivery


if __name__ == "__main__":
    print(json.dumps(verify_delivery(ROOT), indent=2, ensure_ascii=False))
