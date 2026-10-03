"""Prepare one real B+C ROM-pipeline incremental 200 MHz implementation.

Use the exact best retained routed DCP as a physical reference only. The
new netlist is synthesized from the already-tested RTL. No fixing regions,
timing exceptions, reduced jitter, or lower final frequency are introduced.
"""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def replace_once(s,old,new):
    assert s.count(old)==1,(old,s.count(old))
    return s.replace(old,new)

def create(path,s):
    with path.open('x',encoding='utf-8',newline='\n') as stream: stream.write(s)

reference_stage='postroute200_v1_credit_route030_20261003_try2'
record=json.loads((ROOT/'member_b_evidence/timing_200_20261003/postroute_v1_credit_route030/result_manifest.json').read_text())
reference=ROOT/'_synth_bc'/reference_stage/'postroute.dcp'
data=reference.read_bytes()
assert record['postroute_hash']==dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
create(HERE/'rom_pipeline/reference_manifest.json',json.dumps(dict(
    source=reference.relative_to(ROOT).as_posix(),**record['postroute_hash'],
    reference_timing=record['global_timing']['after_restored'],
    role='Physical incremental reference only; candidate netlist comes from new RTL.'),indent=2)+'\n')

helper='''"""Verify and copy the exact incremental reference into a new candidate stage."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
manifest=json.loads((ROOT/'experiments/timing_200_20261003/rom_pipeline/reference_manifest.json').read_text())
source=ROOT/manifest['source']
def check(path):
    data=path.read_bytes()
    assert len(data)==manifest['bytes'] and hashlib.sha256(data).hexdigest()==manifest['sha256'],str(path)
check(source)
destination=Path(sys.argv[1]).resolve()
assert destination.parent.parent==ROOT/'_synth_bc',destination
assert not destination.exists(),'Refusing overwrite of reference snapshot'
shutil.copyfile(source,destination)
check(destination);check(source)
print('EXACT_INCREMENTAL_REFERENCE_COPIED_AND_VERIFIED')
'''
create(HERE/'verify_rom_reference.py',helper)
s=(HERE/'synth_pad_flags.tcl').read_text(encoding='utf-8')
s=s.replace('pad_flags_20261003_setup030','rom_pipeline_inc_20261003_setup030')
s=replace_once(s,'set input_rom_file "$experiment_dir/rtl/c/input_rom.v"',
                 'set input_rom_file "$candidate_dir/rom_pipeline/input_rom.v"')
s=replace_once(s,'set input_stream_file "$experiment_dir/rtl/c/input_stream.v"',
                 'set input_stream_file "$candidate_dir/rom_pipeline/input_stream.v"')
s=s.replace('experiments/timing_200_20261003/synth_pad_flags.tcl',
            'experiments/timing_200_20261003/synth_rom_pipeline_inc.tcl')
anchor='foreach f [concat $c_files $b_files [list "$xdc_dir/c_top.xdc"]] {puts $mf $f}'
s=replace_once(s,anchor,anchor+'''
# Non-RTL inputs are frozen too; the reference supplies placement/routing only.
set reference_copy "$stage/incremental_reference.dcp"
puts [exec "C:/Users/24889/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" -I "$candidate_dir/verify_rom_reference.py" $reference_copy]
foreach f [list $reference_copy "$candidate_dir/verify_rom_reference.py" "$candidate_dir/rom_pipeline/reference_manifest.json"] {puts $mf $f}''')
s=replace_once(s,'# Confirm that the intended complete-product boundary survives synthesis.', '''# Audit actual input-ROM register inference on every mapped physical BRAM.
set rf [open "$out_dir/input_rom_bram_registers.txt" w]
set rom_brams [get_cells -quiet -hier -filter {REF_NAME =~ RAMB* && NAME =~ */u_rom/*}]
puts $rf "input_rom_bram_count=[llength $rom_brams]"
if {[llength $rom_brams]==0} {error "Actual input ROM BRAMs missing"}
foreach b $rom_brams {
    set row [list [get_property NAME $b] [get_property REF_NAME $b]]
    foreach prop {DOA_REG DOB_REG READ_WIDTH_A READ_WIDTH_B} {lappend row "$prop=[get_property $prop $b]"}
    puts $rf $row
    if {[get_property READ_WIDTH_A $b]>0 && [get_property DOA_REG $b]!=1} {error "Active A port has no ROM DO_REG"}
    if {[get_property READ_WIDTH_B $b]>0 && [get_property DOB_REG $b]!=1} {error "Active B port has no ROM DO_REG"}
}
close $rf

# Confirm that the intended complete-product boundary survives synthesis.''')
old='''    if {$ok && [catch {place_design -directive ExtraNetDelay_high} e]} { set ok 0; puts "place_design FAILED: $e" }'''
new='''    if {$ok && [catch {
        read_checkpoint -incremental -directive TimingClosure $reference_copy
        report_incremental_reuse -file "$out_dir/incremental_reuse_before_place.rpt"
        place_design -directive Default
        report_incremental_reuse -file "$out_dir/incremental_reuse_after_place.rpt"
    } e]} {set ok 0; puts "incremental place_design FAILED: $e"}'''
s=replace_once(s,old,new)
s=replace_once(s,'route_design -directive NoTimingRelaxation','route_design -directive Explore')
anchor='''        report_timing_summary -file "$out_dir/timing_summary_route_${setup_tag}.rpt" -max_paths 20'''
s=replace_once(s,anchor,'''        report_timing_summary -file "$out_dir/timing_before_postphysopt_${setup_tag}.rpt" -max_paths 20
        phys_opt_design -directive AggressiveExplore
        if {![report_route_status -boolean_check ROUTED_FULLY]} {route_design -directive Explore -preserve}
        if {![report_route_status -boolean_check ROUTED_FULLY] || [report_route_status -boolean_check ERRORS_IN_ROUTES]} {error "Incremental final routing incomplete/invalid"}
        report_incremental_reuse -file "$out_dir/incremental_reuse_final.rpt"
'''+anchor)
s='# Three-edge C ROM pipeline, exact real B, incremental physical reference.\n'+s
s=replace_once(s,'if {$use_srl} {append variant "_srl"}',
                 'if {$use_srl} {append variant "_srl"}\nappend variant "_try2"')
create(HERE/'synth_rom_pipeline_inc.tcl',s)

collector=(HERE/'collect_pad_flags_impl.py').read_text(encoding='utf-8')
collector=replace_once(collector,"pipeline_runners['synth_pad_flags.tcl'] = ('V1-pad-flags-credit-memory', None)",
                       "pipeline_runners['synth_rom_pipeline_inc.tcl'] = ('V1-pad-flags-credit-memory-ROM3-incremental', None)")
create(HERE/'collect_rom_pipeline_impl.py',collector)
print('ROM_PIPELINE_INCREMENTAL_RUNNER_PREPARED_NOT_RUN')
