"""Step 1 only: isolated RTL candidate and source-bound XSim regressions.

No socket, UART, hardware manager, BIT generation or live-package mutation.
"""
from pathlib import Path
import difflib, hashlib, json, os, re, shutil, subprocess, sys, time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
LIVE=Path(r'C:\t6dup09\main')
OLD_TESTS=WORK/'comm_c_20261008_operator/duplicate_output_candidate_20261009'
V=Path(r'E:\AMDTools2025\2025.2\Vivado')

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,data):Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def prepare():
    source=LIVE/'rtl/evf2_result_window.sv'
    assert sha(source)=='86932586c1f71f0e0713643a8b58bf42a2f6f62e25acfbfb43ed95ec7118c8cc'
    for folder in ['baseline','rtl','tests']: (HERE/folder).mkdir(exist_ok=True)
    (HERE/'baseline/evf2_result_window.sv').write_bytes(source.read_bytes())
    old=source.read_text(encoding='utf-8')
    needle='else if(scan_q>=next_q)begin scan_q<=base_q;retry_pass_q<=retry_requested_q;retry_requested_q<=0;end'
    assert old.count(needle)==1
    new=old.replace(needle,'''else if(scan_q>=next_q)begin
                        scan_q<=base_q;
                        // Consume both a queued retry and expiry on this edge.
                        // Clearing the queue must not discard a same-edge expiry.
                        retry_pass_q<=retry_requested_q||(retry_timer_q==RETRY_CYCLES-1);
                        retry_requested_q<=0;
                    end''')
    (HERE/'rtl/evf2_result_window.sv').write_text(new,encoding='utf-8')
    (HERE/'retry_expiry.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
        fromfile='baseline/evf2_result_window.sv',tofile='rtl/evf2_result_window.sv')),encoding='utf-8')
    dependencies=[]
    for rel in ['rtl/evf2_control_parser.sv','rtl/evf2_response_serializer.sv','rtl/pingpong_buffer.v','rtl/stripe_buffer.v',
                'proof/tb_ack_reuse.sv','proof/window_counter_guard/tb_window.sv',
                'data/ETHERNET_SEQUENCE_MANIFEST.json']:
        dependencies.append(dict(source=str(LIVE/rel),sha256=sha(LIVE/rel)))
    save(HERE/'SOURCE_MANIFEST.json',dict(status='ISOLATED_RETRY_EXPIRY_CANDIDATE_NOT_RUNTIME_RELEASE',
        baseline_source=str(source),baseline_sha256=sha(source),candidate_sha256=sha(HERE/'rtl/evf2_result_window.sv'),
        changes=['retry scan end consumes old queued request OR same-cycle expiry'],
        frozen_dependencies=dependencies,board_tested=False,BIT_generated=False,
        paired_main_manifest_sha256=sha(LIVE/'PACKAGE_MANIFEST.json'),
        live_bit_sha256=sha(LIVE/'image/COMM_window128_150_lab_candidate.bit')))

