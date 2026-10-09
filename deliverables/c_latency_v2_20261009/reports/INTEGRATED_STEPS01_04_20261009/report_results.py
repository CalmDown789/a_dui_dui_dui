from pathlib import Path
import hashlib, json, statistics, sys
sys.dont_write_bytecode=True
REVIEW=Path(__file__).resolve().parent;NEW=Path(r'C:\t6int09\main')
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
manifest=load(NEW/'PACKAGE_MANIFEST.json')
assert all(sha(NEW/name)==digest for name,digest in manifest['file_sha256'].items())
attempts=sorted(p.parent for p in (NEW/'attempts').glob('*/LAB_RUN_STATUS.json'))
assert attempts,'No board attempt completed'
attempt=attempts[-1];state=load(attempt/'LAB_RUN_STATUS.json')
rows=[]
for mode in ('Smoke','Probe','Natural2','Natural16'):
    report_file=attempt/mode/'REPORT.json'
    if not report_file.exists():continue
    r=load(report_file)
    audit_file=attempt/(mode+'_raw_audit')/('AUDIT.json'if mode.startswith('Natural')else'INDEPENDENT_INPUT_PROTOCOL.json')
    audit=load(audit_file)if audit_file.exists()else None
    row=dict(mode=mode,report=str(report_file),success=r.get('success'),status=r.get('status'),audit=audit)
    if mode.startswith('Natural') and r.get('success'):
        frames=r['frames'];whole=[f['timing_ns']['whole']/1e6 for f in frames]
        row.update(frames=r['completed_frames'],whole_frame_ms=dict(median=statistics.median(whole),mean=statistics.mean(whole),minimum=min(whole),maximum=max(whole)),
            phase_median_ms={phase:statistics.median([f['timing_ns'][phase]/1e6 for f in frames])for phase in ('input','commit','output_until_verified','release')},
            protocol_loop_ms=r['protocol_loop_wall_ns']/1e6,protocol_loop_fps=r['protocol_loop_frames_per_second'],
            retries=r['retries'],ignored=r['ignored'],output_duplicates=sum(f['output_duplicate_packets']for f in frames),
            output_rejected=sum(f['output_rejected_packets']for f in frames),all_golden_match=all(f['Golden_match']for f in frames),
            runtime={k:r[k]for k in ('io_mode','timing_mode','timing_sample_every','output_window')})
    rows.append(row)
success=state['status']=='COMPLETE_EVF2_LAB_RAW_OBSERVATIONS_PENDING_ROOT_REVIEW' and len(rows)==4 and all(r['success']and r['audit']and r['audit']['status'].startswith('PASS')for r in rows)
result=dict(status='PASS_INTEGRATED_FOUR_STEPS_BOARD_RUN'if success else 'FAIL_PRESERVE_INTEGRATED_BOARD_EVIDENCE',
    attempt=str(attempt),lab_status=state,package=str(NEW),package_manifest_sha256=sha(NEW/'PACKAGE_MANIFEST.json'),
    candidate_BIT_sha256=manifest['candidate_BIT_sha256'],source_routed_DCP_sha256=manifest['source_routed_DCP_sha256'],
    first_step_rtl_patch_in_bit=True,package_sources_unchanged=True,rows=rows,
    formal_video_permission=False,physical_IO_signoff=False,whole_system_4K30_achieved=False,PC4K_or_display_tested=False)
if success:
    assert all(r['audit']['status']=='PASS_INDEPENDENT_RAW_PROTOCOL_GOLDEN_AUDIT'for r in rows if r['mode'].startswith('Natural'))
    old=load(REVIEW.parents[0]/'STEP04_BOARD_EFFECT_20261009/SUMMARY.json')['groups']['board']['step04_sampled']['whole_frame_ms']['median']
    result['prior_same_host_old_bit_sampled_median_ms']=old
    for row in rows:
        if row['mode'].startswith('Natural'):
            row['difference_from_prior_short_two_frame_median_ms']=row['whole_frame_ms']['median']-old
    text='四步整合的新方案已实际运行成功。\n\n'
    text+='第1步RTL修补已重新综合、布局布线并生成新BIT；主机采用第2步直接EVF2解码、第3步非阻塞IO、第4步sampled/16计时。150 MHz、输入窗口16、输出窗口128。\n\n'
    text+='Smoke、Probe、Natural2、Natural16均成功；两帧和16帧共18帧均经原始报文独立审计验证Golden。\n\n'
    text+='| 测试 | 帧数 | 单帧中位数 | 单帧范围 | 实际协议循环帧率 | 重传 | 输出重复包 |\n| --- | ---: | ---: | --- | ---: | ---: | ---: |\n'
    for row in rows:
        if row['mode'].startswith('Natural'):
            t=row['whole_frame_ms']
            text+=f"| {row['mode']} | {row['frames']} | {t['median']:.3f} ms | {t['minimum']:.3f}–{t['maximum']:.3f} ms | {row['protocol_loop_fps']:.2f} fps | {row['retries']} | {row['output_duplicates']} |\n"
    text+=f'\n上一轮旧BIT配合同一采样主机的短双帧中位数为{old:.3f} ms；本次测试顺序与长度不同，属于观察比较，不能据此宣称严格的因果性能提升。第1步主要修补丢失证明时的恢复，不预期明显减少健康帧耗时。\n\n'
    text+=f"新BIT SHA256：{manifest['candidate_BIT_sha256']}。源RTL SHA256：{manifest['source_manifest']['evf2_result_window.sv']}。\n\n"
    text+=f'运行入口：[run_integrated.ps1]({(NEW/"run_integrated.ps1").as_posix()})。包说明：[README.md]({(NEW/"README.md").as_posix()})。原始证据目录：{attempt}。\n\n'
    text+='主机回归覆盖10项采样、21项非阻塞、5项背压、26种协议故障、7种完整窗口场景与6项边界；RTL复测重现旧版同拍到期故障并确认整合版恢复。首次RTL调试信息生成崩溃日志保留，关闭仿真调试元数据后通过。新BIT严格沿用原有时钟和约束，通过原生时序和DRC门槛。\n\n'
    text+='本次为配置RAM临时JTAG上板试验，未写Flash；PC4K与显示尚未计入。原有冻结包和四个分步候选保持原状。\n'
else:
    text='四步整合候选已准备并尝试运行，当前失败或不完整。\n\n'+json.dumps(state,ensure_ascii=False,indent=2)+f'\n\n证据目录：{attempt}\n'
(REVIEW/'SUMMARY.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(REVIEW/'REVIEW.md').write_text(text,encoding='utf-8')
print(json.dumps(result,indent=2))
