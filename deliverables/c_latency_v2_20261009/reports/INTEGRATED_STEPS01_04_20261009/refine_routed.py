from pathlib import Path
import hashlib,json,shutil,sys
sys.dont_write_bytecode=True
REVIEW=Path(__file__).resolve().parent;NEW=Path(r'C:\t6int09\main')
old=NEW/'implementation_full';build=NEW/'implementation_refine';build.mkdir(exist_ok=False)
for p in (NEW/'rtl').iterdir():
    if p.is_file():shutil.copy2(p,build/p.name)
shutil.copy2(old/'physical_routed.dcp',build/'input_routed.dcp')
text=(old/'build_integrated.tcl').read_text(encoding='utf-8')
anchor='set before_refine [get_timing_paths'
assert text.count(anchor)==1
tail=anchor+text.split(anchor,1)[1]
tail=tail.replace(' route_design\n',' route_design -directive MoreGlobalIterations\n')
prefix='set_param general.maxThreads 8\nopen_checkpoint input_routed.dcp\n'
prefix+='set tx_serial_clock [get_clocks -of_objects [get_pins u_io/u_tx/u_forward/C]]\n'
prefix+='source physical_reset_endpoints.tcl\nsource managed_reset_fault_endpoints.tcl\n'
prefix+='phys_opt_design -directive AggressiveExplore\nroute_design -directive MoreGlobalIterations\n'
(build/'build_integrated.tcl').write_text(prefix+tail,encoding='utf-8')
receipt=json.loads((REVIEW/'ASSEMBLY.json').read_text(encoding='utf-8'))
shutil.copy2(REVIEW/'ASSEMBLY.json',REVIEW/'ASSEMBLY_FULL_IMPLEMENTATION.json')
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
receipt.update(status='POST_ROUTE_REFINEMENT_ONE_77PS_SETUP_PATH',build=str(build),
    build_script_sha256=sha(build/'build_integrated.tcl'),routed_input_checkpoint_sha256=sha(build/'input_routed.dcp'),
    first_full_failure_log=str(old/'integrated_build.log'),first_full_failure_log_sha256=sha(old/'integrated_build.log'))
(REVIEW/'ASSEMBLY.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items()if k!='source_sha256'},indent=2))
