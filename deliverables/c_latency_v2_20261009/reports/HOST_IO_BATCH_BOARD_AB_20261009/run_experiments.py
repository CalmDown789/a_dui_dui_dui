from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess, sys, time
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
PACKAGE = Path(r'C:\t6int09\main')
BIT_SHA = 'cefe3ba044bb208a08969714f48144870f5c00efc6879edb063ac1f358ef1ea5'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def run(command, log, timeout):
    with log.open('xb') as f:
        p = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
    if p.returncode:
        print(log.read_text(encoding='utf-8', errors='replace')[-1800:], flush=True)
        raise RuntimeError('Child failed: ' + str(log))


def main():
    manifest = json.loads((ROOT / 'EXPERIMENT_MANIFEST.json').read_text(encoding='utf-8'))
    for name, digest in manifest['experiment_sources_sha256'].items():
        assert sha(ROOT / name) == digest, name
    original_manifest = json.loads((PACKAGE / 'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    initial_hashes = {name: sha(PACKAGE / name) for name in original_manifest['file_sha256']}
    assert all(initial_hashes[name] == digest for name, digest in original_manifest['file_sha256'].items())
    selection = json.loads((PACKAGE / 'LAB_FUNCTIONAL_SELECTION.json').read_text(encoding='utf-8'))
    assert selection['candidate_BIT_sha256'] == BIT_SHA
    designs = [
        ('io_timing', [('timeout_full', 'timeout', 'full', None),
                       ('timeout_sampled', 'timeout', 'sampled', None),
                       ('nonblocking_full', 'nonblocking', 'full', None),
                       ('nonblocking_sampled', 'nonblocking', 'sampled', None)]),
        ('input_batch', [('batch1', 'nonblocking', 'sampled', 1),
                         ('batch4', 'nonblocking', 'sampled', 4),
                         ('batch8', 'nonblocking', 'sampled', 8),
                         ('batch32', 'nonblocking', 'sampled', 32)])]
    # Balanced positions and first-order carryover within four treatments.
    orders = [(0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1)]
    rows = []
    start = time.monotonic()
    for stage, configs in designs:
        for round_id, order in enumerate(orders):
            for position, config_id in enumerate(order):
                name, io, timing, batch = configs[config_id]
                case = ROOT / 'cases' / stage / f'r{round_id}_{position}_{name}'
                case.mkdir(parents=True, exist_ok=False)
                row = dict(stage=stage, round=round_id, position=position, variant=name,
                           io_mode=io, timing_mode=timing, input_batch=batch or 32,
                           output_batch=32, path=str(case), start_UTC=datetime.now(timezone.utc).isoformat())
                print(json.dumps(dict(event='CASE_START', **row)), flush=True)
                try:
                    run([sys.executable, '-B', str(PACKAGE / 'scripts/capture_board_characterization.py'),
                        '--manifest', str(PACKAGE / selection['characterization_manifest']['file']),
                        '--issued-manifest-sha256', selection['characterization_manifest']['sha256'],
                        '--port', 'COM3', '--vivado-bat', r'E:\AMDTools2025\2025.2\Vivado\bin\vivado.bat',
                        '--program-tcl', str(PACKAGE / 'scripts/program_board_characterization.tcl'),
                        '--out-dir', str(case / 'startup')], case / 'startup.log', 600)
                    row['startup_pass'] = True
                    entry = PACKAGE / 'lab/streaming_board_lab.py' if batch is None else ROOT / 'input_batch_driver.py'
                    args = [sys.executable, '-B', str(entry)]
                    if batch is not None:
                        args += ['--input-batch', str(batch), '--experiment-manifest', str(ROOT / 'EXPERIMENT_MANIFEST.json')]
                    args += ['--mode', 'Natural16', '--startup-capture-report', str(case / 'startup/REPORT.json'),
                        '--out-dir', str(case / 'run'), '--output-window', '128', '--io-mode', io,
                        '--timing-mode', timing, '--timing-sample-every', '16']
                    run(args, case / 'run.log', 180)
                    row['run_pass'] = True
                    report = json.loads((case / 'run/REPORT.json').read_text(encoding='utf-8'))
                    assert report['candidate_BIT_sha256'] == BIT_SHA and report['completed_frames'] == 16
                    if batch is not None:
                        assert report['experiment_runtime']['input_receive_batch_packets'] == batch
                        assert report['experiment_runtime']['output_receive_batch_packets'] == 32
                    run([sys.executable, '-B', str(PACKAGE / 'lab/audit_streaming_run.py'),
                        '--run', str(case / 'run'), '--out-dir', str(case / 'audit')], case / 'audit.log', 180)
                    audit = json.loads((case / 'audit/AUDIT.json').read_text(encoding='utf-8'))
                    assert audit['status'] == 'PASS_INDEPENDENT_RAW_PROTOCOL_GOLDEN_AUDIT'
                    row.update(audit_pass=True, frames=report['frames'], retries=report['retries'],
                        ignored=report['ignored'], protocol_loop_wall_ns=report['protocol_loop_wall_ns'],
                        audit=audit, candidate_BIT_sha256=report['candidate_BIT_sha256'])
                    times = sorted(f['timing_ns']['whole']/1e6 for f in report['frames'])
                    print(json.dumps(dict(event='CASE_PASS', stage=stage, round=round_id, variant=name,
                        frames=16, median_ms=(times[7]+times[8])/2, retries=report['retries'],
                        ignored=report['ignored'], elapsed_seconds=round(time.monotonic()-start, 1))), flush=True)
                except BaseException as exc:
                    row['error'] = repr(exc)
                    rows.append(row)
                    (ROOT / 'RUNS.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
                    raise
                rows.append(row)
                (ROOT / 'RUNS.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    final_hashes = {name: sha(PACKAGE / name) for name in initial_hashes}
    assert final_hashes == initial_hashes
    receipt = dict(status='PASS_ALL_32_CASES_512_FRAMES', completed_UTC=datetime.now(timezone.utc).isoformat(),
        sealed_package_files_unchanged=True, sealed_files_checked=len(initial_hashes),
        frames=sum(len(r['frames']) for r in rows), cases=len(rows), candidate_BIT_sha256=BIT_SHA,
        experiment_manifest_sha256=sha(ROOT/'EXPERIMENT_MANIFEST.json'), elapsed_seconds=time.monotonic()-start)
    (ROOT / 'FINAL_RECEIPT.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
