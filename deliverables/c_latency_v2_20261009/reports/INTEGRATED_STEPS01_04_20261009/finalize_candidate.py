from pathlib import Path
from datetime import datetime, timezone
import ast, hashlib, json, re, shutil, sys
sys.dont_write_bytecode=True
REVIEW=Path(__file__).resolve().parent
BASE=Path(r'C:\t6dup09\main');NEW=Path(r'C:\t6int09\main');BUILD=NEW/'implementation'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n',encoding='utf-8')
assembly=load(REVIEW/'ASSEMBLY.json')
BUILD=Path(assembly['build'])
assert all(sha(NEW/name)==digest for name,digest in assembly['source_sha256'].items())
assert sha(BUILD/'build_integrated.tcl')==assembly['build_script_sha256']
log=(BUILD/'integrated_build.log').read_text(encoding='utf-8',errors='replace')
assert 'INTEGRATED_STEPS01_04_DIGITAL_PASS_BIT_CREATED' in log and 'ERROR:' not in log
assert all(row['exit_code']==0 for row in load(REVIEW/'HOST_REGRESSION.json'))
assert load(REVIEW/'RTL_REGRESSION.json')['status']=='PASS_INTEGRATED_DIRECTED_RTL_REGRESSION'
image=NEW/'image';image.mkdir(exist_ok=False)
bit=BUILD/'COMM_steps01_04_150_lab_candidate.bit';dcp=BUILD/'physical_routed.dcp'
assert bit.stat().st_size>9000000 and dcp.stat().st_size>1000000
shutil.copy2(bit,image/bit.name);shutil.copy2(dcp,image/'COMM_steps01_04_150_routed.dcp')
bit_sha,dcp_sha=sha(bit),sha(dcp)
old=load(BASE/'image/BOARD_CHARACTERIZATION_MANIFEST.json')
assert bit_sha!=old['BIT']['sha256'] and dcp_sha!=old['source_routed_DCP_sha256']
c_source='C_INTEGRATED_STEPS01_04_RETRY_EDGE_20261009_a4bc4b7c3f0a8438'
# Rebind only derivative LAB image guards, retaining the UART, JTAG and false-permission checks.
guard=NEW/'scripts/board_characterization_identity.py';text=guard.read_text(encoding='utf-8')
assert text.count(old['source_routed_DCP_sha256'])==1 and text.count(old['C_source'])==1
text=text.replace(old['source_routed_DCP_sha256'],dcp_sha).replace(old['C_source'],c_source)
anchor="    review_path, review_data = file_item(path.parent, m.get('digital_review'))"
assert text.count(anchor)==1
text=text.replace(anchor,"    _, routed_data = file_item(path.parent, m.get('routed_DCP'))\n"
    "    if sha(routed_data) != SOURCE_DCP_SHA:\n        raise ValueError('Actual routed checkpoint differs')\n"
    "    source_base = path.parent.parent / 'rtl'\n"
    "    sources = m.get('COMM_source_manifest')\n"
    "    if not isinstance(sources, dict) or not sources:\n        raise ValueError('Source manifest required')\n"
    "    for name, digest in sources.items():\n        file_item(source_base, {'file': name, 'sha256': digest})\n"+anchor)
guard.write_text(text,encoding='utf-8')
lab=NEW/'lab/board_lab_functional.py';text=lab.read_text(encoding='utf-8')
assert text.count(old['source_routed_DCP_sha256'])==1
lab.write_text(text.replace(old['source_routed_DCP_sha256'],dcp_sha),encoding='utf-8')
for p in NEW.rglob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'))
sources={p.name:sha(p) for p in (NEW/'rtl').iterdir() if p.is_file()}
for name,digest in sources.items():assert sha(BUILD/name)==digest,name
internal=(BUILD/'internal_slack.txt').read_text()
assert all(float(line.split()[1])>=0 for line in internal.splitlines())
timing=(BUILD/'timing_route.rpt').read_text(errors='replace')
slackline=next(line for line in timing.splitlines() if re.fullmatch(r'\s*-?\d+\.\d+(?:\s+-?\d+(?:\.\d+)?){9,}\s*',line))
values=slackline.split();setup=float(values[0]);hold=float(values[4])
assert setup>=0 and hold>=0
digital=dict(status='PASS_DIGITAL_IMPLEMENTATION_ONLY_ELECTRICAL_UNVERIFIED',source_routed_DCP_sha256=dcp_sha,
    BIT_sha256=bit_sha,approved_for_characterization_only=True,physical_IO_signoff=False,formal_video_permission=False,
    board_tested=False,model_changed=False,numeric_integration_changed=False,source_manifest=sources,
    native_digital_audit=dict(native_setup_slack_ns=setup,native_hold_slack_ns=hold,core_hz=150000000,DRC_error_or_critical_count=0),
    current_build_script_sha256=sha(BUILD/'build_integrated.tcl'),build_log_sha256=sha(BUILD/'integrated_build.log'),
    integrated_directed_rtl_regression_sha256=sha(REVIEW/'RTL_REGRESSION.json'),
    integrated_host_regression_sha256=sha(REVIEW/'HOST_REGRESSION.json'),
    validation_scope='FRESH_SOURCE_SYNTHESIS_FULL_PLACE_ROUTE_NATIVE_TIMING_DRC_AND_INTEGRATED_REGRESSIONS',
    user_authorized_scope='User requested all four steps integrated and run on board; temporary RAM JTAG')
