from pathlib import Path
import hashlib, json, shutil, sys
sys.dont_write_bytecode = True
REVIEW = Path(__file__).resolve().parent
WORK = REVIEW.parents[1]
BASE = Path(r'C:\t6dup09\main')
NEW = Path(r'C:\t6int09\main')
STEP1 = WORK/'output/RTL_STEP01_RETRY_20261009'
STEP4 = WORK/'output/HOST_STEP04_SAMPLED_TIMING_20261009'
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
NEW.mkdir(parents=True,exist_ok=False)
for folder in ('rtl','host','scripts','lab','diagnostics','streaming','data'):
    shutil.copytree(BASE/folder, NEW/folder, ignore=shutil.ignore_patterns('__pycache__','attempts','host_runs','.Xil'))
(NEW/'provenance').mkdir()
for name in ('PACKAGE_MANIFEST.json','LAB_FUNCTIONAL_SELECTION.json','STREAMING_SELECTION.json'):
    shutil.copy2(BASE/name, NEW/'provenance'/('BASE_'+name))
for step in (STEP1,STEP4):
    for name in ('SOURCE_MANIFEST.json','FINAL_RECEIPT.json'):
        shutil.copy2(step/name, NEW/'provenance'/(step.name+'_'+name))
    receipt=load(step/'FINAL_RECEIPT.json')
    for name,digest in receipt.get('artifact_sha256',{}).items(): assert sha(step/name)==digest,name
base_image=load(BASE/'image/BOARD_CHARACTERIZATION_MANIFEST.json')
for name,digest in base_image['COMM_source_manifest'].items(): assert sha(NEW/'rtl'/name)==digest,name
assert sha(STEP1/'rtl/evf2_result_window.sv')=='a4bc4b7c3f0a843803ab5df2a3e80f7c592286282394f160a9d48bbbfbc1f901'
shutil.copy2(STEP1/'rtl/evf2_result_window.sv',NEW/'rtl/evf2_result_window.sv')
for row in load(STEP4/'SOURCE_MANIFEST.json')['files']:
    if row['file'].startswith(('host/','streaming/')):
        p=STEP4/'main'/row['file']; assert sha(p)==row['candidate_sha256']
        shutil.copy2(p,NEW/row['file'])
# Explicit candidate entry enables all three host optimizations together.
entry=NEW/'lab/streaming_board_lab.py'
text=entry.read_text(encoding='utf-8')
anchor="    ap.add_argument('--timeout', type=float, default=.02)"
assert text.count(anchor)==1
text=text.replace(anchor,"    ap.add_argument('--io-mode', choices=('timeout','nonblocking'), default='nonblocking')\n"
    "    ap.add_argument('--timing-mode', choices=('full','sampled'), default='sampled')\n"
    "    ap.add_argument('--timing-sample-every', type=int, default=16)\n"+anchor)
anchor="    'streaming/timing_diagnostics.py',"
assert text.count(anchor)==1
text=text.replace(anchor,anchor+" 'streaming/nonblocking_io.py',")
anchor='timeout=a.timeout, attempts=a.attempts, frame_timeout=a.frame_timeout)'
assert text.count(anchor)==1
text=text.replace(anchor,'timeout=a.timeout, attempts=a.attempts, frame_timeout=a.frame_timeout,\n'
    '                                 io_mode=a.io_mode, timing_mode=a.timing_mode, timing_sample_every=a.timing_sample_every)')
anchor="        began = time.perf_counter_ns()\n        for f, (pixels, golden) in enumerate(prepared):"
assert text.count(anchor)==1
text=text.replace(anchor,"        began = time.perf_counter_ns(); cpu_began = time.thread_time_ns()\n        for f, (pixels, golden) in enumerate(prepared):")
text=text.replace('        end = time.perf_counter_ns()\n        client.finish()', '        end = time.perf_counter_ns(); cpu_end = time.thread_time_ns()\n        client.finish()')
text=text.replace('                      protocol_loop_wall_ns=end-began, completed_frames=len(actual),',
    '                      protocol_loop_wall_ns=end-began, calling_thread_cpu_ns=cpu_end-cpu_began,\n'
    '                      frames=client.frames, io_mode=a.io_mode, timing_mode=a.timing_mode,\n'
    '                      timing_sample_every=a.timing_sample_every, completed_frames=len(actual),')
entry.write_text(text,encoding='utf-8')
# Full source synthesis, then incremental implementation against the last verified routed design.
build=NEW/'implementation'; build.mkdir()
for p in (NEW/'rtl').iterdir():
    if p.is_file(): shutil.copy2(p,build/p.name)
shutil.copy2(BASE/'implementation/physical_routed.dcp',build/'incremental_reference.dcp')
assert sha(build/'incremental_reference.dcp')==base_image['source_routed_DCP_sha256']
tcl=(BASE/'implementation/candidate_build.tcl').read_text(encoding='utf-8')
tcl=tcl.replace('write_checkpoint physical_routed.dcp','write_checkpoint -force physical_routed.dcp')
anchor='puts {COMM_BYTE_PIPELINE_PHYSICAL_150_PASS_NOT_BOARD_VALIDATED_NO_BIT}\nexit'
assert tcl.count(anchor)==1
tcl=tcl.replace(anchor,'write_bitstream COMM_steps01_04_150_lab_candidate.bit\n'
    'puts {INTEGRATED_STEPS01_04_DIGITAL_PASS_BIT_CREATED}\nexit')
(build/'build_integrated.tcl').write_text(tcl,encoding='utf-8')
bound={str(p.relative_to(NEW)):sha(p) for folder in ('rtl','streaming') for p in (NEW/folder).iterdir() if p.is_file()}
receipt=dict(status='ASSEMBLED_BUILD_PENDING', package=str(NEW), build=str(build),
    step01_rtl_sha256=sha(NEW/'rtl/evf2_result_window.sv'), step04_host_sha256=sha(NEW/'streaming/streaming_client.py'),
    source_sha256=bound, build_script_sha256=sha(build/'build_integrated.tcl'),
    incremental_reference_sha256=sha(build/'incremental_reference.dcp'),
    runtime=dict(io_mode='nonblocking',timing_mode='sampled',timing_sample_every=16,output_window=128),
    original_package_manifest_sha256=sha(BASE/'PACKAGE_MANIFEST.json'), formal_video_permission=False)
(REVIEW/'ASSEMBLY.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='source_sha256'},indent=2))
