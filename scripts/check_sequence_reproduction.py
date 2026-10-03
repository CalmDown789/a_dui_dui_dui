"""Compare a fresh safe-directory generation with all published frame/stage bytes."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
from compare_board_sequence import load_manifest

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regenerated",type=Path,required=True)
    args = parser.parse_args()
    if not args.regenerated.is_file():
        if not (ROOT/".data/public_sequence/source.json").is_file():
            subprocess.run([sys.executable,str(ROOT/"scripts/prepare_public_sequence.py")],check=True)
        subprocess.run([sys.executable,str(ROOT/"scripts/generate_video_sequence.py"),"--output-dir",str(args.regenerated.parent)],check=True)
    published_path = ROOT/"artifacts/multiframe/manifest.json"
    published, regenerated = load_manifest(published_path),load_manifest(args.regenerated)
    assert published["frame_count"] == regenerated["frame_count"] == 8
    for old,new in zip(published["frames"],regenerated["frames"]):
        assert old["frame_id"] == new["frame_id"]
        assert old["stage_digests"] == new["stage_digests"]
        for key in ("input","golden"):
            assert (published_path.parent/old[key]["path"]).read_bytes() == (args.regenerated.parent/new[key]["path"]).read_bytes()
    report = {"status":"PASS","all_frames":8,"all_stage_digests_match":True,"final_bytes_identical":True,
              "generation":regenerated["generation"],"board_capture_tested":False,
              "command":["python","scripts/generate_video_sequence.py","--output-dir",str(args.regenerated.parent)],
              "verification_command":["python","scripts/check_sequence_reproduction.py","--regenerated",str(args.regenerated)]}
    (ROOT/"artifacts/multiframe/generation_summary.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(report,indent=2))
