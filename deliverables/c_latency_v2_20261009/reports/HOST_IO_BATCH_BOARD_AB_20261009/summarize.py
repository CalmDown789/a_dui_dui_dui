from pathlib import Path
from collections import defaultdict, Counter
import json, math, statistics, sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path[:0] = [r'C:\t6int09\main\streaming', r'C:\t6int09\main\host']
from binary_journal import records
from audit_protocol import parse


def stats(values):
    x = sorted(values)
    if not x:
        return None
    return dict(n=len(x), median=statistics.median(x), mean=statistics.mean(x),
        p95_nearest_rank=x[math.ceil(.95*len(x))-1], minimum=x[0], maximum=x[-1])


def journal_stats(run):
    sent = {}; acks = defaultdict(list); lags = defaultdict(list)
    refill = []; batch_counts = []; first = last = None; count = 0
    control_sent = {}; control_repeats = []; max_output_seq = {}; seen_output = defaultdict(set)
    late_missing_output = []
    for stamp, direction, raw, source in records(run / 'traffic/datagrams.bin'):
        if direction == 0 and raw[5] in (1, 2, 3, 4, 9):
            if raw in control_sent:
                control_repeats.append(dict(version=raw[4], packet_type=raw[5],
                    frame=int.from_bytes(raw[24:28], 'big'), sequence=int.from_bytes(raw[28:32], 'big'),
                    interval_ms=(stamp-control_sent[raw])/1e6))
            control_sent[raw] = stamp
        if direction == 1 and raw[4] == 2 and raw[5] == 0x17:
            f = int.from_bytes(raw[24:28], 'big'); q = int.from_bytes(raw[28:32], 'big')
            if q < max_output_seq.get(f, -1) and q not in seen_output[f]:
                late_missing_output.append(dict(frame=f, sequence=q, prior_highest_sequence=max_output_seq[f]))
            max_output_seq[f] = max(q, max_output_seq.get(f, -1)); seen_output[f].add(q)
        if raw[4] != 1 or raw[5] not in (2, 3, 0x83):
            continue
        version, p = parse(raw)
        if direction == 0 and p.type == 2:
            first = last = None; count = 0
        if direction == 0 and p.type == 3:
            sent[p.frame_id, p.sequence] = stamp
            if first is not None:
                refill.append((stamp-first)/1e6)
                batch_counts.append(count)
                first = last = None; count = 0
        if direction == 1 and p.type == 0x83 and p.status == 1:
            lags[p.frame_id].append((stamp-sent[p.frame_id, p.sequence])/1e6)
            acks[p.frame_id].append(stamp)
            if first is None:
                first = stamp
            last = stamp; count += 1
    gaps = {f: [(b-a)/1e6 for a, b in zip(t, t[1:])] for f, t in acks.items()}
    return dict(repeated_host_control_or_data_requests=control_repeats,
        late_previously_missing_output_chunks=late_missing_output,
        input_ack_host_observed_lag_ms=stats([x for t in lags.values() for x in t]),
        input_ack_lag_median_per_frame_ms=stats([statistics.median(t) for t in lags.values()]),
        ack_capture_to_next_data_ms=stats(refill), ack_capture_batch_size=stats(batch_counts),
        input_ack_gaps_ms=stats([x for t in gaps.values() for x in t]),
        long_ack_gap_count_per_frame=stats([sum(x > .25 for x in t) for t in gaps.values()]),
        long_ack_gap_total_ms_per_frame=stats([sum(x for x in t if x > .25) for t in gaps.values()]))


