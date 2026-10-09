"""Reconstruct input/result from raw EVF1 UDP evidence and compare to Golden.

Raw protocol PASS is independent of board programming, physical timing, core
counter observation and operator playback confirmation; those remain separate.
"""
from datetime import datetime,timezone
from pathlib import Path
import argparse,hashlib,json,struct,zlib
from video_protocol import decode,InvalidPacket,Type,Status
from video_sequence_identity import verify_sequence


def sha(data):return hashlib.sha256(data).hexdigest()


def audit_packets(run,inputs,goldens):
    run=Path(run).resolve();summary=json.loads((run/'SUMMARY.json').read_text(encoding='utf-8'))
    if not summary.get('success'):raise ValueError('run is incomplete or failed; no continuous-video PASS')
    if len(inputs)!=len(goldens) or not inputs:raise ValueError('input/Golden frame count mismatch')
    n,m=summary['input_bytes'],summary['output_bytes']
    if any(len(x)!=n for x in inputs) or any(len(x)!=m for x in goldens):raise ValueError('input/Golden geometry mismatch')
    input_crcs=[zlib.crc32(x) for x in inputs];output_crcs=[zlib.crc32(x) for x in goldens]
    events=[json.loads(line) for line in (run/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    session=bytes.fromhex(summary['session']);peer=summary['peer']
    fid=0;phase='HELLO';ipos=opos=0;input_data=bytearray();output_data=bytearray();pending=None
    request=None;candidate=None;request_files=set();response_files=set();sends=received=ignores=0;frames=[]
    first_send=None;last_receive=None
    def fail(reason):raise ValueError(reason)
    def read(event,prefix):
        name=event.get('file')
        if not isinstance(name,str) or Path(name).name!=name or not name.startswith(prefix):fail('unsafe raw file path')
        path=(run/name).resolve()
        if not path.is_relative_to(run):fail('raw file escapes run')
        raw=path.read_bytes()
        if len(raw)!=event['bytes'] or sha(raw)!=event['sha256']:fail('raw datagram size/hash differs: '+name)
        return raw
    for event in events:
        kind=event['event']
        if kind=='SEND':
            raw=read(event,'request_');request_files.add(event['file']);sends+=1;request=decode(raw);candidate=None
            if request.session!=session or request.flags or request.reserved or request.status or request.next_offset:fail('invalid request session/flags')
            if request.type==Type.BEGIN and first_send is None:first_send=event['utc']
        elif kind=='RECEIVE':
            raw=read(event,'response_');response_files.add(event['file']);received+=1
            if request is None:fail('reply before request')
            if event['source']!=peer:ignores+=1;continue
            try:r=decode(raw)
            except InvalidPacket:ignores+=1;continue
            if (r.type,r.session,r.frame_id,r.sequence,r.offset,r.frame_bytes,r.reserved)!=(
                int(request.type)|0x80,request.session,request.frame_id,request.sequence,request.offset,request.frame_bytes,0):
                ignores+=1;continue
            if request.type!=Type.READ_RESULT or r.status!=Status.ACK:
                if r.payload or r.flags or r.frame_crc!=request.frame_crc:ignores+=1;continue
            elif r.flags not in (0,1):ignores+=1;continue
            candidate=r;last_receive=event['utc']
        elif kind=='ACK':
            if candidate is None or request is None:fail('ACK has no trusted raw datagram')
            p,r=request,candidate
            if (event['type'],event['frame'],event['sequence'],event['status'],event['next_offset'])!=(p.type,p.frame_id,p.sequence,r.status,r.next_offset):
                fail('ACK event differs from raw reply')
            if r.status==Status.NOT_READY:
                valid_wait=(p.type==Type.READ_RESULT and phase=='OUTPUT' and p.offset==opos and p.sequence==opos//1024 and not p.frame_crc)
                valid_wait=valid_wait or (p.type==Type.ACK_FRAME and phase=='FINAL' and p.offset==m and p.sequence==(m+1023)//1024 and p.frame_crc==output_crcs[fid])
                if not valid_wait or p.frame_id!=fid or p.frame_bytes!=m or p.payload or r.next_offset!=opos:
                    fail('NOT_READY context/progress invalid')
                candidate=None;continue
            if p.type==Type.HELLO:
                if phase!='HELLO' or p.frame_id or p.sequence or p.offset or p.frame_crc or p.payload or p.frame_bytes!=n or r.status!=Status.OK or r.next_offset:
                    fail('HELLO context invalid')
                phase='BEGIN'
            elif p.type==Type.BEGIN:
                if phase!='BEGIN' or fid>=len(inputs) or p.frame_id!=fid or p.sequence or p.offset or p.payload or p.frame_bytes!=n:
                    fail('BEGIN order/identity invalid')
                if p.frame_crc!=input_crcs[fid] or r.status!=Status.ACK or r.next_offset:fail('BEGIN CRC/progress invalid')
                phase='INPUT'
            elif p.type==Type.DATA:
                length=min(1024,n-ipos)
                if phase!='INPUT' or p.frame_id!=fid or p.offset!=ipos or p.sequence!=(ipos//1024) or p.frame_bytes!=n or len(p.payload)!=length or not length:
                    fail('DATA order/length invalid')
                if p.frame_crc!=input_crcs[fid] or p.payload!=inputs[fid][ipos:ipos+length] or r.status!=Status.ACK or r.next_offset!=ipos+length:
                    fail('DATA input/CRC/progress mismatch')
                input_data.extend(p.payload);ipos+=length
            elif p.type==Type.COMMIT:
                if phase!='INPUT' or p.frame_id!=fid or ipos!=n or p.offset!=n or p.sequence!=(n+1023)//1024 or p.payload or p.frame_bytes!=n:
                    fail('COMMIT before full input')
                if bytes(input_data)!=inputs[fid] or p.frame_crc!=zlib.crc32(input_data) or r.status!=Status.STARTED or r.next_offset!=n:
                    fail('COMMIT input/CRC/response mismatch')
                phase='OUTPUT'
            elif p.type==Type.READ_RESULT:
                length=min(1024,m-opos);last=opos+length==m
                if phase!='OUTPUT' or p.frame_id!=fid or p.offset!=opos or p.sequence!=opos//1024 or p.payload or p.frame_crc or p.frame_bytes!=m:
                    fail('READ_RESULT order/identity invalid')
                if r.status!=Status.ACK or len(r.payload)!=length or r.next_offset!=opos or r.flags!=int(last):fail('READ_RESULT length/LAST/progress mismatch')
                if r.payload!=goldens[fid][opos:opos+length] or r.frame_crc!=(output_crcs[fid] if last else 0):
                    fail('raw result differs from independent Golden or final CRC')
                if pending is not None and pending!=r.payload:fail('retained result bytes changed')
                pending=r.payload
            elif p.type==Type.ACK_RESULT:
                if phase!='OUTPUT' or pending is None or p.frame_id!=fid or p.offset!=opos or p.sequence!=opos//1024 or p.frame_bytes!=m or p.frame_crc:
                    fail('ACK_RESULT before current result')
                if p.payload!=struct.pack('!I',zlib.crc32(pending)) or r.status!=Status.ACK or r.next_offset!=opos+len(pending):
                    fail('ACK_RESULT CRC/progress invalid')
                output_data.extend(pending);opos+=len(pending);pending=None
                if opos==m:phase='FINAL'
            elif p.type==Type.ACK_FRAME:
                if phase!='FINAL' or p.frame_id!=fid or p.offset!=m or p.sequence!=(m+1023)//1024 or p.frame_bytes!=m or p.payload:
                    fail('ACK_FRAME before all result acknowledgements')
                if bytes(output_data)!=goldens[fid] or p.frame_crc!=zlib.crc32(output_data) or r.status!=Status.FRAME_DONE or r.next_offset!=m:
                    fail('final frame CRC/progress mismatch')
                if (run/f'frame_{fid:04d}_input.bin').read_bytes()!=input_data or (run/f'frame_{fid:04d}_result.bin').read_bytes()!=output_data:
                    fail('saved input/result differs from raw datagrams')
                frames.append({'frame_id':fid,'input_bytes':n,'result_bytes':m,'input_sha256':sha(input_data),
                               'result_sha256':sha(output_data),'Golden_mismatch_bytes':0,'frame_ack_observed':True,
                               'first_BEGIN_SEND_UTC':first_send,'FRAME_DONE_RECEIVE_UTC':last_receive,
                               'UTC_event_span_seconds':(datetime.fromisoformat(last_receive)-datetime.fromisoformat(first_send)).total_seconds()})
                fid+=1;ipos=opos=0;input_data=bytearray();output_data=bytearray();phase='BEGIN';first_send=None
            else:fail('unexpected accepted request type')
            candidate=None
    if fid!=len(inputs) or phase!='BEGIN':fail('not all supplied frames completed in order')
    if len(request_files)!=summary['unique_requests'] or received!=summary['received'] or sends-len(request_files)!=summary['retries'] or ignores!=summary['ignored']:
        fail('raw events/counts disagree with summary')
    if set(p.name for p in run.glob('request_*.bin'))!=request_files or set(p.name for p in run.glob('response_*.bin'))!=response_files:
        fail('unreferenced datagrams present')
    declared=summary['frames']
    if len(declared)!=len(frames):fail('summary frame count differs')
    for index,f in enumerate(declared):
        if f['frame_id']!=index or f['input']['sha256']!=frames[index]['input_sha256'] or f['result']['sha256']!=frames[index]['result_sha256']:
            fail('summary frame identity differs from raw data')
        timing=f['host_timing_ns'];parts=[v for k,v in timing.items() if k!='whole_frame']
        if any(type(x) is not int or x<0 for x in parts) or sum(parts)!=timing['whole_frame']:fail('host timing fields do not sum')
    return {'status':'PASS_RAW_VIDEO_PACKETS_AGAINST_GOLDEN','checked_at_UTC':datetime.now(timezone.utc).isoformat(),
            'scope':'RAW_UDP_INPUT_OUTPUT_GOLDEN_FRAME_ACK_AUDIT_NOT_PHYSICAL_IMAGE_TIMING_COUNTERS_OR_VIEWING',
            'run_label':summary['label'],'frames':frames,'network_sends':sends,'raw_replies':received,'ignored':ignores,
            'events_sha256':sha((run/'events.jsonl').read_bytes()),'summary_sha256':sha((run/'SUMMARY.json').read_bytes()),
            'physical_core_start_done_observed':None,'hardware_configuration_verified':False,'operator_viewing_confirmed':False,
            'complete_stage_acceptance':False,
            'timing_scope':'UTC_EVENT_SPANS_CHECKED_HOST_MONOTONIC_PARTS_SUM_CHECKED_NOT_ISOLATED_CORE_OR_REALTIME_FPS'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--source-manifest',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    a.out_dir.mkdir(parents=True,exist_ok=False)
    try:
        prepared,identity=verify_sequence(a.source_manifest)
        if (a.run/'SOURCE_MANIFEST.json').read_bytes()!=a.source_manifest.read_bytes():raise ValueError('run/source manifest identity differs')
        result=audit_packets(a.run,[x for x,_ in prepared],[y for _,y in prepared]);result['source_identity']=identity
    except Exception as exc:result={'status':'FAIL','error':repr(exc),'scope':'RAW_VIDEO_EVIDENCE_AUDIT_NOT_BOARD'}
    result['auditor_sha256']=sha(Path(__file__).read_bytes())
    (a.out_dir/'INDEPENDENT_ETHERNET_VIDEO.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'out':str(a.out_dir),'error':result.get('error')}))
    return 0 if result['status'].startswith('PASS') else 1


if __name__=='__main__':raise SystemExit(main())
