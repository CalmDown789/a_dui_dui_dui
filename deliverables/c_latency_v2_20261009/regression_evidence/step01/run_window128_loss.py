"""Additional actual-20ms loss checks with all 128 slots negotiated."""
from pathlib import Path
import json,time,sys
sys.dont_write_bytecode=True
import run_step01 as r

def main():
    main_report=json.loads((r.HERE/'REGRESSION.json').read_text())
    assert main_report['status']=='PASS_LOCAL_DIRECTED_REGRESSION'
    r.report=main_report
    base=(r.OLD_TESTS/'tb_duplicate_suppression.sv').read_text()
    base=base.replace('ACK_DELAY=300000','ACK_DELAY=40000')
    base=base.replace('LOST_PROOF=0','LOST_PROOF=1')
    base=base.replace('.MAX_WINDOW(2)','.MAX_WINDOW(128)').replace('.control_window(8\'d2)', '.control_window(8\'d128)')
    attempt=r.HERE/'runs'/('window128_loss_'+time.strftime('%Y%m%dT%H%M%S',time.gmtime()))
    try:
        for name,q in [('loss_first',0),('loss_middle',1),('loss_tail',3)]:
            tb=base.replace('LOST_PROOF&&q==1','LOST_PROOF&&q=='+str(q))
            r.run_case(attempt,'window128_'+name,r.HERE/'rtl/evf2_result_window.sv','tb_duplicate_suppression',tb)
        r.report['status']='PASS_LOCAL_DIRECTED_REGRESSION'
    except BaseException as exc:
        r.report.update(status='FAIL',error=repr(exc));raise
    finally:r.save(r.HERE/'REGRESSION.json',r.report)
    print('WINDOW128_LOSS=PASS',flush=True)

if __name__=='__main__':main()
