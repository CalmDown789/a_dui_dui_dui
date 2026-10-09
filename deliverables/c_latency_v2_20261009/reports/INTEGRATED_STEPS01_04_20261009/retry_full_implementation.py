from pathlib import Path
import hashlib,json,shutil,sys
sys.dont_write_bytecode=True
REVIEW=Path(__file__).resolve().parent;NEW=Path(r'C:\t6int09\main')
old=NEW/'implementation';build=NEW/'implementation_full';build.mkdir(exist_ok=False)
for p in (NEW/'rtl').iterdir():
    if p.is_file():shutil.copy2(p,build/p.name)
shutil.copy2(old/'physical_synth.dcp',build/'physical_synth.dcp')
text=(old/'build_integrated.tcl').read_text(encoding='utf-8')
assert text.count('\nopt_design\n')==1
tail=text.split('\nopt_design\n',1)[1]
tail=tail.replace('read_checkpoint -incremental -directive TimingClosure incremental_reference.dcp\n','')
tail=tail.replace('report_incremental_reuse -file incremental_reuse_before_place.rpt\n','')
tail=tail.replace('report_incremental_reuse -file incremental_reuse_final.rpt\n','')
prefix='set_param general.maxThreads 8\nopen_checkpoint physical_synth.dcp\n'
prefix+='set tx_serial_clock [get_clocks -of_objects [get_pins u_io/u_tx/u_forward/C]]\n'
prefix+='source physical_reset_endpoints.tcl\nsource managed_reset_fault_endpoints.tcl\nopt_design\n'
(build/'build_integrated.tcl').write_text(prefix+tail,encoding='utf-8')
receipt=json.loads((REVIEW/'ASSEMBLY.json').read_text(encoding='utf-8'))
shutil.copy2(REVIEW/'ASSEMBLY.json',REVIEW/'ASSEMBLY_FIRST_INCREMENTAL.json')
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
receipt.update(status='FULL_IMPLEMENTATION_AFTER_INCREMENTAL_PLACER_FAILURE',build=str(build),
    build_script_sha256=sha(build/'build_integrated.tcl'),synth_checkpoint_sha256=sha(build/'physical_synth.dcp'),
    first_incremental_failure_log=str(old/'integrated_build.log'),
    first_incremental_failure_log_sha256=sha(old/'integrated_build.log'))
(REVIEW/'ASSEMBLY.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items()if k!='source_sha256'},indent=2))
