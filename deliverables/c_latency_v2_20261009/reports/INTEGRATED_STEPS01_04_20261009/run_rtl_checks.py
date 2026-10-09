from pathlib import Path
import hashlib, re, shutil, sys, types
sys.dont_write_bytecode=True
REVIEW=Path(__file__).resolve().parent;WORK=REVIEW.parents[1]
ROOT=Path(r'C:\t6int09');VALIDATION=ROOT/'validation'
old=WORK/'output/RTL_STEP01_RETRY_20261009/run_step01.py'
# XSim 2025.2 debug-info generation crashed; disable debug metadata only.
source=old.read_text(encoding='utf-8');assert source.count("'--debug','typical'")==1
m=types.ModuleType('rtl_test_helper');m.__file__=str(old)
exec(compile(source.replace("'--debug','typical'","'--debug','off'"),str(old),'exec'),m.__dict__)
m.HERE=VALIDATION/'rtl_tests_debug_off';m.HERE.mkdir(exist_ok=False)
m.report.update(helper_original_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
                simulator_debug_mode='off', prior_tool_crash_preserved=str(VALIDATION/'rtl_tests'))
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
print('INTEGRATED_DIRECTED_RTL_PASS',flush=True)
