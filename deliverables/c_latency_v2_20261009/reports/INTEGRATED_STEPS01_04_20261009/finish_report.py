from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,statistics,zipfile,sys
sys.dont_write_bytecode=True
REVIEW=Path(__file__).resolve().parent;NEW=Path(r'C:\t6int09\main');BASE=Path(r'C:\t6dup09\main')
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n',encoding='utf-8')
summary=load(REVIEW/'SUMMARY.json');comparison=load(REVIEW/'COMPARISON_RUNS.json')
assert len(comparison)==6
assert all(all(r[k]==0 for k in ('startup_exit_code','run_exit_code','audit_exit_code'))for r in comparison)
assert all(r['audit']['status']=='PASS_INDEPENDENT_RAW_PROTOCOL_GOLDEN_AUDIT'and r['audit']['Golden_mismatches']==0 for r in comparison)
assert all(r['retries']==r['ignored']==0 for r in comparison)
stats={}
for variant in ('original','integrated'):
    rows=[r for r in comparison if r['variant']==variant]
    values=[v for r in rows for v in r['frame_ms']]
    stats[variant]=dict(runs=len(rows),frames=len(values),median_ms=statistics.median(values),mean_ms=statistics.mean(values),
        minimum_ms=min(values),maximum_ms=max(values),phase_median_ms={phase:statistics.median(f['timing_ns'][phase]/1e6 for r in rows for f in r['frames'])for phase in ('input','commit','output_until_verified','release')})
old,new=stats['original'],stats['integrated']
stats['median_elapsed_reduction_percent']=100*(1-new['median_ms']/old['median_ms'])
stats['mean_elapsed_reduction_percent']=100*(1-new['mean_ms']/old['mean_ms'])
summary.update(comparison=stats,comparison_rows=comparison,integrated_board_frames=24,original_comparison_frames=6,
    total_board_frames_audited=30,board_Golden_mismatches=0,board_retries=0,board_output_duplicates=0,
    conclusion='ALL_FOUR_STEPS_INTEGRATED_AND_BOARD_FUNCTIONAL_PASS_NO_CLEAR_HEALTHY_FRAME_LATENCY_GAIN',
    completed_UTC=datetime.now(timezone.utc).isoformat())
manifest=load(NEW/'PACKAGE_MANIFEST.json')
assert all(sha(NEW/name)==digest for name,digest in manifest['file_sha256'].items())
assert sha(BASE/'PACKAGE_MANIFEST.json')==manifest['origin_package_manifest_sha256']
assert sha(BASE/'image/COMM_window128_150_lab_candidate.bit')=='81377cedf56706a2de904344a8684bdaffcd1e46f3ffa8e65da6a5e1ff584c0e'
assert load(Path(r'C:\t6int09\comparison_launcher\RESULT.json'))['stopped_owned_server'] is True
assert comparison[-1]['variant']=='integrated' and comparison[-1]['candidate_BIT_sha256']==manifest['candidate_BIT_sha256']
summary['last_successfully_programmed_test_BIT_sha256']=manifest['candidate_BIT_sha256']
save(REVIEW/'SUMMARY.json',summary)
save(NEW/'BOARD_TEST_RECEIPT.json',summary)
text=(REVIEW/'REVIEW.md').read_text(encoding='utf-8')
text+='\n四步前原包与整合方案交错对照，各3次重新加载BIT、每次2帧。\n\n'
text+='| 方案 | 单帧中位数 | 单帧均值 | 范围 |\n| --- | ---: | ---: | --- |\n'
for label,row in [('修改前原包（旧BIT、原主机timeout/full）',old),('四步整合（新BIT、nonblocking/sampled16）',new)]:
    text+=f"| {label} | {row['median_ms']:.3f} ms | {row['mean_ms']:.3f} ms | {row['minimum_ms']:.3f}–{row['maximum_ms']:.3f} ms |\n"
text+=f"\n中位数下降{old['median_ms']-new['median_ms']:.3f} ms（{stats['median_elapsed_reduction_percent']:.2f}%），均值反而增加{new['mean_ms']-old['mean_ms']:.3f} ms。波动范围重叠，不能据此认定健康帧端到端耗时有明确收益。\n"
text+='\n新方案总计24帧（2帧检查+16帧连续+6帧对照），原包对照6帧，总计30帧独立Golden审计均通过，重传与输出重复包为0。第1步的同拍到期丢失修补通过RTL因果复测；这次上板对照未主动注入丢包。\n'
text+='\n构建经历增量布局失败、完整布局后单条77 ps建立违例，最终从实际布线检查点进一步优化；最终建立余量0.018 ns、保持余量0.050 ns，DRC无错误/严重违例。失败日志均保留。全部试验完成后，已停止本次创建的硬件服务器，最后加载的是新BIT。\n'
text+='\n运行包：[INTEGRATED_STEPS01_04_runtime.zip](INTEGRATED_STEPS01_04_runtime.zip)。完整构建检查点和原始上板证据保存在C:\\t6int09。压缩包包括运行所需源码、权重、测试帧、BIT、最终DCP、身份检查工具和审计结果，省略中间构建检查点及大量原始报文。\n'
(REVIEW/'REVIEW.md').write_text(text,encoding='utf-8')
archive=REVIEW/'INTEGRATED_STEPS01_04_runtime.zip'
folders=('rtl','host','scripts','lab','diagnostics','streaming','data','image','provenance')
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
    for folder in folders:
        for p in (NEW/folder).rglob('*'):
            if p.is_file()and '__pycache__'not in p.parts:z.write(p,'main/'+p.relative_to(NEW).as_posix())
    for name in ('PACKAGE_MANIFEST.json','BOARD_TEST_RECEIPT.json','run_integrated.ps1','README.md'):
        z.write(NEW/name,'main/'+name)
    z.write(REVIEW/'REVIEW.md','RESULTS.md')
    z.write(REVIEW/'SUMMARY.json','SUMMARY.json')
    for p in (NEW/'implementation_refine').glob('*.rpt'):z.write(p,'build_reports/'+p.name)
with zipfile.ZipFile(archive)as z:
    assert z.testzip()is None
    for name,digest in manifest['file_sha256'].items():assert hashlib.sha256(z.read('main/'+Path(name).as_posix())).hexdigest()==digest,name
receipt=dict(status='PASS_FOUR_STEPS_INTEGRATED_BOARD_AND_RUNTIME_ARCHIVE',candidate_package_manifest_sha256=sha(NEW/'PACKAGE_MANIFEST.json'),
    runtime_archive=dict(file=archive.name,sha256=sha(archive),bytes=archive.stat().st_size),
    integrated_board_frames=24,total_board_frames_audited=30,all_Golden_match=True,original_package_unchanged=True,
    final_native_setup_ns=.018,final_native_hold_ns=.050,
    artifacts={p.name:sha(p)for p in REVIEW.iterdir()if p.is_file()and p.name!='FINAL_RECEIPT.json'})
save(REVIEW/'FINAL_RECEIPT.json',receipt)
print(json.dumps(dict(status=receipt['status'],comparison=stats,runtime_archive=receipt['runtime_archive']),indent=2))