def run_case(attempt,name,src,top,tb,expected_failure=False):
    run=attempt/name;run.mkdir(parents=True,exist_ok=False)
    shutil.copy2(src,run/'evf2_result_window.sv')
    (run/(top+'.sv')).write_text(tb,encoding='ascii')
    (run/'run.tcl').write_text('run all\nquit\n',encoding='ascii')
    row=dict(name=name,status='RUNNING',expected_failure=expected_failure,run_directory=str(run),
             dut_sha256=sha(run/'evf2_result_window.sv'),tb_sha256=sha(run/(top+'.sv')),commands=[])
    report['cases'].append(row);save(HERE/'REGRESSION.json',report)
    print('CASE='+name,flush=True)
    env=os.environ.copy();env['PATH']=str(V/'lib/win64.o')+os.pathsep+env['PATH']
    cmds=[[str(V/'bin/xvlog.bat'),'-sv','evf2_result_window.sv',top+'.sv'],
          [str(V/'bin/xelab.bat'),'--debug','typical','--mt','off',top,'-s','snapshot'],
          [str(V/'bin/xsim.bat'),'snapshot','--tclbatch','run.tcl']]
    for i,cmd in enumerate(cmds):
        started=time.perf_counter()
        with (run/f'{i+1}.log').open('wb') as log:
            p=subprocess.run(cmd,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        text=(run/f'{i+1}.log').read_text(encoding='utf-8',errors='replace')
        row['commands'].append(dict(argv=cmd,exit_code=p.returncode,seconds=time.perf_counter()-started))
        save(HERE/'REGRESSION.json',report)
        if i==2 and expected_failure:
            assert 'Fatal: FIXTURE_TIMEOUT' in text and 'base=1' in text and 'retry_requested=0 retry_pass=0' in text,text[-2500:]
            row.update(status='EXPECTED_RTL_FAILURE_REPRODUCED',evidence=[s for s in text.splitlines() if 'EXPIRY_COLLISION' in s or 'Fatal:' in s])
        else:
            assert p.returncode==0 and 'Fatal:' not in text and 'ERROR:' not in text,text[-2500:]
    if not expected_failure:
        marker={'tb_ack_reuse':'ACK_REUSE_PASS','tb_retry_age_and_stale_ack':'AGE_GUARD_CAUSAL_PASS',
                'tb_retry_priority':'RETRY_PRIORITY_PASS'}.get(top,'DUPLICATE_SUPPRESSION_PASS')
        assert marker in text,text[-2500:]
        row.update(status='PASS',evidence=[s for s in text.splitlines() if marker in s or 'EXPIRY_COLLISION' in s])
    save(HERE/'REGRESSION.json',report);print('RESULT='+row['status'],flush=True)

def main():
    prepare()
    attempt=HERE/'runs'/time.strftime('%Y%m%dT%H%M%S',time.gmtime())
    fixture=(OLD_TESTS/'tb_duplicate_suppression.sv').read_text()
    fixture=fixture.replace('"FIXTURE_TIMEOUT"','"FIXTURE_TIMEOUT base=%0d next=%0d retry_requested=%0d retry_pass=%0d retries=%0d",base,next_q,dut.retry_requested_q,dut.retry_pass_q,retries')
    fixture=fixture.replace('cycles<=cycles+1;', '''cycles<=cycles+1;
  if(dut.active&&dut.retry_timer_q==RETRY-1&&!desc_valid&&dut.scan_q>=next_q)
   $display("EXPIRY_COLLISION cycle=%0d base=%0d next=%0d retry_requested=%0d retry_pass=%0d",cycles,base,next_q,dut.retry_requested_q,dut.retry_pass_q);''')
    cases=[
        ('baseline_loss_actual20ms',True,dict(RETRY=3000000,ACK_DELAY=40000,LOST_PROOF=1)),
        ('healthy_actual20ms',False,dict(RETRY=3000000,ACK_DELAY=300000)),
        ('loss_actual20ms',False,dict(RETRY=3000000,ACK_DELAY=40000,LOST_PROOF=1)),
        ('loss_rto_plus1',False,dict(RETRY=3000001,ACK_DELAY=40000,LOST_PROOF=1)),
        ('loss_rto_plus2',False,dict(RETRY=3000002,ACK_DELAY=40000,LOST_PROOF=1)),
        ('loss_clock_wrap_actual20ms',False,dict(RETRY=3000000,ACK_DELAY=40000,LOST_PROOF=1,CLOCK_WRAP=1)),
        ('healthy_short_rto',False,dict(RETRY=150000,ACK_DELAY=40000)),
        ('loss_short_rto',False,dict(RETRY=150000,ACK_DELAY=40000,LOST_PROOF=1)),
    ]
    try:
        for name,baseline,params in cases:
            tb=fixture
            for key,value in params.items():
                tb,n=re.subn(r'\b'+key+r'=\d+',key+'='+str(value),tb,count=1);assert n==1
            run_case(attempt,name,HERE/('baseline' if baseline else 'rtl')/'evf2_result_window.sv',
                     'tb_duplicate_suppression',tb,baseline)
        run_case(attempt,'slot_ownership',HERE/'rtl/evf2_result_window.sv','tb_ack_reuse',
                 (LIVE/'proof/tb_ack_reuse.sv').read_text())
        tb=(OLD_TESTS.parent/'tb_retry_age_and_stale_ack.sv').read_text()
        tb=tb.replace('second_one_ns-first_one_ns>=999900','second_one_ns-first_one_ns<999900')
        tb=tb.replace('EXPECTED_GLOBAL_TIMER_WITHOUT_PER_PACKET_AGE','PER_PACKET_AGE_WAS_NOT_ENFORCED')
        tb=tb.replace('ORIGINAL_RTL_CAUSAL_PASS early_retry_and_atomic_stale_batch_reject',
                      'AGE_GUARD_CAUSAL_PASS bounded_retry_and_atomic_stale_batch_reject')
        run_case(attempt,'stale_batch_atomicity',HERE/'rtl/evf2_result_window.sv','tb_retry_age_and_stale_ack',tb)
        tb=(WORK/'output/C_B_ACK_SOLUTION_20261009/tb_retry_priority.sv').read_text()
        tb=tb.replace('wanted=$test$plusargs("fixed");','wanted=1;')
        run_case(attempt,'window128_priority',HERE/'rtl/evf2_result_window.sv','tb_retry_priority',tb)
        manifest=json.loads((HERE/'SOURCE_MANIFEST.json').read_text())
        assert sha(Path(manifest['baseline_source']))==manifest['baseline_sha256']
        assert sha(HERE/'rtl/evf2_result_window.sv')==manifest['candidate_sha256']
        assert all(sha(Path(x['source']))==x['sha256'] for x in manifest['frozen_dependencies'])
        report.update(status='PASS_LOCAL_DIRECTED_REGRESSION',runtime_sources_unchanged=True)
    except BaseException as exc:
        report.update(status='FAIL',error=repr(exc));raise
    finally:save(HERE/'REGRESSION.json',report)
    print('STEP01_LOCAL_REGRESSION='+report['status'],flush=True)

report=dict(status='RUNNING',scope='DIRECT_RETAINED_WINDOW_SYNTHETIC_DATA_NOT_FULL_CNN_PHY',
            cases=[],board_tested=False,BIT_generated=False)
if __name__=='__main__':main()