save(image/'DIGITAL_CHARACTERIZATION_REVIEW.json',digital)
manifest=old.copy()
manifest.update(source_routed_DCP_sha256=dcp_sha,C_source=c_source,
    BIT=dict(file=bit.name,sha256=bit_sha,bytes=bit.stat().st_size),
    routed_DCP=dict(file='COMM_steps01_04_150_routed.dcp',sha256=dcp_sha),
    digital_review=dict(file='DIGITAL_CHARACTERIZATION_REVIEW.json',sha256=sha(image/'DIGITAL_CHARACTERIZATION_REVIEW.json')),
    COMM_source_manifest=sources,tools_sha256={n:sha(NEW/'scripts'/n) for n in old['tools_sha256']},
    note='Four-step derivative freshly rebuilt for user-authorized board execution; formal and electrical flags remain false.')
save(image/'BOARD_CHARACTERIZATION_MANIFEST.json',manifest)
selection=load(BASE/'LAB_FUNCTIONAL_SELECTION.json')
selection.update(source_routed_DCP_sha256=dcp_sha,candidate_BIT_sha256=bit_sha,
    characterization_manifest=dict(file='image/BOARD_CHARACTERIZATION_MANIFEST.json',sha256=sha(image/'BOARD_CHARACTERIZATION_MANIFEST.json')),
    lab_tools_sha256={n:sha(NEW/'lab'/n) for n in selection['lab_tools_sha256']})
assert all(sha(NEW/'host'/n)==digest for n,digest in selection['formal_host_sha256'].items())
save(NEW/'LAB_FUNCTIONAL_SELECTION.json',selection)
stream=load(BASE/'STREAMING_SELECTION.json')
stream['files']['streaming/nonblocking_io.py']=''
stream.update(candidate_BIT_sha256=bit_sha,legacy_lab_selection_sha256=sha(NEW/'LAB_FUNCTIONAL_SELECTION.json'),
    files={n:sha(NEW/n) for n in stream['files']},candidate_status='FOUR_STEPS_INTEGRATED_NEW_BIT_DIGITAL_PASS_BOARD_PENDING',
    repair_revision='20261009_STEPS01_04_INTEGRATED',
    runtime_defaults=dict(io_mode='nonblocking',timing_mode='sampled',timing_sample_every=16,output_window=128))
save(NEW/'STREAMING_SELECTION.json',stream)
receipt=dict(status='FOUR_STEPS_INTEGRATED_NEW_BIT_DIGITAL_PASS_BOARD_PENDING',created_UTC=datetime.now(timezone.utc).isoformat(),
    package=str(NEW),source_routed_DCP_sha256=dcp_sha,candidate_BIT_sha256=bit_sha,source_manifest=sources,
    runtime_defaults=stream['runtime_defaults'],first_step_rtl_patch_in_bit=True,
    physical_IO_signoff=False,formal_video_permission=False,whole_system_4K30_achieved=False,
    origin_package_manifest_sha256=sha(BASE/'PACKAGE_MANIFEST.json'),
    file_sha256={str(p.relative_to(NEW)):sha(p) for folder in ('rtl','streaming','host','scripts','lab','diagnostics','image') for p in (NEW/folder).iterdir() if p.is_file()})
for name in ('run_integrated.ps1','README.md'):
    receipt['file_sha256'][name]=sha(NEW/name)
save(NEW/'PACKAGE_MANIFEST.json',receipt);save(REVIEW/'CANDIDATE.json',receipt)
print(json.dumps({k:v for k,v in receipt.items() if k not in ('source_manifest','file_sha256')},indent=2))
