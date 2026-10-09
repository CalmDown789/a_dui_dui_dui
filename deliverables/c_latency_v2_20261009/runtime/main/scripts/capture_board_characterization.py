"""Independent LAB capture: COM3 before temporary JTAG, no network/video permission."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, subprocess, time
from board_characterization_identity import (verify_characterization_manifest,
    verify_capture, post_exit_records, sha, STAGE)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--issued-manifest-sha256', required=True)
    p.add_argument('--port', default='COM3')
    p.add_argument('--vivado-bat', type=Path, required=True)
    p.add_argument('--program-tcl', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--seconds', type=float, default=15)
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=False)
    preflight = dict(scope='LAB_CAPTURE_LOCAL_PREFLIGHT', serial_opened=False,
                     JTAG_started=False, socket_opened=False, physical_IO_signoff=False,
                     network_video_permission=False, electrical_pass=False, video_pass=False)
    try:
        if a.port.upper() != 'COM3' or not 5 <= a.seconds <= 600:
            raise ValueError('Expected COM3 and finite capture seconds in 5..600')
        identity = verify_characterization_manifest(a.manifest, a.issued_manifest_sha256)
        if not a.vivado_bat.is_file() or not a.program_tcl.is_file():
            raise ValueError('Existing Vivado/program TCL absent')
        if sha(a.program_tcl.read_bytes()) != identity['programmer_sha256']:
            raise ValueError('JTAG script differs from root candidate contract')
        import serial
        from serial.tools import list_ports
        ports = [dict(device=p.device, description=p.description, hwid=p.hwid) for p in list_ports.comports()]
        if sum(p['device'].upper() == 'COM3' for p in ports) != 1:
            raise ValueError('COM3 not uniquely enumerated')
        preflight.update(status='LAB_LOCAL_FILES_READY_ONLY', identity=identity, ports=ports)
    except Exception as exc:
        preflight.update(status='LAB_CAPTURE_REJECTED_NO_EXTERNAL_ACTION', error=repr(exc))
        (a.out_dir / 'PREFLIGHT.json').write_text(json.dumps(preflight, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'status': preflight['status'], 'error': preflight['error']}))
        return 1
    (a.out_dir / 'PREFLIGHT.json').write_text(json.dumps(preflight, indent=2) + '\n', encoding='utf-8')
    # Preserve the actually used root identities/tools in this attempt.
    (a.out_dir / 'CANDIDATE_MANIFEST.json').write_bytes(a.manifest.read_bytes())
    (a.out_dir / 'DIGITAL_REVIEW.json').write_bytes(Path(identity['digital_review_file']).read_bytes())
    (a.out_dir / 'ISSUED_PROGRAMMER.tcl').write_bytes(a.program_tcl.read_bytes())
    raw = bytearray()
    events = []
    error = None
    process = None
    exit_code = None
    offset = None
    events_path = a.out_dir / 'events.jsonl'
    events_path.write_bytes(b'')
    def event(name, **fields):
        row = dict(utc=datetime.now(timezone.utc).isoformat(), monotonic_seconds=time.monotonic(), event=name, **fields)
        events.append(row)
        with events_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row) + '\n')
    try:
        with serial.Serial('COM3', 115200, timeout=.02) as port, (a.out_dir / 'uart_raw.bin').open('xb') as stream, (a.out_dir / 'program_console.log').open('xb') as console:
            event('UART_OPENED_BEFORE_JTAG', port='COM3', baud=115200)
            print('LAB UART opened BEFORE JTAG; keep S0 released. This grants no video permission.', flush=True)
            argv = [str(a.vivado_bat.resolve()), '-mode', 'batch', '-source', str(a.program_tcl.resolve()),
                    '-log', 'program.log', '-journal', 'program.jou', '-tclargs', identity['BIT_file']]
            event('JTAG_PROCESS_START', argv=argv)
            process = subprocess.Popen(argv, cwd=a.out_dir, stdout=console, stderr=subprocess.STDOUT)
            program_deadline = time.monotonic() + 480
            deadline = None
            while True:
                payload = port.read(4096)
                if payload:
                    raw.extend(payload)
                    stream.write(payload)
                    stream.flush()
                exit_code = process.poll()
                if exit_code is not None and deadline is None:
                    offset = len(raw)
                    event('JTAG_PROCESS_EXIT', exit_code=exit_code, raw_offset=offset)
                    if exit_code != 0:
                        raise RuntimeError('JTAG nonzero; preserve complete original logs')
                    deadline = time.monotonic() + a.seconds
                if deadline is not None:
                    packets, decoded, positions = post_exit_records(bytes(raw), offset)
                    if len(packets) >= 2:
                        event('TWO_COMPLETE_IDENTICAL_POST_JTAG_PHY0', count=len(packets), offsets=positions)
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Two complete identical successful post-JTAG PHY0 records missing')
                elif time.monotonic() >= program_deadline:
                    raise TimeoutError('Programmer still running; do not launch another programmer or pack growing logs')
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    for filename, content in [('uart_raw.bin', raw), ('program_console.log', b'')]:
        if not (a.out_dir / filename).exists():
            (a.out_dir / filename).write_bytes(content)
    def item(name):
        data = (a.out_dir / name).read_bytes()
        return dict(file=name, bytes=len(data), sha256=sha(data))
    result = dict(scope='ACX750_BOARD_CHARACTERIZATION_UART_CAPTURE_V1', release_stage=STAGE,
                  error=error, port='COM3', baud=115200, ports=ports,
                  manifest_sha256=identity['manifest_sha256'], BIT_sha256=identity['BIT_sha256'],
                  source_routed_DCP_sha256=identity['source_routed_DCP_sha256'], programmer_sha256=identity['programmer_sha256'],
                  JTAG_exit_code=exit_code, JTAG_process_pid=process.pid if process else None,
                  JTAG_process_running_at_capture_return=bool(process and process.poll() is None),
                  post_JTAG_raw_offset=offset, raw=item('uart_raw.bin'),
                  program_console=item('program_console.log'), events_file=item('events.jsonl'), events=events,
                  physical_IO_signoff=False, network_video_permission=False, electrical_pass=False,
                  video_pass=False, complete_stage_acceptance=False)
    report = a.out_dir / 'REPORT.json'
    report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    if error is None:
        try:
            audited = verify_capture(identity, report)
            (a.out_dir / 'LAB_STARTUP_IDENTITY_OBSERVED_ONLY.json').write_text(json.dumps(audited, indent=2) + '\n', encoding='utf-8')
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            result['error'] = error
            report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='LAB_STARTUP_IDENTITY_OBSERVED_ONLY' if error is None else 'LAB_CAPTURE_FAILED', error=error, out_dir=str(a.out_dir))))
    return 0 if error is None else 1

if __name__ == '__main__':
    raise SystemExit(main())
