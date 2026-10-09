from pathlib import Path
import hashlib, json, shutil, statistics
ROOT = Path(__file__).resolve().parent
OUT = Path(r'C:\Users\Administrator\WorkBuddy\srtp\output\HOST_IO_BATCH_BOARD_AB_20261009')


def main():
    s = json.loads((ROOT / 'SUMMARY.json').read_text(encoding='utf-8'))
    receipt = json.loads((ROOT / 'FINAL_RECEIPT.json').read_text(encoding='utf-8'))
    cleanup = json.loads((ROOT / 'launcher/RESULT.json').read_text(encoding='utf-8-sig'))
    cleanup_review = json.loads((ROOT / 'launcher/OWNED_SERVER_CLEANUP.json').read_text(encoding='utf-8-sig'))
    assert s['status'] == 'COMPLETE' and s['audited_frames'] == 512
    assert receipt['status'] == 'PASS_ALL_32_CASES_512_FRAMES'
    assert cleanup['child_exit_code'] == 0
    assert cleanup_review['stopped_owned_server'] and cleanup_review['process_absent_after_stop']
    OUT.mkdir(parents=True, exist_ok=False)
    for name in ['SUMMARY.json', 'FINAL_RECEIPT.json', 'EXPERIMENT_MANIFEST.json', 'VALIDATION.json',
                 'input_batch_driver.py', 'run_experiments.py', 'run_experiments.ps1', 'summarize.py', 'finish_report.py']:
        shutil.copy2(ROOT / name, OUT / name)
    shutil.copy2(ROOT / 'launcher/RESULT.json', OUT / 'CLEANUP.json')
    shutil.copy2(ROOT / 'launcher/OWNED_SERVER_CLEANUP.json', OUT / 'OWNED_SERVER_CLEANUP.json')
    lines = ['已完成同一新BIT上的IO/计时与输入接收批量对照。', '',
        '每组4轮，每轮16帧；每次都重新RAM JTAG加载同一BIT，并通过实际UART启动身份检查。8组共512帧，全部原始报文独立Golden审计通过。输入窗口16、输出窗口128、150 MHz、数据、验证回调和原始日志保持一致。', '',
        '第一项使用原封不动的候选LAB入口；第二项使用外部实验子类，仅在input_packets期间切换接收批量，finally恢复输出批量32。处理预算200 µs保持不变。原候选包所有清单内文件经前后SHA256核对一致。timeout模式逐包读取；32包批读配置仅对nonblocking生效。', '',
        '| IO/计时 | 帧数 | 整帧中位数 | 整帧均值 | p95 | 输入均值 | 输出及验证均值 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name in ['timeout_full', 'timeout_sampled', 'nonblocking_full', 'nonblocking_sampled']:
        g = s['groups']['io_timing'][name]
        lines.append(f"| {name} | {g['frames']} | {g['whole_ms']['median']:.3f} ms | {g['whole_ms']['mean']:.3f} ms | {g['whole_ms']['p95_nearest_rank']:.3f} ms | {g['phase_ms']['input']['mean']:.3f} ms | {g['phase_ms']['output_until_verified']['mean']:.3f} ms |")
    lines += ['', '| 输入接收批量（nonblocking/sampled；输出32） | 帧数 | 整帧中位数 | 整帧均值 | p95 | 输入均值 | 输出及验证均值 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name in ['batch1', 'batch4', 'batch8', 'batch32']:
        g = s['groups']['input_batch'][name]
        lines.append(f"| {name} | {g['frames']} | {g['whole_ms']['median']:.3f} ms | {g['whole_ms']['mean']:.3f} ms | {g['whole_ms']['p95_nearest_rank']:.3f} ms | {g['phase_ms']['input']['mean']:.3f} ms | {g['phase_ms']['output_until_verified']['mean']:.3f} ms |")
    lines += ['', '以下是同一阶段内、按轮次匹配的整帧均值差，正数表示候选更快。每种配置只有4轮独立重复，不将64帧当成64次独立实验，也不据此宣称统计显著。', '',
              '| 对照 | 每轮节省ms | 平均节省ms | 均值下降 | 更快轮数 |',
              '| --- | --- | ---: | ---: | ---: |']
    for c in s['comparisons']:
        lines.append(f"| {c['baseline']} → {c['candidate']} | {', '.join(f'{x:.3f}' for x in c['round_mean_saved_ms'])} | {c['saved_ms_stats']['mean']:.3f} | {c['elapsed_reduction_percent']:.2f}% | {c['positive_gain_rounds']}/4 |")
    lines += ['', '输入ACK主机观察指标：', '',
              '| 批量 | 各轮ACK间隔中位数的中位数 | ACK首次被捕获到下一DATA发送的中位数 | 每帧>0.25ms ACK间隔数量均值 |',
              '| --- | ---: | ---: | ---: |']
    for name in ['batch1', 'batch4', 'batch8', 'batch32']:
        g = s['groups']['input_batch'][name]
        lines.append(f"| {name} | {g['input_ack_lag_median_ms']['median']:.4f} ms | {g['ack_capture_to_next_data_median_ms']['median']*1000:.1f} µs | {g['long_ack_gap_count_per_frame_mean']:.2f} |")
    lines += ['', '这些时间戳是发送调用前、recvfrom返回后的主机记录，包含日志、驱动和调度。批量读取会改变记录位置，因此ACK间隔中位数不能当作线缆RTT，也不能单独用来判断模式更快。', '',
        '完整汇总保留各轮结果、首帧/后续帧分布、最慢帧、控制重试和迟到缺失块。均值和p95保留全部帧，没有删除恢复长帧。', '',
        '原始记录中出现的先缺失、后补齐块只证明主机最终收到了这些块；不能独立确定丢失发生在发送、USB、驱动还是接收路径，也不能仅凭序号回退断言板端重传次数。', '',
        '本次仅验证LAB协议链路，未测PC4K、显示或跨帧流水，也未主动注入丢包。网卡配置未改变。', '',
        '结果判断：', '',
        '1. 四组IO/计时对照中，timeout/sampled整帧中位数76.717 ms，比nonblocking/sampled低2.246 ms；输入均值低2.221 ms。不过包含恢复长帧后的均值差仅0.923 ms，按轮次均值对照3/4轮更快。full条件下timeout在4/4轮均值都更快。默认非阻塞批读没有带来整体加速。', '',
        '2. 第二项中，输入批量1相对32，整帧中位数78.675→77.135 ms，减少1.539 ms（1.96%）；均值78.775→77.479 ms，减少1.296 ms（1.65%）。输入均值46.477→44.792 ms，减少1.685 ms；输出均值29.144→29.108 ms，基本不变。四轮中位数全部改善，节省分别1.962、1.262、1.452、1.526 ms。四轮均值3轮改善，另一轮近乎持平，受释放长帧影响。', '',
        '3. 输入批量1把ACK首次捕获到补发DATA的中位数从78.825降到8.500 µs；但ACK主机观察间隔仍约1.2–1.3 ms，输入仍约45 ms。因此确认批读延迟了窗口补发，但它只贡献了几毫秒开销，不能解释全部离线上板差距。', '',
        '4. 全部512帧Golden不匹配、输出重复与拒绝均为0。3次主机请求重试都发生于EVF1 HELLO，帧计时之外；帧内主机DATA/控制请求重试为0。另有6帧出现先缺失后补齐的输出块，全部独立审计成功；恢复和释放长帧已计入均值、最大值和p95。批量1也出现一帧100.234 ms的释放等待长帧，因此不把较好中位数解释为已经解决尾延迟。', '',
        '5. 建议保留sampled。若下一版继续使用nonblocking，可优先采用输入批量1、输出批量32；timeout/sampled也应作为后续实验对照。没有在本次试验中修改冻结包默认值。更大收益需继续定位真实反馈等待，或评估板端缓冲与输入扩窗。', '',
        '硬件服务器清理：原launcher finally未成功确认退出；随后按PID6688、唯一路径、启动时间与本次重定向日志创建时间匹配确认所有权，关闭且确认该进程消失。原RESULT与补充所有权清理记录均保留。UDP6102已释放，最后加载的仍为同一新BIT。', '',
        f"新BIT SHA256：{receipt['candidate_BIT_sha256']}。", '',
        '全部原始UART/JTAG、报文、实际输出和独立审计位于C:\\t6ab09\\cases。', '',
        '汇总：[SUMMARY.json](C:/Users/Administrator/WorkBuddy/srtp/output/HOST_IO_BATCH_BOARD_AB_20261009/SUMMARY.json)。实验入口与来源SHA：[EXPERIMENT_MANIFEST.json](C:/Users/Administrator/WorkBuddy/srtp/output/HOST_IO_BATCH_BOARD_AB_20261009/EXPERIMENT_MANIFEST.json)。']
    (OUT / 'REVIEW.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}
    (OUT / 'ARTIFACT_RECEIPT.json').write_text(json.dumps(dict(status='SAVED_COMPLETE_AUDITED_RESULTS', artifact_sha256=hashes,
        raw_evidence_root=str(ROOT/'cases'), stopped_owned_hardware_server=cleanup_review['stopped_owned_server']), indent=2), encoding='utf-8')
    print(str(OUT / 'REVIEW.md'))


if __name__ == '__main__':
    main()
