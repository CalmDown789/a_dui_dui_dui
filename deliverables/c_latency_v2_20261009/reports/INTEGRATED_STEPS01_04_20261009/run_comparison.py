from pathlib import Path
import json, subprocess, sys
sys.dont_write_bytecode=True
ROOT=Path(r'C:\t6int09\comparisons');ROOT.mkdir(exist_ok=False)
packages=dict(original=Path(r'C:\t6dup09\main'),integrated=Path(r'C:\t6int09\main'))
rows=[]
for index,variant in enumerate(['original','integrated']*3):
    package=packages[variant];case=ROOT/f'{index:02}_{variant}';case.mkdir()
    selection=json.loads((package/'LAB_FUNCTIONAL_SELECTION.json').read_text(encoding='utf-8'))
    commands=[('startup',[sys.executable,'-B',str(package/'scripts/capture_board_characterization.py'),
        '--manifest',str(package/selection['characterization_manifest']['file']),
        '--issued-manifest-sha256',selection['characterization_manifest']['sha256'],
        '--port','COM3','--vivado-bat',r'E:\AMDTools2025\2025.2\Vivado\bin\vivado.bat',
        '--program-tcl',str(package/'scripts/program_board_characterization.tcl'),'--out-dir',str(case/'startup')]),
        ('run',[sys.executable,'-B',str(package/'lab/streaming_board_lab.py'),
        '--mode','Natural2','--startup-capture-report',str(case/'startup/REPORT.json'),'--out-dir',str(case/'run'),'--output-window','128']),
        ('audit',[sys.executable,'-B',str(package/'lab/audit_streaming_run.py'),
        '--run',str(case/'run'),'--out-dir',str(case/'audit')])]
    row=dict(variant=variant,path=str(case),runtime='original timeout/full'if variant=='original'else'integrated nonblocking/sampled16')
    for stage,command in commands:
        print(json.dumps(dict(event='COMPARISON_STAGE',index=index,variant=variant,stage=stage)),flush=True)
        with (case/(stage+'.log')).open('wb')as log:
            p=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        row[stage+'_exit_code']=p.returncode
        if p.returncode:
            print((case/(stage+'.log')).read_text(encoding='utf-8',errors='replace')[-2000:],flush=True)
            break
    if (case/'run/REPORT.json').exists():
        report=json.loads((case/'run/REPORT.json').read_text(encoding='utf-8'))
        frames=json.loads((case/'run/traffic/FRAMES.json').read_text(encoding='utf-8'))if (case/'run/traffic/FRAMES.json').exists()else report.get('frames',[])
        row.update(frame_ms=[f['timing_ns']['whole']/1e6 for f in frames],frames=frames,
            retries=report.get('retries'),ignored=report.get('ignored'),protocol_loop_wall_ns=report.get('protocol_loop_wall_ns'),
            candidate_BIT_sha256=report['candidate_BIT_sha256'])
    if (case/'audit/AUDIT.json').exists():row['audit']=json.loads((case/'audit/AUDIT.json').read_text(encoding='utf-8'))
    rows.append(row)
    (Path(__file__).resolve().parent/'COMPARISON_RUNS.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in row.items()if k not in ('audit','frames')},indent=2),flush=True)
    if row.get('startup_exit_code'):break