def main():
    runs = json.loads((ROOT / 'RUNS.json').read_text(encoding='utf-8'))
    grouped = defaultdict(list)
    case_rows = []
    for r in runs:
        if not r.get('audit_pass'):
            continue
        run = Path(r['path']) / 'run'
        t = json.loads((run / 'traffic/TIMING_DIAGNOSTICS.json').read_text(encoding='utf-8'))
        j = journal_stats(run)
        case = {k: r[k] for k in ('stage', 'round', 'position', 'variant', 'io_mode', 'timing_mode', 'input_batch', 'output_batch', 'path', 'retries', 'ignored')}
        case.update(whole_ms=stats([f['timing_ns']['whole']/1e6 for f in r['frames']]),
            phase_ms={p: stats([f['timing_ns'][p]/1e6 for f in r['frames']]) for p in r['frames'][0]['timing_ns']},
            readiness_wait_ms_per_frame=t['stages'].get('readiness_wait', {}).get('wall_total_ns', 0)/1e6/16,
            io_counters=t['counters'], raw_analysis=j, raw_journal_sha256=r['audit']['raw_journal_sha256'])
        case_rows.append(case)
        grouped[r['stage'], r['variant']].append((r, case))
    groups = {}
    for (stage, variant), cases in grouped.items():
        rows = [f for r, _ in cases for f in r['frames']]
        subsequent = [f for r, _ in cases for f in r['frames'][1:]]
        groups.setdefault(stage, {})[variant] = dict(runs=len(cases), frames=len(rows),
            whole_ms=stats([f['timing_ns']['whole']/1e6 for f in rows]),
            first_frame_ms=stats([r['frames'][0]['timing_ns']['whole']/1e6 for r, _ in cases]),
            subsequent_frame_ms=stats([f['timing_ns']['whole']/1e6 for f in subsequent]),
            phase_ms={p: stats([f['timing_ns'][p]/1e6 for f in rows]) for p in rows[0]['timing_ns']},
            round_mean_ms=[c['whole_ms']['mean'] for r, c in sorted(cases, key=lambda rc: rc[0]['round'])],
            readiness_wait_ms_per_frame=stats([c['readiness_wait_ms_per_frame'] for _, c in cases]),
            input_ack_lag_median_ms=stats([c['raw_analysis']['input_ack_host_observed_lag_ms']['median'] for _, c in cases]),
            ack_capture_to_next_data_median_ms=stats([c['raw_analysis']['ack_capture_to_next_data_ms']['median'] for _, c in cases]),
            ack_capture_batch_median=stats([c['raw_analysis']['ack_capture_batch_size']['median'] for _, c in cases]),
            long_ack_gap_count_per_frame_mean=statistics.mean(c['raw_analysis']['long_ack_gap_count_per_frame']['mean'] for _, c in cases),
            long_ack_gap_total_ms_per_frame_mean=statistics.mean(c['raw_analysis']['long_ack_gap_total_ms_per_frame']['mean'] for _, c in cases),
            retries=sum(r['retries'] for r, _ in cases), ignored=sum(r['ignored'] for r, _ in cases),
            repeated_host_request_types=dict(Counter(str(p['version'])+':'+str(p['packet_type'])
                for _, c in cases for p in c['raw_analysis']['repeated_host_control_or_data_requests'])),
            late_previously_missing_output_chunks=sum(len(c['raw_analysis']['late_previously_missing_output_chunks']) for _, c in cases),
            duplicates=sum(f['output_duplicate_packets'] for f in rows),
            rejected=sum(f['output_rejected_packets'] for f in rows),
            Golden_mismatches=sum(r['audit']['Golden_mismatches'] for r, _ in cases),
            protocol_loop_fps=len(rows)*1e9/sum(r['protocol_loop_wall_ns'] for r, _ in cases))
    comparisons = []
    desired = [('io_timing','timeout_full','timeout_sampled'),
               ('io_timing','nonblocking_full','nonblocking_sampled'),
               ('io_timing','timeout_full','nonblocking_full'),
               ('io_timing','timeout_sampled','nonblocking_sampled'),
               ('input_batch','batch32','batch1'),('input_batch','batch32','batch4'),('input_batch','batch32','batch8')]
    for stage, baseline, candidate in desired:
        if baseline not in groups.get(stage, {}) or candidate not in groups[stage]:
            continue
        a = {r['round']: r for r in case_rows if r['stage']==stage and r['variant']==baseline}
        b = {r['round']: r for r in case_rows if r['stage']==stage and r['variant']==candidate}
        common = sorted(a.keys() & b.keys())
        if not common:
            continue
        gain = [a[i]['whole_ms']['mean']-b[i]['whole_ms']['mean'] for i in common]
        median_gain = [a[i]['whole_ms']['median']-b[i]['whole_ms']['median'] for i in common]
        phase_gain = {p: [a[i]['phase_ms'][p]['mean']-b[i]['phase_ms'][p]['mean'] for i in common] for p in a[common[0]]['phase_ms']}
        mean_base = statistics.mean(a[i]['whole_ms']['mean'] for i in common)
        comparisons.append(dict(stage=stage, baseline=baseline, candidate=candidate, matched_rounds=common,
            round_mean_saved_ms=gain, saved_ms_stats=stats(gain), elapsed_reduction_percent=100*statistics.mean(gain)/mean_base,
            round_median_saved_ms=median_gain, median_saved_ms_stats=stats(median_gain),
            positive_median_gain_rounds=sum(x > 0 for x in median_gain),
            positive_gain_rounds=sum(x > 0 for x in gain), phase_saved_ms={p:stats(x) for p,x in phase_gain.items()}))
    result = dict(status='COMPLETE' if len(case_rows)==32 else 'PARTIAL', audited_cases=len(case_rows),
        audited_frames=sum(len(r['frames']) for r in runs if r.get('audit_pass')), groups=groups,
        comparisons=comparisons, cases=case_rows,
        scope='SAME_NEW_BIT_150MHZ_INPUT_WINDOW16_OUTPUT_WINDOW128_NO_PC4K_OR_DISPLAY',
        p95_method='nearest rank; four rounds are the replication units',
        journal_timestamp_scope='TX before syscall; RX after recvfrom; not PHY or wire timestamps')
    (ROOT / 'SUMMARY.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=result['status'], frames=result['audited_frames'], groups={s:{v:dict(whole_mean=g['whole_ms']['mean'],whole_median=g['whole_ms']['median'],p95=g['whole_ms']['p95_nearest_rank'],input_mean=g['phase_ms']['input']['mean'],output_mean=g['phase_ms']['output_until_verified']['mean'],retries=g['retries'],round_means=g['round_mean_ms']) for v,g in vs.items()} for s,vs in groups.items()}, comparisons=comparisons), indent=2))


if __name__ == '__main__':
    main()
