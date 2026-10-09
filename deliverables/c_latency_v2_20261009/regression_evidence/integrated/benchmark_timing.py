"""Six interleaved rounds, three variants, frozen data, isolated imports."""
from pathlib import Path
import json,statistics,subprocess,sys,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
run=ROOT/'validation/benchmark_runs'/str(time.time_ns());run.mkdir(parents=True)
variants=['step03_full','step04_full','step04_sampled'];rows=[]
for lap in range(6):
    order=variants[lap%3:]+variants[:lap%3]
    if lap>=3:order=list(reversed(order))
    for variant in order:
        out=run/f'{lap}_{variant}'
        done=subprocess.run([sys.executable,'-B',str(ROOT/'validation/benchmark_worker.py'),variant,str(out)],capture_output=True,text=True)
        (run/f'{lap}_{variant}.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8')
        if done.returncode:raise RuntimeError('benchmark failed; preserved '+str(out))
        r=json.loads((out/'BENCHMARK.json').read_text());assert r['status']=='PASS'
        r['lap']=lap;rows.append(r)
    print('TIMING_BENCHMARK_ROUND='+str(lap)+' PASS',flush=True)
wall={v:statistics.median(r['wall_ns']for r in rows if r['variant']==v)for v in variants}
cpu={v:statistics.median(r['calling_thread_cpu_ns']for r in rows if r['variant']==v)for v in variants}
samples={v:statistics.median(r['fine_timing_samples']for r in rows if r['variant']==v)for v in variants}
result=dict(status='PASS',rounds=6,rows=rows,median_two_frame_wall_ns=wall,median_calling_thread_cpu_ns=cpu,
    median_fine_timing_samples=samples,sampled_wall_reduction_vs_step04_full_percent=100*(1-wall['step04_sampled']/wall['step04_full']),
    sampled_wall_reduction_vs_step03_full_percent=100*(1-wall['step04_sampled']/wall['step03_full']),
    scope='MEMORY_PEER_CLIENT_AND_PEER_CPU_COMPLETE_DIAGNOSTIC_VS_SAMPLED_NOT_REAL_SOCKET_BOARD_OR_FPS',
    frame_and_raw_journal_sampling=False,real_windows_select_exercised=False,socket_created=False)
(ROOT/'TIMING_BENCHMARK.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(status='PASS',median_wall_ns=wall,median_cpu_ns=cpu,reduction_vs_step04_full_percent=result['sampled_wall_reduction_vs_step04_full_percent'])))
