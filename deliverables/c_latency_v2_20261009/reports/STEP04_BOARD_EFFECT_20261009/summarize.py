from pathlib import Path
import hashlib, json, statistics, sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
BOARD = Path(r'C:\t6s4board09')
STEP4 = ROOT.parents[1]/'output/HOST_STEP04_SAMPLED_TIMING_20261009'
sys.path.insert(0, r'C:\t6dup09\main\streaming')
from binary_journal import records
from audit_protocol import parse
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def stats(values):
    return dict(count=len(values), median=statistics.median(values), mean=statistics.mean(values),
                minimum=min(values), maximum=max(values))
all_rows = []
for environment, folders in [('board', sorted(BOARD.glob('*_step*'))), ('offline', sorted((ROOT/'offline').glob('*_step*')))]:
    for folder in folders:
        run = folder/'run' if environment == 'board' else folder
        r = load(run/'REPORT.json')
        if environment == 'board':
            audit = load(folder/'audit/AUDIT.json')
            assert r['success'] and audit['status'] == 'PASS_INDEPENDENT_RAW_PROTOCOL_GOLDEN_AUDIT'
            assert audit['Golden_mismatches'] == 0
            assert r['candidate_BIT_sha256'] == '81377cedf56706a2de904344a8684bdaffcd1e46f3ffa8e65da6a5e1ff584c0e'
            assert all(sha(Path(p)) == digest for p,digest in r['runtime_sources_sha256'].items())
        else:
            audit = r['audit']
            assert r['status'] == 'PASS'
        timing = load(run/'traffic/TIMING_DIAGNOSTICS.json')
        sent, lags = {}, []
        raw_count = 0
        for stamp, direction, raw, source in records(run/'traffic/datagrams.bin'):
            raw_count += 1
            version,p = parse(raw)
            if direction == 0 and version == 1 and p.type == 3: sent[p.frame_id,p.sequence] = stamp
            if direction == 1 and version == 1 and p.type == 0x83:
                lags.append((stamp-sent[p.frame_id,p.sequence])/1e6)
        row = dict(environment=environment, variant=r['variant'], path=str(run),
                   frames=r['frames'], audit=audit, retries=r['retries'], ignored=r['ignored'],
                   hello_and_two_frames_wall_ms=r['hello_and_two_frames_wall_ns']/1e6,
                   calling_thread_cpu_ms=r['calling_thread_cpu_ns']/1e6,
                   input_data_ack_host_observed_lag_ms=stats(lags), raw_journal_records=raw_count,
                   raw_journal_sha256=sha(run/'traffic/datagrams.bin'),
                   readiness_wait_calls=timing['counters'].get('io_readiness_wait_calls',0),
                   readiness_wait_ms=timing['stages'].get('readiness_wait',{}).get('wall_total_ns',0)/1e6)
        assert all(f['Golden_match'] and not f['output_duplicate_packets'] and not f['output_rejected_packets'] for f in row['frames'])
        all_rows.append(row)
groups = {}
for environment in ('board','offline'):
    groups[environment] = {}
    for variant in ('step03_full','step04_sampled','step04_full'):
        rows = [r for r in all_rows if r['environment']==environment and r['variant']==variant]
        if not rows: continue
        frames = [f for r in rows for f in r['frames']]
        groups[environment][variant] = dict(runs=len(rows), frames=len(frames),
            whole_frame_ms=stats([f['timing_ns']['whole']/1e6 for f in frames]),
            phase_ms={phase:stats([f['timing_ns'][phase]/1e6 for f in frames]) for phase in ('input','commit','output_until_verified','release')},
            hello_and_two_frames_wall_ms=stats([r['hello_and_two_frames_wall_ms'] for r in rows]),
            calling_thread_cpu_ms_per_two_frames=stats([r['calling_thread_cpu_ms'] for r in rows]),
            input_data_ack_host_observed_lag_median_ms=statistics.median([r['input_data_ack_host_observed_lag_ms']['median'] for r in rows]),
            readiness_wait_calls_total=sum(r['readiness_wait_calls'] for r in rows),
            readiness_wait_ms_per_two_frames=stats([r['readiness_wait_ms'] for r in rows]),
            retries_total=sum(r['retries'] for r in rows), ignored_total=sum(r['ignored'] for r in rows))
comparisons = {}
for environment,g in groups.items():
    baseline, sampled = g['step03_full']['whole_frame_ms']['median'], g['step04_sampled']['whole_frame_ms']['median']
    comparisons[environment] = dict(saved_ms_per_frame=baseline-sampled, elapsed_reduction_percent=100*(1-sampled/baseline))
baseline_board = groups['board']['step03_full']['whole_frame_ms']['median']
sampled_board = groups['board']['step04_sampled']['whole_frame_ms']['median']
baseline_offline = groups['offline']['step03_full']['whole_frame_ms']['median']
sampled_offline = groups['offline']['step04_sampled']['whole_frame_ms']['median']
comparisons['board_vs_offline'] = dict(step03_extra_ms=baseline_board-baseline_offline,
    step04_extra_ms=sampled_board-sampled_offline, step04_extra_percent=100*(sampled_board/sampled_offline-1))
