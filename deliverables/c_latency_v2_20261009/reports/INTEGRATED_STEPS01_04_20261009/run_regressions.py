from pathlib import Path
import importlib.util, json, os, re, shutil, subprocess, sys
sys.dont_write_bytecode = True
REVIEW = Path(__file__).resolve().parent
WORK = REVIEW.parents[1]
ROOT = Path(r'C:\t6int09')
STEP4 = WORK/'output/HOST_STEP04_SAMPLED_TIMING_20261009'
VALIDATION = ROOT/'validation'; VALIDATION.mkdir(exist_ok=False)
(ROOT/'main/proof').mkdir()
for name in ('host_regression.py','check_host_window128.py'):
    shutil.copy2(STEP4/'main/proof'/name,ROOT/'main/proof'/name)
for p in (STEP4/'validation').glob('*.py'):
    text=p.read_text(encoding='utf-8').replace(str(STEP4),str(ROOT))
    (VALIDATION/p.name).write_text(text,encoding='utf-8')
env=os.environ.copy();env['STEP03_IO_MODE']='nonblocking';env['STEP04_TIMING_MODE']='sampled'
rows=[]
for name in ('check_sampler.py','check_nonblocking.py','check_transfer_backpressure.py','run_host_regression.py','run_window128.py','protocol_edge_regression.py'):
    print('REGRESSION_START='+name,flush=True)
    with (VALIDATION/(name+'.log')).open('wb') as log:
        p=subprocess.run([sys.executable,'-B',str(VALIDATION/name)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    rows.append(dict(name=name,exit_code=p.returncode,log=str(VALIDATION/(name+'.log'))))
    (REVIEW/'HOST_REGRESSION.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print((VALIDATION/(name+'.log')).read_text(encoding='utf-8',errors='replace')[-1000:],flush=True)
    assert p.returncode==0,name
# Reuse the source-bound directed test helper with new output paths, without rerunning preparation.
old=WORK/'output/RTL_STEP01_RETRY_20261009/run_step01.py'
spec=importlib.util.spec_from_file_location('rtl_test_helper',old);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.HERE=VALIDATION/'rtl_tests';m.HERE.mkdir()
fixture=(WORK/'comm_c_20261008_operator/duplicate_output_candidate_20261009/tb_duplicate_suppression.sv').read_text()
fixture=fixture.replace('"FIXTURE_TIMEOUT"','"FIXTURE_TIMEOUT base=%0d next=%0d retry_requested=%0d retry_pass=%0d retries=%0d",base,next_q,dut.retry_requested_q,dut.retry_pass_q,retries')
fixture=fixture.replace('cycles<=cycles+1;', 'cycles<=cycles+1;\n  if(dut.active&&dut.retry_timer_q==RETRY-1&&!desc_valid&&dut.scan_q>=next_q)\n   $display("EXPIRY_COLLISION cycle=%0d base=%0d next=%0d retry_requested=%0d retry_pass=%0d",cycles,base,next_q,dut.retry_requested_q,dut.retry_pass_q);')
for key,value in dict(RETRY=3000000,ACK_DELAY=40000,LOST_PROOF=1).items():
    fixture,n=re.subn(r'\b'+key+r'=\d+',key+'='+str(value),fixture,count=1);assert n==1
attempt=m.HERE/'cases'
m.run_case(attempt,'old_collision_fails',Path(r'C:\t6dup09\main\rtl\evf2_result_window.sv'),'tb_duplicate_suppression',fixture,True)
m.run_case(attempt,'integrated_collision_recovers',ROOT/'main/rtl/evf2_result_window.sv','tb_duplicate_suppression',fixture)
m.run_case(attempt,'integrated_slot_ownership',ROOT/'main/rtl/evf2_result_window.sv','tb_ack_reuse',Path(r'C:\t6dup09\main\proof\tb_ack_reuse.sv').read_text())
m.report['status']='PASS_INTEGRATED_DIRECTED_RTL_REGRESSION'
m.save(m.HERE/'REGRESSION.json',m.report)
shutil.copy2(m.HERE/'REGRESSION.json',REVIEW/'RTL_REGRESSION.json')
print('ALL_INTEGRATED_REGRESSIONS_PASS',flush=True)
