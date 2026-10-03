"""Preserve the SUBST path-guard failure, before repairing its helper."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
log=ROOT/'_synth_bc/rom_pipeline_inc_impl_20261003_try1.log'
content=log.read_text(encoding='utf-8',errors='replace')
assert 'assert destination.parent.parent' in content and 'AssertionError:' in content
assert 'INFO: [Common 17-206] Exiting Vivado' in content
assert '\nCommand: synth_design ' not in content
stage=ROOT/'_synth_bc/acc36_realrom_200_member_b_rom_pipeline_inc_20261003_setup030_ascii_ramdecomp'
assert not (stage/'reports/launch_source_manifest.json').exists()
out=ROOT/'member_b_evidence/timing_200_20261003/rom_reference_alias_guard_failure'
out.mkdir(exist_ok=False)
records=[]
for source in [log,HERE/'synth_rom_pipeline_inc.tcl',HERE/'verify_rom_reference.py',
               HERE/'prepare_rom_impl.py',stage/'reports/run_config.txt',stage/'reports/source_files.txt',Path(__file__)]:
    data=source.read_bytes(); rel=source.relative_to(ROOT).as_posix()
    target=out/'snapshots'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    records.append(dict(source=rel,archive=target.relative_to(out).as_posix(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
(out/'manifest.json').write_text(json.dumps(dict(kind='rom_reference_alias_guard_failure',files=records,
    note='Python resolved script ROOT to native F path but compared unresolved V destination. Guard refused before snapshot copy/synthesis; no timing result.'),indent=2)+'\n')
print('ROM_REFERENCE_ALIAS_GUARD_FAILURE_ARCHIVED')
