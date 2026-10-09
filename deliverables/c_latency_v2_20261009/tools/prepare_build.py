"""Prepare a fresh source build directory; never runs Vivado or programs hardware."""
from pathlib import Path
import argparse, hashlib, json, shutil

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out-dir', type=Path, required=True)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root/'runtime/main/rtl'
    a.out_dir.mkdir(parents=True, exist_ok=False)
    for p in source.iterdir():
        if p.is_file(): shutil.copy2(p,a.out_dir/p.name)
    original = (root/'build_history/implementation/build_integrated.tcl').read_text(encoding='utf-8')
    marker = 'write_checkpoint physical_synth.dcp\n'
    if original.count(marker) != 1: raise ValueError('Unexpected synthesis boundary')
    prefix = original.split(marker)[0]+marker
    # Original command reads three EVF2 sources before cd; make preparation independent of launch cwd.
    early = 'read_verilog -sv [list evf2_result_window.sv evf2_control_parser.sv evf2_response_serializer.sv]\n'
    if prefix.count(early) != 1: raise ValueError('Unexpected EVF2 sources')
    prefix = prefix.replace(early,'').replace('cd $out\n','cd $out\n'+early,1)
    (a.out_dir/'synthesis.tcl').write_text(prefix+'exit\n',encoding='utf-8')
    full = (root/'build_history/implementation_full/build_integrated.tcl').read_text(encoding='utf-8')
    if 'open_checkpoint physical_synth.dcp' not in full or 'read_checkpoint -incremental' in full:
        raise ValueError('Expected actual full implementation script')
    header = 'set out [file normalize [file dirname [info script]]]\ncd $out\n'
    (a.out_dir/'full_implementation.tcl').write_text(header+full,encoding='utf-8')
    shutil.copy2(root/'build_history/implementation_refine/build_integrated.tcl',a.out_dir/'refine_reference.tcl')
    rows = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.out_dir.iterdir() if p.is_file()}
    receipt = dict(scope='BUILD_PREPARATION_ONLY_NOT_IMPLEMENTATION_OR_BIT_ACCEPTANCE',
                   board_or_vivado_actions=False, source_files_sha256=rows,
                   refine_note='Historical refine opens input_routed.dcp; explicitly stage failed routed checkpoint in a fresh directory before using it. No automatic retry or guarantee.')
    (a.out_dir/'BUILD_PREPARATION.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='PREPARED_NEW_SOURCE_BUILD_DIRECTORY',files=len(rows),directory=str(a.out_dir))))

if __name__ == '__main__': main()
