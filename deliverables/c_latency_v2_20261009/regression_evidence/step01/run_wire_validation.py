"""Full 1080p retained-window/serializer validation; preloaded Golden, no SR or NIC."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys,time,zlib,shutil
sys.dont_write_bytecode=True

HERE=Path(__file__).resolve().parent
ROOT=Path(r'C:\t6dup09\main')
V=Path(r'E:\AMDTools2025\2025.2\Vivado\bin')
sys.path.insert(0,str(ROOT/'host'))
from video_protocol import Packet,decode
SESSION=bytes(range(16));W=128
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def wire(p):
    raw=p.encode();head=b'EVF2\x02'+raw[5:60]
    return head+struct.pack('!I',zlib.crc32(head))+raw[64:]
def read(raw):
    assert raw[:5]==b'EVF2\x02' and zlib.crc32(raw[:60])==int.from_bytes(raw[60:64],'big')
    head=b'EVF1\x01'+raw[5:60]
    return decode(head+struct.pack('!I',zlib.crc32(head))+raw[64:])
def hexfile(p,data):p.write_text(''.join(f'{b:02x}\n' for b in data),encoding='ascii')

def main():
    run=HERE/'runs'/('full_wire_'+time.strftime('%Y%m%dT%H%M%S'));run.mkdir(parents=True)
    frozen=ROOT/'proof/window_counter_guard'
    manifest=json.loads((ROOT/'data/ETHERNET_SEQUENCE_MANIFEST.json').read_text())
    frames=[]
    for row in manifest['frames'][:2]:
        p=ROOT/'data'/row['golden_file'];assert sha(p)==row['golden_sha256'];frames.append(p.read_bytes())
    sources=[]
    for name in ['evf2_result_window.sv','evf2_control_parser.sv','evf2_response_serializer.sv','pingpong_buffer.v','stripe_buffer.v']:
        p=HERE/'rtl'/name if name=='evf2_result_window.sv' else ROOT/'rtl'/name
        shutil.copy2(p,run/name);sources.append({'source':str(p),'sha256':sha(p)})
    tb=(frozen/'tb_window.sv').read_text()
    tb=tb.replace('.RETRY_CYCLES(5000)', '.RETRY_CYCLES(3000000)')
    tb=tb.replace('||retries==0)', '||retries!=0)')
    tb=tb.replace('#100000000;', '#1000000000;')
    (run/'tb_window.sv').write_text(tb,encoding='ascii')
    requests=bytearray();actions=[]
    def send(p):
        raw=wire(p);actions.append(f'send_control({len(requests)},{len(raw)},0);');requests.extend(raw)
    size=len(frames[0]);total=(size+1023)//1024
    send(Packet(1,SESSION,frame_bytes=size,payload=struct.pack('!HHB3x',1024,W,0x17)))
    actions.append('wait(offers==1);repeat(3)@(negedge clk);')
    for f,data in enumerate(frames):
        actions.append(f'launch({f});')
        for at in range(0,total,W):
            end=min(at+W,total);actions.append(f'wait_coverage({end});')
            body=b''.join(struct.pack('!II',q,zlib.crc32(data[q*1024:(q+1)*1024])) for q in range(at,end))
            send(Packet(0x97,SESSION,f,frame_bytes=size,payload=body,status=1,next_offset=end*1024))
            actions.append(f'wait_control_idle();wait_base({end});')
        actions.append('@(negedge clk);core_done=1;@(negedge clk);core_done=0;')
        final=Packet(9,SESSION,f,total,size,size,zlib.crc32(data))
        send(final);actions.append(f'wait(releases=={f+1});@(negedge clk);')
        send(final);actions.append(f'wait(final_replies=={(f+1)*2});')
    hexfile(run/'window_golden.hex',b''.join(frames));hexfile(run/'window_requests.hex',requests)
    (run/'window_config.vh').write_text(f'localparam BYTES={size},PACKETS={total},W={W};\n',encoding='ascii')
    (run/'window_actions.vh').write_text('\n'.join(actions),encoding='ascii')
    (run/'run.tcl').write_text('run all\nquit\n',encoding='ascii')
    receipt=dict(status='RUNNING',scope='FULL_1080P_PRELOADED_GOLDEN_WINDOW_PARSER_SERIALIZER_NOT_SR_OR_BOARD',
                 sources=sources,run_directory=str(run),commands=[],board_tested=False,BIT_generated=False)
    def save():(HERE/'WIRE_REGRESSION.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    save()
    commands=[[str(V/'xvlog.bat'),'-sv']+[Path(row['source']).name for row in sources]+['tb_window.sv'],
              [str(V/'xelab.bat'),'--debug','off','--mt','off','tb_window','-s','snapshot'],
              [str(V/'xsim.bat'),'snapshot','--tclbatch','run.tcl']]
    try:
        for i,command in enumerate(commands):
            started=time.perf_counter()
            with (run/f'{i+1}.log').open('wb') as log:
                p=subprocess.run(command,cwd=run,stdout=log,stderr=subprocess.STDOUT,timeout=300)
            receipt['commands'].append(dict(argv=command,exit_code=p.returncode,seconds=time.perf_counter()-started));save()
            text=(run/f'{i+1}.log').read_text(encoding='utf-8',errors='replace')
            assert p.returncode==0 and 'ERROR:' not in text and 'Fatal:' not in text,text[-2500:]
            print(f'STEP={i+1} PASS',flush=True)
        assert 'EVF2_WINDOW_PASS' in text,text[-2000:]
        coverage=[set(),set()];duplicates=0;statuses=[];output_packets=0
        for line in (run/'wire_packets.txt').read_text().splitlines():
            p=read(bytes.fromhex(line));assert p.session==SESSION and p.frame_bytes==size and p.reserved==0
            if p.type==0x17:
                assert p.frame_id in (0,1);q=p.sequence;at=q*1024;data=frames[p.frame_id]
                assert 0<=q<total and p.status==1 and p.offset==at and p.next_offset==0
                assert p.payload==data[at:at+1024] and p.flags==int(q==total-1)
                assert p.frame_crc==(zlib.crc32(data) if q==total-1 else 0)
                duplicates+=q in coverage[p.frame_id];coverage[p.frame_id].add(q);output_packets+=1
            elif p.type==0x81:assert p.status==0 and p.payload==struct.pack('!HHB3x',1024,W,0x17)
            elif p.type==0x89:assert not p.payload;statuses.append(p.status)
            else:raise AssertionError(p.type)
        assert coverage==[set(range(total)),set(range(total))] and duplicates==0 and statuses==[4,4,4,4]
        assert all(sha(Path(row['source']))==row['sha256'] for row in sources)
        receipt.update(status='PASS',frames=2,unique_packets=output_packets,duplicate_packets=duplicates,
                       golden_bytes=sum(map(len,frames)),golden_mismatches=0,final_statuses=statuses,
                       wire_sha256=sha(run/'wire_packets.txt'),sources_unchanged=True)
    except BaseException as exc:receipt.update(status='FAIL',error=repr(exc));save();raise
    finally:save()
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('sources','commands')},indent=2),flush=True)

if __name__=='__main__':main()