receipt = load(STEP4/'FINAL_RECEIPT.json')
assert all(sha(STEP4/name)==digest for name,digest in receipt['artifact_sha256'].items())
summary = dict(status='PASS_SHORT_BOARD_AND_OFFLINE_COMPARISON', groups=groups, comparisons=comparisons,
               board_total_frames=sum(r['environment']=='board' for r in all_rows)*2,
               offline_total_frames=sum(r['environment']=='offline' for r in all_rows)*2,
               input_and_golden_identical=True, step04_frozen_receipt_unchanged=True,
               first_step_rtl_patch_in_bit=False, actual_30fps_proven=False,
               per_frame_boundary='BEGIN through verified Golden, journal checkpoint and FRAME_DONE; HELLO excluded',
               offline_peer_executes_in_calling_thread=True,
               cpu_clock_quantum_note='Windows thread CPU results have approximately 15.625 ms granularity; do not infer sub-ms CPU savings',
               sustained_throughput_tested=False, PC4K_or_display_tested=False, rows=all_rows)
(ROOT/'SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
md = f'''本次上板成功：7次重新加载现有BIT、各传2帧，共14帧；所有原始报文独立审计通过，Golden不匹配、重传、重复包均为0。

同数据离线复测3轮/模式，上板主对比3轮/模式。下表为各模式6帧单帧耗时中位数，BEGIN到FRAME_DONE，包含输入、输出验证与释放，不含HELLO。

| 模式 | 本次离线复测 | 实际上板 |
| --- | ---: | ---: |
| 第3步 full | {baseline_offline:.3f} ms | {baseline_board:.3f} ms |
| 第4步 sampled / 16 | {sampled_offline:.3f} ms | {sampled_board:.3f} ms |
| 第4步收益 | {comparisons['offline']['elapsed_reduction_percent']:.2f}% / {baseline_offline-sampled_offline:.3f} ms | {comparisons['board']['elapsed_reduction_percent']:.2f}% / {baseline_board-sampled_board:.3f} ms |

第4步上板比本次离线单帧多{sampled_board-sampled_offline:.3f} ms，约{comparisons['board_vs_offline']['step04_extra_percent']:.1f}%。上板full范围{groups['board']['step03_full']['whole_frame_ms']['minimum']:.3f}–{groups['board']['step03_full']['whole_frame_ms']['maximum']:.3f} ms，sampled范围{groups['board']['step04_sampled']['whole_frame_ms']['minimum']:.3f}–{groups['board']['step04_sampled']['whole_frame_ms']['maximum']:.3f} ms；范围重叠，1%左右收益不足以证明稳定的端到端提升。

第4步采样阶段中位数：上板输入{groups['board']['step04_sampled']['phase_ms']['input']['median']:.3f} ms、输出及验证{groups['board']['step04_sampled']['phase_ms']['output_until_verified']['median']:.3f} ms；离线分别{groups['offline']['step04_sampled']['phase_ms']['input']['median']:.3f} ms、{groups['offline']['step04_sampled']['phase_ms']['output_until_verified']['median']:.3f} ms。上板输入DATA发出到ACK被主机记录的中位间隔约{groups['board']['step04_sampled']['input_data_ack_host_observed_lag_median_ms']:.3f} ms，输入窗口仍为16。实际传输/等待占比显著，降低主机诊断开销较少改变整体耗时。该间隔含主机调度和驱动，不是硬件线速RTT；未单独测得CNN核时间。

离线Peer在主机同一线程内编码/解码，因此不能把离线耗时当作板卡延迟。本次离线采用与上板相同PreparedGolden、验证回调、逐帧事件写入和计时边界；早先报告的HELLO+两帧折算均值67.63/58.62 ms不能直接当成本表的单帧中位数。

另测第4步full两帧{', '.join(f"{f['timing_ns']['whole']/1e6:.3f}" for r in all_rows if r['environment']=='board' and r['variant']=='step04_full' for f in r['frames'])} ms，也通过审计，样本少，仅作观察。

使用原有BIT SHA256 81377cedf56706a2de904344a8684bdaffcd1e46f3ffa8e65da6a5e1ff584c0e，尚未包含第1步RTL修补。只RAM JTAG加载，未改Flash、冻结包、正式入口或网卡配置。本次是短双帧传输，未测长序列稳定性、PC4K或显示；约79 ms/帧仍高于30 fps的33.33 ms预算。

完整机器可读结果：[SUMMARY.json]({(ROOT/'SUMMARY.json').as_posix()})。所有UART/JTAG、原始UDP报文、实际输出和独立审计见 C:\\t6s4board09；同数据离线原始日志见本目录offline。
'''
(ROOT/'REVIEW.md').write_text(md,encoding='utf-8')
print(json.dumps(dict(status=summary['status'], groups=groups, comparisons=comparisons),indent=2))
