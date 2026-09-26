"""Collect completed timing runs without changing source or Git state."""
from pathlib import Path
import hashlib, json, re, shutil, sys
ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / 'experiments/timing_margin_20260926'
CASES = {
 'forcefifo': ('acc36_realrom_150_member_b_forcefifo0926_ascii_ramdecomp','synth_forcefifo.tcl'),
 'setup030': ('acc36_realrom_150_member_b_setup0300926_ascii_ramdecomp','synth_setup030.tcl'),
 'multi_target': ('margin0926_multi_target','route_physical_branch.tcl'),
 'route_setup030': ('margin0926_route_setup030','route_setup030.tcl'),
 'srl': ('acc36_realrom_150_member_b_srl0926_ascii_ramdecomp','synth_srl.tcl'),
}
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def collect(name):
 stage,script=CASES[name]
 src=ROOT/'_synth_bc'/stage/'reports'
 dst=ROOT/'member_b_evidence/timing_margin_20260926'/name
 timing=(src/'timing_summary_postroute.rpt').read_text()
 route=(src/'route_status.rpt').read_text()
 util=(src/'utilization_postroute.rpt').read_text()
 values=re.search(r'WNS\(ns\)[^\n]*\n[^\n]*\n\s*([^\n]+)',timing).group(1).split()
 errors=int(re.search(r'nets with routing errors\.+\s*:\s*(\d+)',route).group(1))
 first=re.search(r'Slack \((?:MET|VIOLATED)\)\s*:[\s\S]*?(?=Location\s+Delay type)',timing).group(0)
 resource={}
 for key,pattern in [('LUT',r'\|\s*Slice LUTs\*?\s*\|\s*(\d+)'),('FF',r'\|\s*Slice Registers\s*\|\s*(\d+)'),('RAMB36',r'\|\s*RAMB36/FIFO\*?\s*\|\s*(\d+)'),('RAMB18',r'\|\s*RAMB18\s*\|\s*(\d+)'),('DSP',r'\|\s*DSPs\*?\s*\|\s*(\d+)')]:
  resource[key]=int(re.search(pattern,util).group(1))
 summary=dict(candidate=name,WNS=float(values[0]),TNS=float(values[1]),WHS=float(values[4]),THS=float(values[5]),route_errors=errors,resources=resource,worst_path=first.strip())
 dst.mkdir(parents=True,exist_ok=True)
 for f in src.iterdir():
  if f.is_file():shutil.copy2(f,dst/f.name)
 (dst/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 paths=[]
 filelist=src/'source_files.txt'
 if not filelist.exists():
  parent='setup030' if name=='route_setup030' else 'forcefifo'
  filelist=ROOT/'_synth_bc'/CASES[parent][0]/'reports/source_files.txt'
 for line in filelist.read_text().splitlines():paths.append(ROOT/line.removeprefix('V:').lstrip('/'))
 paths+=list((ROOT/'rom/member_a_d16_s8_m1_c16').glob('*_packed.mem'))
 paths+=list((ROOT/'member_b_evidence/real_banks').glob('rom_bank_*.mem'))
 paths.append(EXPERIMENT/script)
 manifest=[dict(path=f.relative_to(ROOT).as_posix(),sha256=sha(f),bytes=f.stat().st_size) for f in paths]
 if name=='route_setup030':
  sf=EXPERIMENT/'synth_setup030.tcl'
  manifest.append(dict(path=sf.relative_to(ROOT).as_posix(),sha256=sha(sf),bytes=sf.stat().st_size))
  f=ROOT/'_synth_bc/acc36_realrom_150_member_b_setup0300926_ascii_ramdecomp/placed_setup030.dcp'
  manifest.append(dict(path=f.relative_to(ROOT).as_posix(),sha256=sha(f),bytes=f.stat().st_size))
 if name=='multi_target':
  sf=EXPERIMENT/'synth_forcefifo.tcl'
  manifest.append(dict(path=sf.relative_to(ROOT).as_posix(),sha256=sha(sf),bytes=sf.stat().st_size))
  f=ROOT/'_synth_bc/acc36_realrom_150_member_b_forcefifo0926_ascii_ramdecomp/base_postphys.dcp'
  manifest.append(dict(path=f.relative_to(ROOT).as_posix(),sha256=sha(f),bytes=f.stat().st_size))
 (dst/'source_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in summary.items() if k!='worst_path'}))
args=sys.argv[1:]
for name in args:
 if name!='--verify-preserved':collect(name)
# Local preservation audit is optional: another clone does not contain the
# original workstation's unrelated, untracked diagnostic files.
if '--verify-preserved' in args:
 old=json.loads((EXPERIMENT/'preserved_existing_files.json').read_text())
 changed=[p for p,h in old.items() if not (ROOT/p).exists() or sha(ROOT/p)!=h]
 if changed:raise RuntimeError('Pre-existing files missing or changed: '+str(changed))
 print('PRESERVED_EXISTING_FILES_PASS')
