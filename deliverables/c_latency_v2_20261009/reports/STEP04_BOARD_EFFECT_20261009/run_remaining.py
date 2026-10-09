from pathlib import Path
import json, subprocess, sys
sys.dont_write_bytecode = True
ROOT = Path(r'C:\t6s4board09')
PACKAGE = Path(r'C:\t6dup09\main')
REVIEW = Path(__file__).resolve().parent
PY = sys.executable
cases = [(3, 'step04_sampled'), (4, 'step03_full'), (5, 'step04_sampled'), (6, 'step03_full')]
results = []
for index, variant in cases:
    case = ROOT / f'{index:02}_{variant}'
    case.mkdir(exist_ok=False)
    commands = [
        ('startup', [PY, '-B', str(PACKAGE/'scripts/capture_board_characterization.py'),
          '--manifest', str(PACKAGE/'image/BOARD_CHARACTERIZATION_MANIFEST.json'),
          '--issued-manifest-sha256', '6c05cd53e9f5a3b286ebd482c8592688af299cc46a90c9d5dbc4e307ea93e7ae',
          '--port', 'COM3', '--vivado-bat', r'E:\AMDTools2025\2025.2\Vivado\bin\vivado.bat',
          '--program-tcl', str(PACKAGE/'scripts/program_board_characterization.tcl'), '--out-dir', str(case/'startup')]),
        ('run', [PY, '-B', str(REVIEW/'run_board_case.py'), '--variant', variant,
          '--startup', str(case/'startup/REPORT.json'), '--out', str(case/'run')]),
        ('audit', [PY, '-B', str(PACKAGE/'lab/audit_streaming_run.py'),
          '--run', str(case/'run'), '--out-dir', str(case/'audit')]),
    ]
    result = dict(case=str(case), variant=variant)
    for stage, command in commands:
        print(json.dumps(dict(event='START_STAGE', case=index, variant=variant, stage=stage)), flush=True)
        with (case/f'{stage}_console.log').open('w', encoding='utf-8') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        result[stage+'_exit_code'] = process.returncode
        print(json.dumps(dict(event='END_STAGE', case=index, stage=stage, exit_code=process.returncode)), flush=True)
        if process.returncode:
            print((case/f'{stage}_console.log').read_text(encoding='utf-8')[-2500:], flush=True)
            break
    if (case/'run/REPORT.json').exists():
        report = json.loads((case/'run/REPORT.json').read_text(encoding='utf-8'))
        result['frame_ms'] = [f['timing_ns']['whole']/1e6 for f in report['frames']]
        print(json.dumps(result), flush=True)
    results.append(result)
    (REVIEW/'REPEATED_RUNS.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    if result.get('startup_exit_code'):
        break
