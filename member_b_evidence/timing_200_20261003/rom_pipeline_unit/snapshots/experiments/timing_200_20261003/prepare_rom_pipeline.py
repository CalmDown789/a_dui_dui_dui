"""Prepare/freeze an isolated C ROM latency-three candidate; never launch tools.

The bank-local output register separates BRAM clock-to-Q from the global
bank mux. A bank-local request register cuts the enable path as well.
A four-entry response queue reserves capacity for all three in-flight
requests, so arbitrary downstream stalls cannot overwrite a response.
"""
from pathlib import Path
import hashlib
import json
import argparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEST = HERE / 'rom_pipeline'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--freeze', action='store_true')
args = parser.parse_args()
if not args.freeze:
    DEST.mkdir(exist_ok=False)
original = ROOT / 'experiments/l5_splitmem_20260924/rtl/c/input_rom.v'
text = original.read_text(encoding='utf-8')
old = '''    always @(posedge clk) begin
        if (en)
            dout <= mem[addr];
    end'''
new = '''    // Three-edge read: bank-local address/enable, BRAM read, BRAM DO_REG.
    // The bank-specific enable follows the first read, including at bank
    // boundaries and after an idle request cycle.
    reg [DATA_W-1:0] read_data_q;
    reg read_en_q, request_en_q;
    reg [ADDR_W-1:0] request_addr_q;
    always @(posedge clk) begin
        request_en_q <= en;
        request_addr_q <= addr;
        read_en_q <= request_en_q;
        if (request_en_q) read_data_q <= mem[request_addr_q];
        if (read_en_q) dout <= read_data_q;
    end'''
assert text.count(old) == 1
text = text.replace(old, new)
text = text.replace('    reg [BANK_SEL_W-1:0] bank_sel_q;',
                    '    reg [BANK_SEL_W-1:0] bank_sel_q, bank_sel_p1, bank_sel_p2;\n    reg bank_en_p1, bank_en_p2;')
old = '''            always @(posedge clk) begin
                if (en)
                    bank_sel_q <= addr[ADDR_W-1:BANK_ADDR_W];
            end'''
new = '''            always @(posedge clk) begin
                bank_en_p1 <= en;
                bank_en_p2 <= bank_en_p1;
                if (en) bank_sel_p1 <= addr[ADDR_W-1:BANK_ADDR_W];
                if (bank_en_p1) bank_sel_p2 <= bank_sel_p1;
                if (bank_en_p2) bank_sel_q <= bank_sel_p2;
            end'''
assert text.count(old) == 1
text = text.replace(old, new)
expected = '// Experimental latency-three ROM; pair only with the matching stream.\n' + text.rstrip('\n') + '\n'
if args.freeze:
    assert (DEST / 'input_rom.v').read_text(encoding='utf-8') == expected, 'ROM differs from reviewed transform'
else:
    (DEST / 'input_rom.v').write_text(expected, encoding='utf-8', newline='\n')
files = [original, ROOT / 'experiments/l5_splitmem_20260924/rtl/c/input_stream.v',
         Path(__file__), DEST / 'input_rom.v']
if args.freeze:
    files += [DEST / name for name in ('input_stream.v', 'tb_rom_pipeline.sv', 'run_unit.tcl')]
manifest = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size,
                 sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
target = DEST / ('frozen_manifest.json' if args.freeze else 'prepared_manifest.json')
with target.open('x', encoding='utf-8') as stream:
    json.dump(dict(state='PREPARED_NOT_RUN' if args.freeze else 'DRAFT_NOT_RUN',
                  rom_latency_edges=3, inputs=manifest), stream, indent=2)
    stream.write('\n')
print('ROM_PIPELINE_PREPARED_NOT_RUN')
