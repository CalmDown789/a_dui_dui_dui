"""Explicit C lab entry; reuse the existing image/startup guard before a socket.

This file is a package template. Run it only inside an independently issued
candidate bundle. It does not program hardware or grant formal acceptance.
"""
from pathlib import Path
import argparse, faulthandler, hashlib, json, math, secrets, socket, sys, time

PACKAGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE / 'lab'))
sys.path.insert(0, str(PACKAGE / 'host'))
sys.path.insert(0, str(PACKAGE / 'scripts'))
sys.path.insert(0, str(PACKAGE / 'streaming'))
sys.path.insert(0, str(PACKAGE / 'diagnostics'))
import lab_diagnostics as diag
from board_lab_functional import selection, save_scope, bound_file
from streaming_client import StreamingClient, PreparedGolden
from board_characterization_identity import file_item, verify_capture

LABEL = 'EVF2_BOARD_LAB_PROTOCOL_OBSERVATIONS_ONLY_NOT_4K30_OR_ELECTRICAL_ACCEPTANCE'
SOURCE_FILES = {
    'streaming/streaming_client.py', 'streaming/stream_receiver.py',
    'streaming/binary_journal.py', 'streaming/audit_protocol.py',
    'streaming/timing_diagnostics.py', 'streaming/nonblocking_io.py',
    'lab/streaming_board_lab.py', 'lab/audit_streaming_run.py', 'lab/run_c_streaming.ps1',
    'diagnostics/lab_bootstrap.py', 'diagnostics/lab_diagnostics.py',
    'diagnostics/Invoke-DiagnosticPython.ps1',
    'diagnostics/owned_job.cs',
}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def streaming_selection(mode, capture, files_only, window):
    # The original candidate/BIT, source constants, tool SHA, source sequence,
    # real post-JTAG UART ordering, scope and endpoint checks all remain here.
    binding = selection(mode, capture, files_only=files_only)
    path = PACKAGE / 'STREAMING_SELECTION.json'
    cfg = json.loads(path.read_text(encoding='utf-8'))
    if cfg.get('scope') != 'ACX750_EXPLICIT_EVF2_OUTPUT_LAB_V1' or cfg.get('wire_version') != 2:
        raise ValueError('An independently issued EVF2 lab selection is required')
    if cfg.get('candidate_BIT_sha256') != binding['candidate_identity']['BIT_sha256']:
        raise ValueError('Streaming selection uses a different BIT')
    if cfg.get('legacy_lab_selection_sha256') != binding['release_sha256']:
        raise ValueError('Existing lab selection changed')
    for key in ('physical_IO_signoff', 'formal_video_permission', 'whole_system_4K30_achieved'):
        if cfg.get(key) is not False:
            raise ValueError('Streaming lab selection must retain false ' + key)
    if cfg.get('electrical_status') != 'UNVERIFIED' or cfg.get('model_changed') is not False:
        raise ValueError('Model/electrical scope changed')
    if cfg.get('core_MHz') != 150 or cfg.get('pause') != 0 or cfg.get('stripe_rows') != 16:
        raise ValueError('Root-selected runtime geometry/clock changed')
    files = cfg.get('files')
    if not isinstance(files, dict) or set(files) != SOURCE_FILES:
        raise ValueError('All streaming sources and entries must be hash bound')
    for name, digest in files.items():
        bound_file({'file': name, 'sha256': digest})
    if window not in cfg.get('allowed_output_windows', []) or not 1 <= window <= 128:
        raise ValueError('Unissued output-window selection')
    return binding, cfg, sha(path)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode', choices=('Natural2', 'Natural16'), required=True)
    ap.add_argument('--startup-capture-report', type=Path)
    ap.add_argument('--files-only', action='store_true')
    ap.add_argument('--out-dir', type=Path, required=True)
    ap.add_argument('--output-window', type=int, choices=(1, 2, 4, 8, 16, 32, 64, 128), default=128)
    ap.add_argument('--io-mode', choices=('timeout','nonblocking'), default='nonblocking')
    ap.add_argument('--timing-mode', choices=('full','sampled'), default='sampled')
    ap.add_argument('--timing-sample-every', type=int, default=16)
    ap.add_argument('--timeout', type=float, default=.02)
    ap.add_argument('--attempts', type=int, default=4)
    ap.add_argument('--frame-timeout', type=float, default=10.)
    a = ap.parse_args()
    if not all(math.isfinite(v) and v > 0 for v in (a.timeout, a.frame_timeout)) or not 1 <= a.attempts <= 10:
        ap.error('Finite positive deadlines and attempts 1..10 required')
    try:
        binding, cfg, cfg_sha = streaming_selection(a.mode, a.startup_capture_report, a.files_only, a.output_window)
    except Exception as exc:
        a.out_dir.mkdir(parents=True, exist_ok=False)
        report = dict(status='FAIL_SELECTION_BEFORE_SOCKET', error=repr(exc), socket_created=False,
                      network_traffic_started=False, board_programmed_by_this_entry=False, scope=LABEL)
        (a.out_dir / 'REPORT.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report)); return 1
    a.out_dir.mkdir(parents=True, exist_ok=False)
    save_scope(a.out_dir, a.mode, binding)
    if a.files_only:
        report = dict(status='PASS_STREAMING_FILES_ONLY_NO_SOCKET_UART_JTAG', socket_created=False,
                      network_traffic_started=False, streaming_selection_sha256=cfg_sha, scope=LABEL)
        (a.out_dir / 'REPORT.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report)); return 0

    pairs = binding['prepared']
    prepared = [(pixels, PreparedGolden(golden)) for pixels, golden in pairs]
    session = secrets.token_bytes(16)
    peer = tuple(binding['release']['peer']); local = tuple(binding['release']['local'])
    (a.out_dir / 'SOURCE_MANIFEST.json').write_bytes(binding['sequence_path'].read_bytes())
    (a.out_dir / 'IMAGE_MANIFEST.json').write_bytes(binding['candidate_path'].read_bytes())
    # Keep portable original UART/JTAG files, so the independent raw auditor can
    # repeat the actual post-JTAG ordering check after C sends the evidence zip.
    evidence = a.out_dir / 'startup_evidence'; evidence.mkdir()
    original_capture = a.startup_capture_report.resolve()
    captured = json.loads(original_capture.read_text(encoding='utf-8-sig'))
    for name in ('raw', 'program_console', 'events_file'):
        _, data = file_item(original_capture.parent, captured[name])
        q = evidence / captured[name]['file']; q.parent.mkdir(parents=True, exist_ok=True); q.write_bytes(data)
    (evidence / 'REPORT.json').write_bytes(original_capture.read_bytes())
    verify_capture(binding['candidate_identity'], evidence / 'REPORT.json')
    actual = []; transport = client = event_file = None
    report = dict(status='RUNNING', scope=LABEL, mode=a.mode, session=session.hex(),
                  peer=list(peer), local=list(local), output_window=a.output_window,
                  candidate_BIT_sha256=binding['candidate_identity']['BIT_sha256'],
                  streaming_selection_sha256=cfg_sha, socket_created=False, network_traffic_started=False,
                  board_programmed_by_this_entry=False, physical_IO_signoff=False,
                  formal_video_permission=False, whole_system_4K30_achieved=False,
                  frames_expected=len(prepared), PC4K_or_preview_integrated=False)
    try:
        # Only this explicitly invoked, fully guarded C entry constructs a socket.
        transport = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        report['socket_created'] = True
        transport.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
        transport.bind(local)
        transport.settimeout(a.timeout)  # Bound the first send as well as receives.
        report['actual_socket_receive_buffer_bytes'] = transport.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        client = StreamingClient(diag.ObservedSocket(transport), peer, session, a.out_dir / 'traffic', output_window=a.output_window,
                                 timeout=a.timeout, attempts=a.attempts, frame_timeout=a.frame_timeout,
                                 io_mode=a.io_mode, timing_mode=a.timing_mode, timing_sample_every=a.timing_sample_every)
        report['output_ack_batch'] = client.ack_batch
        report['output_ack_flush_max_delay_ms'] = client.ack_delay*1000
        event_file = (a.out_dir / 'frame_events.jsonl').open('x', encoding='utf-8')
        def accept_frame(data, identity):
            f = len(actual)
            if f >= len(prepared) or identity['frame_id'] != f or identity['session'] != session.hex():
                raise ValueError('Bounded lab frame sink ownership/identity')
            if identity['golden_match'] is not True or identity['integrity_sha256'] != prepared[f][1].sha256:
                raise ValueError('Frame sink requires the validated Golden identity')
            actual.append(data)  # Fixed 2/16-frame bound; immutable bytes.
            event_file.write(json.dumps(dict(event='VALIDATED_FRAME_ACCEPTED', monotonic_ns=time.perf_counter_ns(),
                                             frame_id=f, identity=identity)) + '\n')
            event_file.flush()  # Failure propagates before final frame ACK.
        report['network_send_attempt_started'] = True
        print(json.dumps(dict(event='EVF2_HELLO_BEGIN', monotonic_ns=time.perf_counter_ns(), socket_timeout=a.timeout)), flush=True)
        client.hello()
        print(json.dumps(dict(event='EVF2_NEGOTIATED', monotonic_ns=time.perf_counter_ns(), output_window=a.output_window)), flush=True)
        began = time.perf_counter_ns(); cpu_began = time.thread_time_ns()
        for f, (pixels, golden) in enumerate(prepared):
            returned = client.transfer(pixels, golden, f, accept_frame)
            assert returned is actual[f]
        end = time.perf_counter_ns(); cpu_end = time.thread_time_ns()
        client.finish()
        report.update(status='COMPLETE_PROTOCOL_BYTES_PENDING_INDEPENDENT_RAW_AUDIT', success=True,
                      protocol_loop_wall_ns=end-began, calling_thread_cpu_ns=cpu_end-cpu_began,
                      frames=client.frames, io_mode=a.io_mode, timing_mode=a.timing_mode,
                      timing_sample_every=a.timing_sample_every, completed_frames=len(actual),
                      protocol_loop_frames_per_second=len(actual)*1e9/(end-began),
                      timing_scope='BEGIN_TO_LAST_FRAME_DONE_INCLUDES_HOST_PROTOCOL_AND_JOURNAL_CHECKPOINTS_NO_PC4K_OR_DISPLAY',
                      ignored=client.ignored, retries=client.retries, max_input_retained=client.max_retained,
                      max_inbox=client.max_inbox)
        # Materialize outputs after the timed protocol loop. Raw journal still
        # permits independent reconstruction; PNG/playback is a separate step.
        report['outputs'] = []
        for f, data in enumerate(actual):
            p = a.out_dir / f'actual_result_{f}.bin'; p.write_bytes(data)
            report['outputs'].append(dict(frame_id=f, file=p.name, bytes=len(data), sha256=sha(p)))
    except Exception as exc:
        if client is not None: client.abort()
        report.update(status='FAIL_PRESERVE_PARTIAL_RAW_EVIDENCE', success=False, error=repr(exc),
                      completed_frames=0 if client is None else len(client.frames))
    finally:
        if client is not None:
            report['successful_send_calls'] = client.serial
            report['network_traffic_started'] = client.serial > 0
        if event_file is not None: event_file.close()
        if transport is not None: transport.close()
        (a.out_dir / 'REPORT.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'scope', 'network_traffic_started')}))
    return 0 if report.get('success') else 1

if __name__ == '__main__':
    raise SystemExit(main())
