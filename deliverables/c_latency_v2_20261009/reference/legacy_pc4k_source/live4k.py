"""Separate supplement to the exact independently issued communication package.

Use file preflight first, then C's actual post-JTAG startup capture. This script
never programs a board or changes NIC settings. No socket before all gates and
runtime preparation pass. A 300 second offer is a measurement, not a PASS rule.
"""
from pathlib import Path
from threading import Event, Thread, current_thread
import argparse, hashlib, importlib.util, json, math, secrets, shutil, socket, sys, time

HERE = Path(__file__).resolve().parent
EXPECTED_FILES = {'live4k.py','engine.py','audit_live4k.py','check_engine.py','check_app.py','check_audit.py',
                  'make_supplement.py','run_live4k.ps1','pc4k/pipeline.py','pc4k/reference.py','README.md',
                  'proof/LOCAL_ENGINE_CHECK.json','proof/LOCAL_APP_CHECK.json','proof/LOCAL_AUDIT_CHECK.json',
                  'check_pc_path_sustained.py','check_fast_wire.py','proof/LOCAL_PC_PATH_CHECK.json','proof/LOCAL_FAST_WIRE_CHECK.json'}


def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


def guard(package, capture, files_only):
    cfg = json.loads((HERE/'SUPPLEMENT_MANIFEST.json').read_text(encoding='utf-8'))
    if cfg['scope'] not in {'EXACT_COMM_PACKAGE_PC4K_MEASUREMENT_SUPPLEMENT_V1',
                            'C_REPAIR_DERIVATIVE_MAIN_NATURAL2_NATURAL16_BOARD_PASS_PC4K_5S_FAIL_NO_4K30_CLAIM'}:
        raise ValueError('issued supplement required')
    for key in ('whole_system_4K30_achieved', 'formal_video_permission', 'physical_IO_signoff'):
        if cfg.get(key) is not False: raise ValueError('scope permission changed: '+key)
    if cfg.get('model_changed')is not False or cfg.get('core_hz')!=150000000 or cfg.get('pause')!=0:
        raise ValueError('requires frozen model, 150MHz and pause=0 supplement')
    if {item['file'] for item in cfg['files']} != EXPECTED_FILES or len(cfg['files']) != len(EXPECTED_FILES):
        raise ValueError('all supplement sources, references and local proofs must be hash bound')
    for item in cfg['files']:
        p = HERE/item['file']
        if not p.resolve().is_relative_to(HERE.resolve()) or sha(p) != item['sha256']:
            raise ValueError('supplement file hash: '+item['file'])
    if sha(package/'PACKAGE_MANIFEST.json') != cfg['comm_package_manifest_sha256']:
        raise ValueError('requires exact independently issued communication package')
    if sha(package/'STREAMING_SELECTION.json') != cfg['streaming_selection_sha256']:
        raise ValueError('requires unchanged communication selection')
    for folder in ('host', 'scripts', 'streaming', 'diagnostics', 'lab'):
        sys.path.insert(0, str(package/folder))
    entry = load('live4k_guarded_board_entry', package/'lab/streaming_board_lab.py')
    binding, selection, selection_sha = entry.streaming_selection('Natural16', capture, files_only, 128)
    if binding['candidate_identity']['BIT_sha256'] != cfg['candidate_BIT_sha256']:
        raise ValueError('supplement BIT differs from observed candidate')
    return binding, cfg


