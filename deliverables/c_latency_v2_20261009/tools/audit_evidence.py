"""Portable offline re-audit using the unchanged frozen runtime auditor."""
from pathlib import Path
import argparse, json, subprocess, sys
sys.dont_write_bytecode = True

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    ap.add_argument('--case', help='Optional case path relative to evidence root')
    a = ap.parse_args()
    package = Path(__file__).resolve().parents[1]/'runtime/main'
    root = a.evidence_root.resolve()
    if a.case:
        cases = [(root/a.case).resolve()]
        if not cases[0].is_relative_to(root/'cases'): raise ValueError('Case must stay inside evidence cases')
    else:
        cases = sorted(p.parent for p in (root/'cases').glob('*/*/run'))
        if len(cases) != 32: raise ValueError(f'Expected 32 cases, found {len(cases)}')
    a.out_dir.mkdir(parents=True, exist_ok=False)
    results = []; failed = False
    for case in cases:
        if not (case/'run/REPORT.json').is_file(): raise ValueError('Missing case: '+str(case))
        name = case.parent.name+'_'+case.name
        dest = a.out_dir/name
        command = [sys.executable,'-B',str(package/'lab/audit_streaming_run.py'),
                   '--run',str(case/'run'),'--out-dir',str(dest)]
        with (a.out_dir/(name+'.log')).open('wb') as log:
            done = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        result = json.loads((dest/'AUDIT.json').read_text(encoding='utf-8')) if (dest/'AUDIT.json').exists() else {'status':'FAIL_MISSING_AUDIT'}
        ok = done.returncode == 0 and result.get('status') == 'PASS_INDEPENDENT_RAW_PROTOCOL_GOLDEN_AUDIT'
        failed |= not ok
        results.append(dict(case=case.relative_to(root).as_posix(), exit_code=done.returncode, audit=result))
        print(name, result['status'], flush=True)
    total = sum(x['audit'].get('frames',0) for x in results)
    if not a.case and total != 512: failed = True
    summary = dict(status='FAIL_REAUDIT' if failed else 'PASS_PORTABLE_OFFLINE_REAUDIT',
                   cases=len(results), frames=total, network_or_board_actions=False, results=results)
    (a.out_dir/'SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return 1 if failed else 0

if __name__ == '__main__': raise SystemExit(main())
