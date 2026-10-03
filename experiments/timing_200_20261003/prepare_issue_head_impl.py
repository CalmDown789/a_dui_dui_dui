"""Prepare a fresh-placement real B+C direct FIFO-head timing candidate.

Retain the three-edge ROM, cached pad boundaries and credit-memory write.
Only the eight-phase sequencer changes from the active ROM3 candidate.
Remove the physical incremental reference; preserve the 5 ns final clock,
original jitter/XDC and temporary 0.300 ns setup search pressure.
"""
from pathlib import Path
import hashlib, json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def replace_once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)

def create(path, text):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)

runner = (HERE / 'synth_rom_pipeline_inc.tcl').read_text(encoding='utf-8')
runner = replace_once(runner,
    '# Three-edge C ROM pipeline, exact real B, incremental physical reference.',
    '# Direct FIFO-head sequencer + ROM3, fresh placement, exact real B+C.')
runner = runner.replace('rom_pipeline_inc_20261003_setup030', 'issue_head_fresh_20261003_setup030')
runner = replace_once(runner, 'append variant "_try2"', 'append variant "_try1"')
runner = runner.replace('experiments/timing_200_20261003/synth_rom_pipeline_inc.tcl',
                        'experiments/timing_200_20261003/synth_issue_head_fresh.tcl')
runner = runner.replace('exec git -C $root_dir', 'exec git -c "safe.directory=$root_dir" -C $root_dir')
runner = replace_once(runner, '"$b_real_dir/stream/eight_phase_issue.sv"',
                               '"$candidate_dir/issue_head/eight_phase_issue.sv"')
start = runner.index('# Non-RTL inputs are frozen too;')
end = runner.index('close $mf', start)
runner = runner[:start] + runner[end:]
start = runner.index('    if {$ok && [catch {\n        read_checkpoint -incremental')
end = runner.index('    if {$ok && [catch {phys_opt_design', start)
runner = runner[:start] + '''    if {$ok && [catch {place_design -directive ExtraNetDelay_high} e]} {set ok 0; puts "place_design FAILED: $e"}
''' + runner[end:]
runner = runner.replace('route_design -directive Explore', 'route_design -directive NoTimingRelaxation')
runner = replace_once(runner,
    '        report_incremental_reuse -file "$out_dir/incremental_reuse_final.rpt"\n', '')
runner = runner.replace('Incremental final routing incomplete/invalid', 'Fresh final routing incomplete/invalid')
anchor = '# Confirm that the intended complete-product boundary survives synthesis.'
runner = replace_once(runner, anchor, '''# The direct-head issue must not contain a wide copied-window register.
set copy_regs [get_cells -quiet -hier -filter {NAME =~ */mac/issue/out_window_reg*}]
set rf [open "$out_dir/issue_head_register_audit.txt" w]
puts $rf "copied_window_register_cells=[llength $copy_regs]"
foreach cell $copy_regs {puts $rf [list [get_property NAME $cell] [get_property REF_NAME $cell]]}
close $rf
if {[llength $copy_regs]!=0} {error "Unexpected issue copied-window registers"}

''' + anchor)
create(HERE / 'synth_issue_head_fresh.tcl', runner)

collector = (HERE / 'collect_rom_pipeline_impl.py').read_text(encoding='utf-8')
collector = replace_once(collector,
    "pipeline_runners['synth_rom_pipeline_inc.tcl'] = ('V1-pad-flags-credit-memory-ROM3-incremental', None)",
    "pipeline_runners['synth_issue_head_fresh.tcl'] = ('V1-pad-flags-credit-memory-ROM3-direct-head-fresh', None)")
start = collector.index("summary['incremental_reuse'] = {}")
end = collector.index('\npaths = [repo_path', start)
collector = collector[:start] + '''audit = read('issue_head_register_audit.txt').strip()
assert audit == 'copied_window_register_cells=0', 'Wide copied-window registers survived'
summary['copied_window_register_cells'] = 0
summary['physical_strategy'] = 'Fresh ExtraNetDelay_high placement; NoTimingRelaxation route; AggressiveExplore pre/post-route physical optimization.'
''' + collector[end:]
create(HERE / 'collect_issue_head_impl.py', collector)

records = []
for path in (HERE / 'synth_issue_head_fresh.tcl', HERE / 'collect_issue_head_impl.py',
             HERE / 'issue_head/eight_phase_issue.sv', Path(__file__).resolve()):
    data = path.read_bytes()
    records.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest()))
create(HERE / 'issue_head/implementation_prepared_manifest.json',
       json.dumps(records, indent=2)+'\n')
print('ISSUE_HEAD_FRESH_IMPL_PREPARED_NOT_RUN')
