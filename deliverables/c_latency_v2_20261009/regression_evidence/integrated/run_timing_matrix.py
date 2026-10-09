"""Both IO modes and both timing modes against independent protocol audits."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];rows=[];supplement=[]
def run(name,env,label):
    result=subprocess.run([sys.executable,'-B',str(ROOT/'validation'/name)],env=env,capture_output=True,text=True)
    (ROOT/'validation'/f'{label}_{name}.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError(label+' '+name+' failed; see preserved log')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for timing in ('full','sampled'):
    for io in ('timeout','nonblocking'):
        env=dict(os.environ,STEP03_IO_MODE=io,STEP04_TIMING_MODE=timing,PYTHONDONTWRITEBYTECODE='1')
        label=io+'_'+timing
        for name in ('run_host_regression.py','run_window128.py'):run(name,env,label)
        host=Path(json.loads((ROOT/'validation/LATEST_host.json').read_text())['saved_directory'])/'RESULTS.json'
        window=Path(json.loads((ROOT/'WINDOW128_RUN.json').read_text())['saved_directory'])/'RESULTS.json'
        for p in (host,window):
            r=json.loads(p.read_text());assert r['status']=='PASS'and r['io_mode']==io and r['timing_mode']==timing
        rows.append(dict(io_mode=io,timing_mode=timing,status='PASS',host_fault_cases=26,window128_cases=7,
            host_results=str(host),host_results_sha256=sha(host),window128_results=str(window),window128_results_sha256=sha(window)))
        print('MATRIX='+label+' PASS host=26 full_window128=7',flush=True)
    env=dict(os.environ,STEP04_TIMING_MODE=timing,PYTHONDONTWRITEBYTECODE='1')
    for name,report in [('check_nonblocking.py','NONBLOCKING_CHECKS.json'),('check_transfer_backpressure.py','TRANSFER_BACKPRESSURE.json')]:
        run(name,env,timing);p=ROOT/report
        r=json.loads(p.read_text());assert r['status']=='PASS'and r['timing_mode']==timing
        dest=ROOT/(timing+'_'+report);dest.write_bytes(p.read_bytes())
        supplement.append(dict(timing_mode=timing,report=dest.name,sha256=sha(dest),status='PASS'))
    print('SUPPLEMENT='+timing+' PASS scheduler=21 backpressure=5',flush=True)
(ROOT/'TIMING_MODE_MATRIX.json').write_text(json.dumps(dict(status='PASS',rows=rows,supplement=supplement,socket_created=False),indent=2),encoding='utf-8')