class TkPreview:
    def __init__(self, width, height):
        import tkinter as tk
        self.tk = tk
        self.root = tk.Tk(); self.closed = False; self.photo = None; self.photo_size=None
        self.root.title('PLD · 实际网口 → FPGA 1080p → PC 4K')
        self.root.geometry(f'{width}x{height+70}')
        self.label = tk.Label(self.root, text='完整4K生成与内屏缩放提交分别测量；应用提交不等于面板刷新')
        self.label.pack(fill='x')
        self.canvas = tk.Canvas(self.root, width=width, height=height, bg='black', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.item = self.canvas.create_image(0, 0, anchor='nw')
        self.root.protocol('WM_DELETE_WINDOW', self.request_close)
        self.root.update()

    def request_close(self):
        self.closed = True

    def warmup(self, validated_4k):
        from types import SimpleNamespace
        began=time.perf_counter_ns()
        self(SimpleNamespace(y8=validated_4k,frame_id='准备'))
        self.label.configure(text='准备完成：冻结Golden经PC后端校验；测量尚未开始')
        self.root.update()
        return {'warmup_ms':(time.perf_counter_ns()-began)/1e6,'counted_as_measured_frame':False}

    def __call__(self, completed):
        if self.closed: raise RuntimeError('preview closed by user; stop input and drain accepted frames')
        if completed is None:
            self.root.update(); return None
        import cv2
        from PIL import Image, ImageTk
        began=time.perf_counter_ns()
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = min(width/3840, height/2160, 1)
        size = (max(1, int(3840*scale)), max(1, int(2160*scale)))
        pixels = cv2.resize(completed.y8, size, interpolation=cv2.INTER_AREA)
        scaled=time.perf_counter_ns()
        image=Image.fromarray(pixels)
        created=self.photo is None or self.photo_size!=size
        if created:
            self.photo=ImageTk.PhotoImage(image,master=self.root);self.photo_size=size
        else:self.photo.paste(image)
        photo_ready=time.perf_counter_ns()
        if created:self.canvas.itemconfigure(self.item,image=self.photo)
        self.label.configure(text=f'帧 {completed.frame_id} · 4K生成 3840×2160 · 缩放提交 {size[0]}×{size[1]}')
        configured=time.perf_counter_ns()
        self.root.update_idletasks(); submitted = time.perf_counter_ns()
        self.root.update()
        return {'submitted_ns': submitted, 'size': list(size),
                'stages_ms':{'rescale_ms':(scaled-began)/1e6,'tk_photo_ms':(photo_ready-scaled)/1e6,
                             'canvas_label_ms':(configured-photo_ready)/1e6,'redraw_submit_ms':(submitted-configured)/1e6,
                             'event_loop_ms':(time.perf_counter_ns()-submitted)/1e6}}

    def finish(self, out):
        try:
            if self.photo is not None:
                from PIL import ImageTk
                ImageTk.getimage(self.photo).save(out/'last_app_preview.png')
        finally: self.root.destroy()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--package', type=Path, required=True)
    ap.add_argument('--startup-capture-report', type=Path)
    ap.add_argument('--out-dir', type=Path, required=True)
    ap.add_argument('--files-only', action='store_true')
    ap.add_argument('--runtime-preflight', action='store_true', help='With --files-only: verify backend/Golden/Tk before any board IO')
    ap.add_argument('--seconds', type=float, default=300)
    ap.add_argument('--fps', type=float, default=30)
    ap.add_argument('--backend', choices=('torch-cuda-f64','opencv-f64'), default='torch-cuda-f64')
    ap.add_argument('--preview-width', type=int, default=1280)
    ap.add_argument('--preview-height', type=int, default=720)
    ap.add_argument('--diagnostic-stage', choices=('pc4k','protocol-main','sender-no-pipeline','pipeline-no-preview','pipeline-with-preview'), default='pc4k')
    ap.add_argument('--diagnostic-frames', type=int, default=0)
    a = ap.parse_args()
    if a.runtime_preflight and not a.files_only:
        ap.error('--runtime-preflight requires --files-only; no startup capture or board IO')
    out = a.out_dir.resolve(); out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'PREPARING', 'socket_created': False, 'network_traffic_started': False,
              'UART_JTAG_used_by_this_entry': False, 'Flash_written': False,
              'whole_system_4K30_achieved': False, 'physical_display_refresh_measured': False}
    transport = preview = client = None
    finalize_error = None
    try:
        if not math.isfinite(a.seconds) or not .1 <= a.seconds <= 600 or not math.isfinite(a.fps) or not 0 < a.fps <= 60:
            raise ValueError('finite duration .1..600 seconds and FPS (0,60] required')
        frames = round(a.seconds*a.fps)
        if a.diagnostic_stage != 'pc4k':
            if not 1 <= a.diagnostic_frames <= 16:
                raise ValueError('diagnostic stages require 1..16 explicitly offered frames')
            frames = a.diagnostic_frames
        if not 1 <= frames <= 18000 or not 320 <= a.preview_width <= 2560 or not 180 <= a.preview_height <= 1600:
            raise ValueError('finite offered slots and bounded preview geometry required')
        binding, cfg = guard(a.package.resolve(), a.startup_capture_report, a.files_only)
        report.update(candidate_BIT_sha256=cfg['candidate_BIT_sha256'], source_manifest_sha256=sha(binding['sequence_path']),
                      supplement_manifest_sha256=sha(HERE/'SUPPLEMENT_MANIFEST.json'), backend=a.backend,
                      offered_slots=frames, target_fps=a.fps, requested_seconds=a.seconds)
        if a.runtime_preflight:
            report.update(scope='HOST_RUNTIME_PREPARATION_ONLY_NO_BOARD_MEASUREMENT',offered_slots=0,requested_seconds=0)
        if a.files_only and not a.runtime_preflight:
            report['status'] = 'PASS_FILES_ONLY_NO_SOCKET_UART_JTAG'; return 0
        # Prepare immutable source pairs, reference images and GPU before the
        # measured interval or network. Outputs are recomputed for every slot.
        module = load('live4k_bound_pipeline', HERE/'pc4k/pipeline.py')
        reference = load('live4k_bound_integer_reference', HERE/'pc4k/reference.py')
        from streaming_client import StreamingClient, PreparedGolden
        from board_characterization_identity import file_item, verify_capture
        import lab_diagnostics as diag
        pairs = [(pixels, PreparedGolden(golden)) for pixels, golden in binding['prepared']]
        backend = module.make_backend(a.backend)
        expected = [reference.integer_reference(module.np.frombuffer(g.data, dtype=module.np.uint8).reshape(1080,1920)) for _,g in pairs]
        for source, wanted in zip(pairs, expected):
            actual, _ = backend.resize(module.np.frombuffer(source[1].data, dtype=module.np.uint8).reshape(1080,1920))
            if not module.np.array_equal(actual, wanted): raise ValueError('runtime backend independent reference mismatch before socket')
        if a.runtime_preflight:
            import cv2, PIL, tkinter
            preview = TkPreview(a.preview_width, a.preview_height)
            report['preview_preparation'] = preview.warmup(actual)
            runtime = dict(python_executable=sys.executable, python_version=sys.version, prefix=sys.prefix,
                           numpy_version=module.np.__version__, opencv_version=cv2.__version__,
                           pillow_version=PIL.__version__, tk_version=tkinter.TkVersion,
                           backend=backend.name, independent_reference_zero_difference_frames=len(expected),
                           protocol_clock='time.perf_counter',
                           protocol_clock_info=vars(time.get_clock_info('perf_counter')),
                           platform_monotonic_clock_info=vars(time.get_clock_info('monotonic')))
            if a.backend == 'torch-cuda-f64':
                runtime.update(torch_version=backend.torch.__version__, cuda_runtime=backend.torch.version.cuda,
                               cuda_device=backend.torch.cuda.get_device_name())
            report.update(status='PASS_RUNTIME_BACKEND_GOLDEN_TK_NO_SOCKET_UART_JTAG',runtime=runtime,
                          preparation_images_only=True, measured_board_frames=0)
            return 0
        # Full raw evidence is retained. Stop preparation if disk cannot hold
        # three normal traffic volumes plus two GiB; never disable the journal.
        required = frames*9000000 + 2*1024**3
        if shutil.disk_usage(out).free < required: raise RuntimeError('insufficient free disk for finite raw traffic evidence')
        report['raw_evidence_disk_reserve_bytes'] = required
        for name, path in [('SOURCE_MANIFEST.json',binding['sequence_path']),('IMAGE_MANIFEST.json',binding['candidate_path'])]:
            (out/name).write_bytes(path.read_bytes())
        evidence = out/'startup_evidence'; evidence.mkdir()
        original = a.startup_capture_report.resolve(); captured = json.loads(original.read_text(encoding='utf-8-sig'))
        for name in ('raw','program_console','events_file'):
            _, data = file_item(original.parent, captured[name]); q = evidence/captured[name]['file']
            q.parent.mkdir(parents=True, exist_ok=True); q.write_bytes(data)
        (evidence/'REPORT.json').write_bytes(original.read_bytes())
        verify_capture(binding['candidate_identity'], evidence/'REPORT.json')
        if a.diagnostic_stage in ('pc4k','pipeline-with-preview'):
            preview = TkPreview(a.preview_width, a.preview_height)
            # PIL/Tk's first actual PhotoImage initialization belongs to preparation.
            # Keep startup cost visible; never count this Golden preparation image.
            report['preview_preparation']=preview.warmup(actual)
        else:
            report['preview_preparation']={'scope':'NOT_CREATED_FOR_THIS_DIAGNOSTIC_STAGE','counted_as_measured_frame':False}
        session = secrets.token_bytes(16); peer, local = tuple(binding['release']['peer']), tuple(binding['release']['local'])
        transport = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); report['socket_created'] = True
        transport.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304); transport.bind(local); transport.settimeout(.02)
        observed = diag.ObservedSocket(transport)
        client = StreamingClient(observed, peer, session, out/'traffic', output_window=128, frame_log_mode='jsonl')
        report.update(session=session.hex(), peer=list(peer), local=list(local),
                      actual_socket_receive_buffer_bytes=transport.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF),
                      diagnostic_stage=a.diagnostic_stage)
        if a.diagnostic_stage in ('protocol-main','sender-no-pipeline'):
            outcome={'error':None,'completed':0,'thread_name':None,'thread_cpu_ns':0,'main_wait_thread_cpu_ns':0}
            task_done=Event()
            def protocol_task():
                began=time.thread_time_ns();outcome['thread_name']=current_thread().name
                try:
                    client.hello()
                    for frame_id in range(frames):
                        source_id=frame_id%len(pairs)
                        pixels,golden=pairs[source_id]
                        client.transfer(pixels,golden,frame_id)
                        outcome['completed']+=1
                except BaseException as exc:
                    outcome['error']=repr(exc)
                finally:
                    outcome['thread_cpu_ns']=time.thread_time_ns()-began
                    task_done.set()
            if a.diagnostic_stage == 'protocol-main':
                protocol_task()
            else:
                worker=Thread(target=protocol_task,name='diagnostic-stream-sender',daemon=False)
                main_wait_cpu=time.thread_time_ns();worker.start()
                if not task_done.wait(max(30,frames*(client.frame_timeout+client.timeout*client.attempts+5))):
                    transport.close();worker.join(5)
                    raise RuntimeError('diagnostic sender thread did not stop within its finite wait bound')
                worker.join(1)
                outcome['main_wait_thread_cpu_ns']=time.thread_time_ns()-main_wait_cpu
                if worker.is_alive():raise RuntimeError('diagnostic sender completion event preceded thread exit')
            if outcome['error'] is not None:raise RuntimeError(outcome['error'])
            client.finish()
            diagnostic={'scope':'ONE_VARIABLE_PROTOCOL_THREAD_COMPARISON_NO_PC4K_QUEUE_NO_TK_NO_4K30_CLAIM',
                'stage':a.diagnostic_stage,'frames':outcome['completed'],'completed_frames':len(client.frames),
                'run_thread':outcome['thread_name'],'run_thread_cpu_ns':outcome['thread_cpu_ns'],
                'main_wait_thread_cpu_ns':outcome['main_wait_thread_cpu_ns'],'frame_rows':client.frames,
                'timing_diagnostics_file':'traffic/TIMING_DIAGNOSTICS.json','raw_journal_file':'traffic/datagrams.bin',
                'socket_receive_buffer_bytes':transport.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF),
                'queue_mode':'NO_PC4K_QUEUE_ACCEPTANCE_DIAGNOSTIC_ONLY','preview_mode':'NONE',
                'physical_display_refresh_measured':False,'whole_system_4K30_achieved':False}
            (out/'DIAGNOSTIC.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
            report.update(status='PASS_PROTOCOL_THREAD_DIAGNOSTIC',diagnostic=diagnostic,
                          successful_send_calls=client.serial,network_traffic_started=client.serial>0,
                          timing_diagnostics_sha256=sha(out/'traffic/TIMING_DIAGNOSTICS.json'))
            return 0
        engine = load('live4k_bound_engine', HERE/'engine.py')
        diagnostic_preview=preview if a.diagnostic_stage in ('pc4k','pipeline-with-preview') else None
        measured = engine.measure(client,pairs,module,backend,session.hex(),
            'frozen-d16-s8-m1-c16/BIT:'+cfg['candidate_BIT_sha256'],out/'measurement',frames,a.fps,
            preview=diagnostic_preview,source_kind='EXACT_NEW_BIT_POST_JTAG_PHY_VERIFIED_BOARD_STREAM',expected_4k=expected,queue_accept_timeout=.5)
        if a.diagnostic_stage != 'pc4k':
            measured['diagnostic_stage']=a.diagnostic_stage
            measured['diagnostic_scope']='ONE_VARIABLE_PIPELINE_OR_PREVIEW_COMPARISON_NOT_FORMAL_PC4K_AUDIT'
            (out/'measurement/RESULTS.json').write_text(json.dumps(measured,ensure_ascii=False,indent=2),encoding='utf-8')
        report.update(status=measured['status'], successful_send_calls=client.serial,
                      network_traffic_started=client.serial>0, measurement_result_sha256=sha(out/'measurement/RESULTS.json'),
                      timing_diagnostics_sha256=sha(out/'traffic/TIMING_DIAGNOSTICS.json'))
        return 0 if measured['status']=='COMPLETE_MEASUREMENT' else 1
    except BaseException as exc:
        report.update(status='FAIL_PRESERVE_EVIDENCE', error=repr(exc)); return 1
    finally:
        if transport is not None: transport.close()
        if client is not None:
            # measure normally owns finish/abort. An exception before its
            # normal return still needs a closed, preserved capture prefix.
            if not client.journal.closed:
                try: client.abort()
                except BaseException as exc:
                    report.update(status='FAIL_PRESERVE_EVIDENCE',evidence_abort_error=repr(exc))
            report.update(successful_send_calls=client.serial,network_traffic_started=client.serial>0)
        if preview is not None:
            try: preview.finish(out)
            except BaseException as exc:
                finalize_error = exc
                report.update(status='FAIL_PREVIEW_FINALIZE_PRESERVE_EVIDENCE',preview_finalize_error=repr(exc))
        (out/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
        if finalize_error is not None: raise RuntimeError('preview finalize failed; evidence report saved') from finalize_error


if __name__ == '__main__': raise SystemExit(main())
