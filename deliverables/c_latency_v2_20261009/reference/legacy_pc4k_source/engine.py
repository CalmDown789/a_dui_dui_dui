"""Finite, paced stream -> existing PC4K queues -> application preview.

Transport and preview are supplied by the caller. This module opens no socket,
UART or JTAG. Every offered slot keeps its ID, even when delivery is late.
"""
from pathlib import Path
from queue import Empty
from threading import Event, Lock, Thread
from time import perf_counter_ns, thread_time_ns
import hashlib, json, math, statistics


def summary(values):
    if not values:
        return None
    values = sorted(values)
    return {'count': len(values), 'median': statistics.median(values),
            'p95': values[max(0, math.ceil(.95 * len(values)) - 1)], 'max': values[-1]}


def measure(client, pairs, module, backend, session, model_source, out_dir,
            frames, fps, preview=None, source_kind='CALLER_INJECTED_TRANSPORT', expected_4k=None,queue_accept_timeout=0):
    """Drain every accepted output; a rejected queue prevents its final ACK.

    preview(completed) returns {submitted_ns, size}. It must run on this calling
    thread (Tk main thread). It may raise to stop delivery and preserve evidence.
    """
    if type(frames) is not int or not 1 <= frames <= 18000:
        raise ValueError('finite frame count 1..18000 required')
    if not math.isfinite(fps) or not 0 < fps <= 60 or not pairs:
        raise ValueError('finite target FPS and prepared source pairs required')
    if not math.isfinite(queue_accept_timeout) or not 0<=queue_accept_timeout<=.5:
        raise ValueError('bounded queue acceptance wait 0..0.5 seconds required')
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=False)
    pipeline = module.Pipeline(backend, capacity=2)
    state = {'accepted': [], 'protocol_done': [], 'outputs': [], 'error': None,
             'sender_end_ns': None, 'preview_error': None, 'consumer_error': None,
             'attempted_slots': 0, 'sender_aborted': False, 'evidence_abort_error': None}
    stop, sender_done, lock = Event(), Event(), Lock()
    accepted_events = (out / 'accepted.jsonl').open('x', encoding='utf-8')
    output_events = (out / 'outputs.jsonl').open('x', encoding='utf-8')
    start = perf_counter_ns()
    scheduled_end = start + round(frames * 1e9 / fps)
    hard_end = start + round(max(30, 2*frames/fps+10)*1e9)
    next_output = 0
    last_output = None

    def accept(data, identity, frame_id, source_id, due, began):
        callback_cpu_began=thread_time_ns()
        if stop.is_set():
            raise RuntimeError('consumer stopped; board final ACK withheld')
        expected = pairs[source_id][1]
        if (not isinstance(data, bytes) or len(data) != 2073600 or
                identity['session'] != session or identity['frame_id'] != frame_id or
                identity.get('golden_match') is not True or
                identity.get('integrity_sha256') != expected.sha256):
            raise ValueError('validated immutable frame ownership/Golden identity')
        frame = module.ReceivedFrame(frame_id,
            module.np.frombuffer(data, dtype=module.np.uint8).reshape(1080, 1920),
            model_source, identity['received_perf_counter_ns'],
            source_kind,
            verified=True, integrity_sha256=expected.sha256, source_frame_id=source_id)
        queue_began=perf_counter_ns()
        if not pipeline.submit(frame, timeout=queue_accept_timeout):
            raise RuntimeError('bounded PC4K input queue full; board final ACK withheld')
        accepted_stamp=perf_counter_ns()
        row = {'frame_id': frame_id, 'source_frame_id': source_id,
               'scheduled_due_ns': due, 'begin_ns': began,
               'received_verified_ns': identity['received_perf_counter_ns'],
               'accepted_ns': accepted_stamp, 'queue_accept_wait_ms':(accepted_stamp-queue_began)/1e6,'input_sha256': expected.sha256,
               'delivery_lateness_ms': (began - due) / 1e6,
               'accept_callback_thread_cpu_ns':thread_time_ns()-callback_cpu_began}
        # Append ownership before recording it. A disk failure still leaves the
        # accepted queue task to drain, and propagates before board final ACK.
        with lock:
            state['accepted'].append(row)
        accepted_events.write(json.dumps(row) + '\n'); accepted_events.flush()

    def sender():
        try:
            client.hello()
            for frame_id in range(frames):
                if perf_counter_ns() > hard_end:
                    raise RuntimeError('finite run wall deadline; no offered ID silently skipped')
                due = start + round(frame_id * 1e9 / fps)
                if stop.wait(max(0, (due - perf_counter_ns()) / 1e9)):
                    raise RuntimeError('run stopped before next offered slot')
                began = perf_counter_ns(); source_id = frame_id % len(pairs)
                with lock: state['attempted_slots'] += 1
                pixels, golden = pairs[source_id]
                frame_cpu_began=thread_time_ns()
                client.transfer(pixels, golden, frame_id,
                    lambda data, identity: accept(data, identity, frame_id, source_id, due, began))
                with lock:
                    state['protocol_done'].append({'frame_id': frame_id, 'done_ns': perf_counter_ns(),
                                                   'sender_thread_cpu_ns':thread_time_ns()-frame_cpu_began})
        except BaseException as exc:
            with lock: state['error'] = repr(exc)
            try:
                client.abort()
            except BaseException as abort_exc:
                with lock:state['evidence_abort_error']=repr(abort_exc)
            finally:
                with lock:state['sender_aborted']=True
                stop.set()
        finally:
            with lock: state['sender_end_ns'] = perf_counter_ns()
            sender_done.set()

    worker = Thread(target=sender, name='guarded-stream-sender', daemon=False)
    consumer_thread_cpu_began=thread_time_ns()
    worker.start()
    try:
        while True:
            if perf_counter_ns() > hard_end:
                state['consumer_error'] = 'finite run wall deadline'; stop.set()
            with lock:
                accepted = len(state['accepted'])
            if sender_done.is_set() and next_output == accepted:
                break
            try:
                completed = pipeline.get(timeout=.01)
            except Empty:
                if preview is not None and not state['preview_error']:
                    try: preview(None)
                    except BaseException as exc:
                        state['preview_error'] = repr(exc); stop.set()
                continue
            expected_id = next_output
            next_output += 1
            if isinstance(completed, dict):
                state['outputs'].append(dict(completed, consumer_error=True))
                stop.set()
                continue
            if completed.frame_id != expected_id:
                raise RuntimeError('output ID duplicate/missing/out of order')
            last_output = completed
            row = {'frame_id': completed.frame_id, 'source_frame_id': completed.source_frame_id,
                   'received_verified_ns': completed.received_complete_ns,
                   'processing_start_ns': completed.processing_start_ns,
                   'processing_complete_ns': completed.processing_complete_ns,
                   'shape': list(completed.y8.shape), 'bytes': completed.y8.nbytes,
                   'stages_ms': completed.stages_ms, 'preview_submitted_ns': None,
                   'pipeline_worker_thread_cpu_ns':completed.processing_thread_cpu_ns}
            if completed.y8.shape != (2160, 3840) or completed.y8.nbytes != 8294400:
                raise RuntimeError('complete 4K Y8 geometry')
            if expected_4k is not None:
                expected = expected_4k[completed.source_frame_id]
                if not module.np.array_equal(completed.y8, expected):
                    raise RuntimeError('4K differs from independent integer reference')
                row['mismatch_pixels'] = 0
                row['generated_4k_sha256'] = hashlib.sha256(completed.y8).hexdigest()
            if preview is not None and not state['preview_error']:
                try:
                    shown = preview(completed)
                    stamp = shown['submitted_ns']
                    if not completed.processing_complete_ns <= stamp <= perf_counter_ns():
                        raise ValueError('preview must return this host monotonic submit time')
                    row.update(preview_submitted_ns=stamp, preview_size=shown['size'])
                    if 'stages_ms' in shown:row['preview_stages_ms']=shown['stages_ms']
                except BaseException as exc:
                    state['preview_error'] = repr(exc); stop.set()
            state['outputs'].append(row)
            output_events.write(json.dumps(row) + '\n'); output_events.flush()
    except BaseException as exc:
        state['consumer_error'] = repr(exc)
    finally:
        stop.set()
        # Normal/error paths above drain all accepted frames while sender ends.
        # A caller failure here is kept visible; no accepted output is discarded.
        worker.join(client.frame_timeout + client.timeout * client.attempts + 5)
        if worker.is_alive():
            raise RuntimeError('sender did not stop within its finite protocol deadline')
        accepted_events.close(); output_events.close()
        while next_output < pipeline.stats.accepted:
            completed = pipeline.get(timeout=30)
            state['outputs'].append({'frame_id': completed.get('frame_id') if isinstance(completed, dict) else completed.frame_id,
                                     'drained_after_consumer_failure': True, 'preview_submitted_ns': None})
            next_output += 1
        pipeline.close(timeout=30)
    end = perf_counter_ns()
    consumer_thread_cpu_end=thread_time_ns()
    # Final durable flush/SHA is evidence preparation after traffic and output
    # drain. It can read tens of GiB; record its cost separately from live FPS.
    evidence_finalize_error=None
    evidence_capture_status='ABORTED_PREFIX' if state['sender_aborted'] else 'FINALIZED'
    if not state['sender_aborted']:
        try:client.finish()
        except BaseException as exc:
            evidence_finalize_error=repr(exc);evidence_capture_status='ABORTED_PREFIX'
            try:client.abort()
            except BaseException as abort_exc:state['evidence_abort_error']=repr(abort_exc)
    evidence_finalized=perf_counter_ns()
    completed_rows = [r for r in state['outputs'] if 'processing_complete_ns' in r]
    shown_rows = [r for r in completed_rows if r.get('preview_submitted_ns')]
    duration = (end - start) / 1e9
    window_seconds = frames / fps
    def in_window(rows, key):
        return [r for r in rows if start <= r[key] < scheduled_end]
    protocol_window = in_window(state['protocol_done'], 'done_ns')
    generated_window = in_window(completed_rows, 'processing_complete_ns')
    preview_window = in_window(shown_rows, 'preview_submitted_ns')
    result = {'status': 'COMPLETE_MEASUREMENT' if not state['error'] and not state['preview_error'] and not state['consumer_error'] and not evidence_finalize_error and not state['evidence_abort_error'] and
              pipeline.stats.accepted == pipeline.stats.completed == frames and not pipeline.stats.errors else 'FAIL_PRESERVE_EVIDENCE',
              'scope': 'CALLER_TRANSPORT_4K_APP_SUBMIT_SEPARATE_METRICS_NO_PHYSICAL_REFRESH_CLAIM',
              'target_fps': fps, 'offered_slots': frames, 'nominal_window_seconds': window_seconds,
              'window_start_ns': start, 'window_end_ns': scheduled_end, 'drain_end_ns': end,
              'evidence_finalized_ns':evidence_finalized,'evidence_finalize_error':evidence_finalize_error,
              'evidence_capture_status':evidence_capture_status,'evidence_abort_error':state['evidence_abort_error'],
              'post_measurement_evidence_finalize_ms':(evidence_finalized-end)/1e6,
              'run_wall_deadline_ns': hard_end,
              'actual_span_seconds': duration, 'protocol_completed': len(state['protocol_done']),
              'accepted_1080p': len(state['accepted']), 'generated_4k': len(completed_rows),
              'preview_submitted': len(shown_rows), 'protocol_fps_over_actual_span': len(state['protocol_done']) / duration,
              'generated_4k_fps_over_actual_span': len(completed_rows) / duration,
              'preview_submit_fps_over_actual_span': len(shown_rows) / duration,
              'protocol_fps_in_nominal_window': len(protocol_window) / window_seconds,
              'generated_4k_fps_in_nominal_window': len(generated_window) / window_seconds,
              'preview_submit_fps_in_nominal_window': len(preview_window) / window_seconds,
              'attempted_slots': state['attempted_slots'],
              'unattempted_slots': frames - state['attempted_slots'], 'error': state['error'],
              'preview_error': state['preview_error'], 'consumer_error': state['consumer_error'],
              'pipeline_stats': vars(pipeline.stats), 'source_kind': source_kind,
              'retries': client.retries, 'ignored_datagrams': client.ignored,
              'sender_thread_cpu_ms':summary([r['sender_thread_cpu_ns']/1e6 for r in state['protocol_done']]),
              'consumer_thread_cpu_ms':(consumer_thread_cpu_end-consumer_thread_cpu_began)/1e6,
              'pipeline_worker_thread_cpu_ms':summary([r['pipeline_worker_thread_cpu_ns']/1e6 for r in completed_rows]),
              'accept_callback_thread_cpu_ms':summary([r['accept_callback_thread_cpu_ns']/1e6 for r in state['accepted']]),
              'delayed_input_slots': sum(r['delivery_lateness_ms'] >= 1000 / fps for r in state['accepted']),
              'delivery_lateness_ms': summary([r['delivery_lateness_ms'] for r in state['accepted']]),
              'receive_to_4k_ms': summary([(r['processing_complete_ns']-r['received_verified_ns'])/1e6 for r in completed_rows]),
              'receive_to_preview_ms': summary([(r['preview_submitted_ns']-r['received_verified_ns'])/1e6 for r in shown_rows]),
              'duplicate_output_ids': len(state['outputs']) - len({r['frame_id'] for r in state['outputs']}),
              'missing_generated_ids': sorted({r['frame_id'] for r in state['accepted']} - {r['frame_id'] for r in completed_rows}),
              'accepted_but_no_frame_done': sorted({r['frame_id'] for r in state['accepted']} - {r['frame_id'] for r in state['protocol_done']}),
              'physical_display_refresh_measured': False, 'whole_system_4K30_achieved': False,
              'personal_selftest_completed': False}
    result['generated_4k_reference_checked'] = expected_4k is not None
    result['queue_accept_timeout_s']=queue_accept_timeout
    result['queue_accept_wait_ms']=summary([r['queue_accept_wait_ms']for r in state['accepted']])
    result['generated_4k_reference_zero_difference_frames'] = sum(r.get('mismatch_pixels') == 0 for r in completed_rows)
    begin_by_id = {r['frame_id']: r['begin_ns'] for r in state['accepted']}
    result['begin_to_4k_ms'] = summary([(r['processing_complete_ns']-begin_by_id[r['frame_id']])/1e6 for r in completed_rows])
    result['begin_to_preview_ms'] = summary([(r['preview_submitted_ns']-begin_by_id[r['frame_id']])/1e6 for r in shown_rows])
    for label, rows, key in [('protocol', protocol_window, 'done_ns'),
                              ('generated_4k', generated_window, 'processing_complete_ns'),
                              ('preview_submit', preview_window, 'preview_submitted_ns')]:
        stamps = [r[key] for r in rows]
        result[label+'_per_second'] = [sum(start+i*10**9 <= t < start+(i+1)*10**9 for t in stamps)
                                       for i in range(math.ceil(window_seconds))]
        result[label+'_interval_ms'] = summary([(b-a)/1e6 for a,b in zip(stamps, stamps[1:])])
    if last_output is not None:
        (out/'last_generated_4k.bin').write_bytes(last_output.y8.tobytes())
    (out/'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
