"""Bind the continuous PC4K measurement entry to a verified new COMM package."""
from pathlib import Path
import argparse, hashlib, json, shutil, zipfile
HERE=Path(__file__).resolve().parent; STREAM=HERE.parent; ROOT=STREAM.parents[2]


def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--package',type=Path,required=True)
    a=ap.parse_args(); primary=a.package.resolve()
    issued=json.loads((STREAM/'C_PACKAGE.json').read_text(encoding='utf-8'))
    assert primary==Path(issued['directory']) and sha(primary/'PACKAGE_MANIFEST.json')==issued['PACKAGE_MANIFEST_sha256']
    checked=json.loads((STREAM/'LATEST_package_check.json').read_text(encoding='utf-8'))
    validation=json.loads((Path(checked['saved_directory'])/'RESULTS.json').read_text(encoding='utf-8'))
    assert validation['status']=='PASS_PACKAGE_INVENTORY_AND_PRE_SOCKET_GUARDS'
    assert validation['archive_sha256']==issued['archive_sha256']==sha(issued['archive'])
    check=json.loads((HERE/'LATEST_engine.json').read_text(encoding='utf-8'))
    engine=json.loads((Path(check['saved_directory'])/'RESULTS.json').read_text(encoding='utf-8'))
    assert engine['status']=='PASS_INJECTED_TRANSPORT_REAL_CUDA_CONTINUOUS_ENGINE'
    for rel,digest in engine['source_sha256'].items(): assert sha(ROOT/rel)==digest
    additional_checks={}
    for tag,expected_status in [('app','PASS_REAL_TK_APP_PIXELS_ID_AND_QUEUE_HANDOFF'),('audit','PASS_INDEPENDENT_STREAMING_AUDITOR_FAULT_CHECKS'),
                              ('pc_path','PASS_PC_ONLY_150_PACED_CUDA_4K_TK_FRAMES_NOT_BOARD_RATE'),
                              ('fast_wire','PASS_PREENCODED_150_FRAME_HOST_CUDA_TK_STREAM_AUDIT_NOT_BOARD_RATE')]:
        report=Path(json.loads((HERE/('LATEST_'+tag+'.json')).read_text(encoding='utf-8'))['saved_directory'])/'RESULTS.json'
        verified=json.loads(report.read_text(encoding='utf-8'));assert verified['status']==expected_status
        for rel,digest in verified['source_sha256'].items():assert sha(ROOT/rel)==digest
        additional_checks[tag]=report
    pack_guard_report=Path(json.loads((STREAM/'LATEST_pack_writer_guard.json').read_text(encoding='utf-8'))['saved_directory'])/'RESULTS.json'
    pack_guard=json.loads(pack_guard_report.read_text(encoding='utf-8'))
    assert pack_guard['status']=='PASS_ACTUAL_PACK_WRITER_GUARDS_PS51_AND_PS7'
    for rel,digest in pack_guard['source_sha256'].items():assert sha(STREAM/rel)==digest
    assert sha(primary/'proof/pack_writer_guard/RESULTS.json')==sha(pack_guard_report)
    output=ROOT/'output/COMM_PC4K_MEASURE_20261007_150'; output.mkdir(exist_ok=False)
    for name in ('live4k.py','engine.py','audit_live4k.py','check_engine.py','check_app.py','check_audit.py','make_supplement.py','check_pc_path_sustained.py','check_fast_wire.py'):
        shutil.copy2(HERE/name,output/name)
    script=(HERE/'run_live4k.ps1').read_text(encoding='utf-8')
    original=(primary/'lab/run_c_streaming.ps1').read_text(encoding='utf-8')
    network=original[original.index('function Check-LabNetwork'):original.index('function Assert-LabCaptureWritersStopped')]
    assert script.count('# NETWORK_GUARD_INSERT')==1
    (output/'run_live4k.ps1').write_text(script.replace('# NETWORK_GUARD_INSERT',network),encoding='utf-8')
    (output/'pc4k').mkdir()
    for name in ('pipeline.py','reference.py'):
        shutil.copy2(ROOT/'experiments/pc_4k_20261007'/name,output/'pc4k'/name)
    (output/'proof').mkdir(); shutil.copy2(Path(check['saved_directory'])/'RESULTS.json',output/'proof/LOCAL_ENGINE_CHECK.json')
    for tag,report in additional_checks.items():
        shutil.copy2(report,output/'proof'/('LOCAL_'+tag.upper()+'_CHECK.json'))
    config=json.loads((primary/'STREAMING_SELECTION.json').read_text(encoding='utf-8'))
    guide='''# 新通信BIT：连续4K生成和内屏缩放测量补充包

配合已独立校验的新 `COMM_TO_C_20261007_150` 主包使用。此补充包不含BIT，不改主包。先完成主包的Natural2/Natural16及原始审计，再用主包记录的真实post-JTAG启动捕获进入本测量；无需重新装载镜像。不能借用旧B三槽BIT的捕获。

解压例如 `E:\\COMM_PC4K_20261007`。Python环境需已有numpy、opencv-python、Pillow、Tk；CUDA入口另需已有可用CUDA版PyTorch。C电脑配置尚未核实，CPU入口必须显式选择，不自动代替CUDA。

文件预检不导入GPU依赖，不开UART/JTAG/socket：

```powershell
& 'C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe' -B 'E:\\COMM_PC4K_20261007\\live4k.py' --package 'E:\\COMM_150_20261007' --files-only --out-dir 'E:\\COMM_PC4K_20261007\\preflight_新attempt'
```

正式执行前确认主包保存的网卡/IP/永久邻居未变化，UDP6102空闲。以下命令使用主包实际打印的Natural16启动捕获路径；目录必须是新的attempt。程序不修改网卡、不执行JTAG、不写Flash，按真实身份/启动/PHY检查后才创建socket。保留主包网络快照并记录是否变更。

```powershell
& 'C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe' -B -u -X faulthandler 'E:\\COMM_PC4K_20261007\\live4k.py' --package 'E:\\COMM_150_20261007' --startup-capture-report 'E:\\COMM_150_20261007\\attempts\\实际Run目录\\startup_for_16\\REPORT.json' --backend torch-cuda-f64 --seconds 300 --fps 30 --out-dir 'E:\\COMM_PC4K_20261007\\live_新attempt'
```

这是9000个目标输入槽，16份冻结预录输入/Golden循环、唯一frame_id。迟到的槽继续用自己的ID记录，不降低实际提供速率或重复显示掩盖失败；队列暂满最多等待500ms，此前不发最终释放ACK；超时拒绝该帧，等待/迟到照实记录，不扩大队列。最多约610秒执行窗口，再受单帧10秒截止约束。启动时逐源建立独立整数4K参考并校验实际后端；每个新输出仍完整重新计算和逐像素核对。1280×720是默认缩放画布，可指定预览尺寸；记录实际缩放提交尺寸，不宣称面板全画面原生4K显示。

原始UDP报文全部保留，9000帧的正常流量约几十GB。准备阶段检查约83GB空闲余量（3倍正常流量和2GiB）；日志SHA和审计使用流式读取。关闭预览会停止后续输入并排空已接收任务，失败证据保留。CPU后端参数为 `--backend opencv-f64`，性能单独记录。

中途失败、队列拒绝或关闭预览后，未获最终确认的帧会留在板端；先保留并打包原attempt。下一次测量通过主包 `-Mode Run` 重新临时JTAG、启动捕获及Natural2/Natural16，使用该次真实Natural16 REPORT；不要用旧捕获绕过仍活动的帧/会话。

结束后独立审计：

```powershell
& 'C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe' -B 'E:\\COMM_PC4K_20261007\\audit_live4k.py' --package 'E:\\COMM_150_20261007' --run 'E:\\COMM_PC4K_20261007\\live_实际attempt' --out-dir 'E:\\COMM_PC4K_20261007\\audit_新attempt'
```

`measurement/RESULTS.json`分别记录协议完成、4K生成、应用缩放提交在目标窗口中的帧率、实际输入到输出排空跨度、每秒计数、帧间隔、延迟、迟到/未尝试/队列拒绝/重复与缺失ID。全程原始1080p回传可独立重审Golden/CRC/证明/释放；每帧4K运行时全像素核对，事件SHA可对独立参考复核，只保存末帧完整4K和应用画布PNG，不保存所有4K raw。应用提交不等于面板刷新，数值正确和实测速率分别验收。收尾fsync/整日志SHA在输出排空后执行，另记耗时与失败，未通过不能作为完整证据；它不计入运行跨度。Tk/Pillow实际首张准备画面在网络/计时前预热，明确不计帧。完成测量不自动将整机4K30标为已达成。

将完整attempt、独立audit、主包原始身份/网络快照和本补充包SHA一起回传。较短试跑可用 `--seconds 5`；这些是测量入口默认值，未将5分钟阈值登记为新的生效任务书要求。本机工程检查使用内存传输，不证明实板帧率；电气UNVERIFIED、正式video许可false保持。
'''
    (output/'README.md').write_text(guide,encoding='utf-8')
    with (output/'README.md').open('a',encoding='utf-8') as f:
        f.write('''
推荐通过补充包PowerShell入口执行，它沿用主包完全相同的网卡检查，并使用原诊断helper保留30秒调用栈及首sendto前120秒监督：

```powershell
& 'E:\\COMM_PC4K_20261007\\run_live4k.ps1' -Mode Run -CommPackage 'E:\\COMM_150_20261007' -Python 'C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe' -StartupCaptureReport 'E:\\COMM_150_20261007\\attempts\\实际Run目录\\startup_for_16\\REPORT.json' -Backend torch-cuda-f64 -Seconds 300 -Fps 30
```

随后用相同入口的 `-Mode Audit -RunRoot '实际打印的attempt路径'` 复核，`-Mode Pack -RunRoot '同一attempt路径'` 打包全部证据，失败也Pack。Preflight可用 `-Mode Preflight`，不执行硬件/网络操作。每次入口均填上同一 `-CommPackage` 和实际 `-Python`；Run前后保存真实网卡快照，不改配置。只把真实启动捕获及完整审计通过后的测量解释为本BIT实测。
''')
    cfg=dict(scope='EXACT_COMM_PACKAGE_PC4K_MEASUREMENT_SUPPLEMENT_V1',candidate_BIT_sha256=config['candidate_BIT_sha256'],
             comm_package_manifest_sha256=sha(primary/'PACKAGE_MANIFEST.json'),streaming_selection_sha256=sha(primary/'STREAMING_SELECTION.json'),
             whole_system_4K30_achieved=False,formal_video_permission=False,physical_IO_signoff=False,
             model_changed=False,core_hz=150000000,pause=0,
             files=[dict(file=p.relative_to(output).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(output.rglob('*')) if p.is_file()])
    (output/'SUPPLEMENT_MANIFEST.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(output).as_posix())
    receipt=dict(status='ISSUED_FILES_ONLY_NO_BOARD_RUN',directory=str(output),archive=str(archive),archive_sha256=sha(archive),
                 archive_bytes=archive.stat().st_size,primary_archive_sha256=issued['archive_sha256'],board_test=False,whole_system_4K30_achieved=False)
    (HERE/'SUPPLEMENT_PACKAGE.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__': main()
