"""Verify and copy the exact incremental reference into a new candidate stage."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
manifest=json.loads((ROOT/'experiments/timing_200_20261003/rom_pipeline/reference_manifest.json').read_text())
source=ROOT/manifest['source']
def check(path):
    data=path.read_bytes()
    assert len(data)==manifest['bytes'] and hashlib.sha256(data).hexdigest()==manifest['sha256'],str(path)
check(source)
destination=Path(sys.argv[1])
assert destination.parent.parent==ROOT/'_synth_bc',destination
assert not destination.exists(),'Refusing overwrite of reference snapshot'
shutil.copyfile(source,destination)
check(destination);check(source)
print('EXACT_INCREMENTAL_REFERENCE_COPIED_AND_VERIFIED')
