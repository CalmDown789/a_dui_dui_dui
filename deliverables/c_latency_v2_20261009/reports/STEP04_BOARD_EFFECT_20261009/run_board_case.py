"""User-authorized short board comparison; preserve existing identity gates."""
from pathlib import Path
import argparse, hashlib, importlib, json, secrets, shutil, socket, sys, time

sys.dont_write_bytecode = True
WORK = Path(__file__).resolve().parents[2]
PACKAGE = Path(r'C:\t6dup09\main')
STEP4 = WORK / 'output/HOST_STEP04_SAMPLED_TIMING_20261009'

def sha(p):
    with Path(p).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', choices=('step03_full', 'step04_full', 'step04_sampled'), required=True)
    ap.add_argument('--startup', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--files-only', action='store_true')
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    report = dict(status='PREFLIGHT', variant=a.variant, socket_created=False,
                  first_step_rtl_patch_in_bit=False, actual_30fps_proven=False,
                  physical_IO_signoff=False, formal_video_permission=False,
                  scope='USER_AUTHORIZED_EXISTING_BIT_HOST_COMPARISON_NO_PC4K_OR_DISPLAY')
    transport = client = event_file = None
    try:
        # Execute the unchanged issued package's BIT/source/startup/endpoint guards.
        sys.path.insert(0, str(PACKAGE / 'lab'))
        import streaming_board_lab as guarded
        binding, cfg, cfg_sha = guarded.streaming_selection('Natural2', a.startup, a.files_only, 128)
        manifest = json.loads((STEP4 / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
        prefix = 'baseline' if a.variant == 'step03_full' else 'main'
        sources = {}
        for row in manifest['files']:
            p = STEP4 / prefix / row['file']
            expected = row['step03_sha256'] if prefix == 'baseline' else row['candidate_sha256']
            assert sha(p) == expected, str(p)
            sources[str(p)] = expected
        for row in json.loads((STEP4/'FINAL_RECEIPT.json').read_text(encoding='utf-8'))['artifact_sha256'].items():
            assert sha(STEP4/row[0]) == row[1], row[0]
        report.update(candidate_BIT_sha256=binding['candidate_identity']['BIT_sha256'],
                      streaming_selection_sha256=cfg_sha, mode='Natural2', output_window=128,
                      peer=binding['release']['peer'], local=binding['release']['local'],
                      runtime_sources_sha256=sources, runner_sha256=sha(__file__))
        (a.out/'HOST_RUNTIME_MANIFEST.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if a.files_only:
            report['status'] = 'PASS_FILES_ONLY'
            return 0
        guarded.save_scope(a.out, 'Natural2', binding)
        (a.out/'SOURCE_MANIFEST.json').write_bytes(binding['sequence_path'].read_bytes())
        (a.out/'IMAGE_MANIFEST.json').write_bytes(binding['candidate_path'].read_bytes())
        shutil.copytree(a.startup.parent, a.out/'startup_evidence')
        # Keep the guarded package intact; load the separately hash-bound host candidate.
        for name in ('streaming_client', 'stream_receiver', 'binary_journal', 'timing_diagnostics',
                     'nonblocking_io', 'audit_protocol'):
            sys.modules.pop(name, None)
        sys.path[:0] = [str(STEP4/prefix/'streaming'), str(STEP4/prefix/'host')]
        candidate = importlib.import_module('streaming_client')
        assert Path(candidate.__file__).resolve() == (STEP4/prefix/'streaming/streaming_client.py').resolve()
        session = secrets.token_bytes(16)
        report['session'] = session.hex()
        peer, local = tuple(report['peer']), tuple(report['local'])
        prepared = [(pixels, candidate.PreparedGolden(golden)) for pixels, golden in binding['prepared']]
        actual = []
        transport = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        report['socket_created'] = True
        transport.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
        transport.bind(local)
        transport.settimeout(.02)
        report['actual_socket_receive_buffer_bytes'] = transport.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        kw = dict(output_window=128, timeout=.02, attempts=4, frame_timeout=10., io_mode='nonblocking')
        if prefix == 'main':
            kw.update(timing_mode='sampled' if a.variant == 'step04_sampled' else 'full', timing_sample_every=16)
        client = candidate.StreamingClient(transport, peer, session, a.out/'traffic', **kw)
        event_file = (a.out/'frame_events.jsonl').open('x', encoding='utf-8')
        def accept(data, identity):
            f = len(actual)
            assert identity['frame_id'] == f and identity['session'] == session.hex()
            assert identity['golden_match'] is True and identity['integrity_sha256'] == prepared[f][1].sha256
            actual.append(data)
            event_file.write(json.dumps(dict(event='VALIDATED_FRAME_ACCEPTED', monotonic_ns=time.perf_counter_ns(),
                                             frame_id=f, identity=identity))+'\n')
            event_file.flush()
        print(json.dumps(dict(event='BOARD_TEST_START', variant=a.variant, session=session.hex())), flush=True)
        began = time.perf_counter_ns(); cpu_began = time.thread_time_ns()
        client.hello()
        negotiated = time.perf_counter_ns()
        print('BOARD_NEGOTIATED', flush=True)
        for f, (pixels, golden) in enumerate(prepared):
            returned = client.transfer(pixels, golden, f, accept)
            assert returned is actual[f]
            print(json.dumps(dict(event='FRAME_COMPLETE', frame=f, metrics=client.frames[-1])), flush=True)
        end = time.perf_counter_ns(); cpu_end = time.thread_time_ns()
        client.finish()
        report.update(status='COMPLETE_PROTOCOL_BYTES_PENDING_INDEPENDENT_RAW_AUDIT', success=True,
                      completed_frames=len(actual), protocol_loop_wall_ns=end-negotiated,
                      hello_and_two_frames_wall_ns=end-began, calling_thread_cpu_ns=cpu_end-cpu_began,
                      hello_wall_ns=negotiated-began, frames=client.frames, retries=client.retries, ignored=client.ignored)
        report['outputs'] = []
        for f, data in enumerate(actual):
            p = a.out/f'actual_result_{f}.bin'; p.write_bytes(data)
            report['outputs'].append(dict(frame_id=f, file=p.name, bytes=len(data), sha256=sha(p)))
        assert all(sha(p)==digest for p,digest in sources.items())
        return 0
    except Exception as exc:
        if client is not None:
            try: client.abort()
            except Exception as preserve: report['preservation_error'] = repr(preserve)
        report.update(status='FAIL_PRESERVE_PARTIAL_EVIDENCE', success=False, error=repr(exc),
                      completed_frames=len(client.frames) if client is not None else 0,
                      frames=client.frames if client is not None else [],
                      received_datagrams=client.received if client is not None else 0,
                      successful_send_calls=client.serial if client is not None else 0)
        print(json.dumps(report), flush=True)
        return 1
    finally:
        if event_file is not None: event_file.close()
        if transport is not None: transport.close()
        (a.out/'REPORT.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

if __name__ == '__main__':
    raise SystemExit(main())
