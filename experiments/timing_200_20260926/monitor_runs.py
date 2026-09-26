"""Read-only compact progress for this experiment's existing jobs."""
from pathlib import Path
from datetime import datetime
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
print(datetime.now().strftime('%H:%M:%S'))
for name in ('pipeline000', 'pipeline030', 'pipeline2_030', 'pipeline6_030'):
    text = (HERE / f'{name}.log').read_text(encoding='utf-8', errors='replace')
    phases = re.findall(r'^Phase [^\r\n]+', text, re.M)
    ended = re.findall(r'^INFO: \[Common 17-206\] Exiting Vivado[^\r\n]+', text, re.M)
    errors = re.findall(r'^ERROR: [^\r\n]+', text, re.M)
    value = ended[-1] if ended else phases[-1] if phases else 'starting'
    print(f'{name}: {value}' + (f'; {errors[-1]}' if errors else ''))
sim = ROOT / '_sim_l5_member_b_acc36_pipeline200_v6/tb_b_real_full/xsim.log'
if sim.exists():
    lines = sim.read_text(encoding='utf-8', errors='replace').splitlines()
    status = [x.strip() for x in lines if 'progress:' in x or 'RESULT:' in x]
    print('V6 full: ' + (status[-1] if status else 'starting'))
for name in ('postroute200_v2_pressure000_try2', 'postroute200_v1_pressure000_try1'):
    log = ROOT / '_synth_bc' / name / 'vivado.log'
    if not log.exists():
        continue
    text = log.read_text(encoding='utf-8', errors='replace')
    phases = re.findall(r'^Phase [^\r\n]+', text, re.M)
    ended = re.findall(r'^INFO: \[Common 17-206\] Exiting Vivado[^\r\n]+', text, re.M)
    print(name + ': ' + (ended[-1] if ended else phases[-1] if phases else 'starting'))
