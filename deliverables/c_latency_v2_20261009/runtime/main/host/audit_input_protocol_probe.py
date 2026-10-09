"""Re-decode saved probe datagrams without trusting PASS in the run report.

This checks raw protocol evidence and request bounds. It cannot observe the
physical core_start wire, hardware image identity, or SR output.
"""
from datetime import datetime,timezone
from pathlib import Path
import argparse,hashlib,json,struct,zlib
from video_protocol import decode,InvalidPacket,FrameReceiver,Type,INPUT_BYTES,State

FULL_CASES=[
    'HELLO','STATUS_IDLE','OLD_SESSION_REJECTED','FUTURE_FRAME_REJECTED','BEGIN',
    'OTHER_SESSION_CANNOT_TAKE_OVER','BAD_PAYLOAD_CRC_REJECTED','FUTURE_CHUNK_REJECTED',
    'BAD_FLAGS_REJECTED','SHORT_CHUNK_REJECTED','WRONG_FRAME_CRC_REJECTED','DATA0',
    'LOST_ACK_RETRY_SAME_PROGRESS','CHANGED_DUPLICATE_REJECTED','DUPLICATE_BEGIN_RETAINS_PROGRESS',
    'INCOMPLETE_COMMIT_REJECTED','BAD_HEADER_DISCARDED','STATUS_STILL_RECEIVING',
    'MISSING_CHUNK_RETRY','TOO_OLD_DUPLICATE_REJECTED','ABORT_HALF_FRAME',
    'STATUS_RECOVERED_IDLE','FRESH_SESSION_AFTER_ABORT','OLD_SESSION_AFTER_RESTART_REJECTED']


def audit(run,smoke=False):
    run=Path(run).resolve()
    report=json.loads((run/'REPORT.json').read_text(encoding='utf-8'))
    events=[json.loads(line) for line in (run/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    expected_cases=FULL_CASES[:2] if smoke else FULL_CASES
    rx=FrameReceiver();active=None;wanted=None;accepted=False;cases=[];data_for_request=None
    sends=received=ignored=0;request_files=set();reply_files=set();file_identity={}
    def raw(event,prefix):
        name=event.get('file')
        if not isinstance(name,str) or not name.startswith(prefix) or Path(name).name!=name:
            raise ValueError('unsafe or wrong datagram file name')
        path=(run/name).resolve()
        if not path.is_relative_to(run):raise ValueError('datagram path escapes run')
        data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        if len(data)!=event['bytes'] or digest!=event['sha256']:raise ValueError('raw datagram hash/size mismatch: '+name)
        if name in file_identity and file_identity[name]!=digest:raise ValueError('raw file identity changed')
        file_identity[name]=digest
        return data
    for event in events:
        if event['event']=='SEND':
            data=raw(event,'request_');request_files.add(event['file']);sends+=1
            active=event['case'];wanted=rx.process(data);accepted=False
            if rx.start_count or rx.state==State.RUNNING:raise ValueError('probe could start a complete frame')
        elif event['event']=='RECEIVE':
            data=raw(event,'reply_');reply_files.add(event['file']);received+=1
            if active!=event['case']:raise ValueError('receive case differs from active request')
            if event['source']!=report['peer']:ignored+=1;continue
            try:p=decode(data)
            except InvalidPacket:ignored+=1;continue
            if wanted is None:
                # Bad header carries no trusted request identity. Any matching
                # response to these exact mutated header fields is disallowed.
                if active=='BAD_HEADER_DISCARDED':
                    last_request=data_for_request
                    h=last_request[:60]+b'\0'*4
                    h=h[:60]+struct.pack('!I',zlib.crc32(h[:60]))+last_request[64:]
                    q=decode(h)
                    if p.type==(q.type|0x80) and p.session==q.session and p.frame_id==q.frame_id and p.sequence==q.sequence:
                        raise ValueError('corrupt header got a trusted response')
                ignored+=1;continue
            q=decode(wanted)
            envelope=(p.type,p.session,p.frame_id,p.sequence,p.offset,p.frame_bytes,p.frame_crc,p.flags,p.reserved,p.payload)
            reference=(q.type,q.session,q.frame_id,q.sequence,q.offset,q.frame_bytes,q.frame_crc,q.flags,q.reserved,q.payload)
            if envelope!=reference:ignored+=1;continue
            if data!=wanted:raise ValueError('trusted response status/progress differs from independent model')
            accepted=True
        elif event['event']=='CASE_PASS':
            if active!=event['case']:raise ValueError('case PASS differs from active request')
            if wanted is not None and not accepted:raise ValueError('case has no valid raw reply: '+active)
            if wanted is None and active!='BAD_HEADER_DISCARDED':raise ValueError('untrusted request outside corrupt-header case')
            if wanted is not None:
                p=decode(wanted)
                if event.get('reply_status')!=p.status or event.get('next_offset')!=p.next_offset:
                    raise ValueError('declared case PASS differs from raw reply')
            cases.append(active)
        if event['event']=='SEND':data_for_request=data
    if cases!=expected_cases:raise ValueError('required cases missing, reordered or duplicated')
    if len(request_files)!=len(expected_cases) or len(reply_files)!=received:raise ValueError('datagram counts disagree')
    if set(p.name for p in run.glob('request_*.bin'))!=request_files or set(p.name for p in run.glob('reply_*.bin'))!=reply_files:
        raise ValueError('unreferenced raw datagrams')
    if sends!=report['network_sends'] or received!=report['received'] or len(request_files)!=report['unique_requests']:
        raise ValueError('report counts disagree with raw events')
    if report['retries']!=sends-len(request_files) or report['ignored']!=ignored:raise ValueError('retry/ignore counts disagree')
    if [c['case'] for c in report['cases']]!=cases or not report['success']:raise ValueError('report cases/success disagree')
    if rx.start_count!=0 or rx.write_bytes!=(0 if smoke else 2048) or rx.offset!=0 or rx.state!=State.IDLE:
        raise ValueError('independent model final write/start/state differs')
    return {'status':'PASS_RAW_INPUT_PROTOCOL_EVIDENCE','checked_at_UTC':datetime.now(timezone.utc).isoformat(),
            'scope':'RAW_DATAGRAM_RESPONSE_AND_BOUNDED_REQUEST_AUDIT_NOT_HARDWARE_START_OR_IMAGE_OR_VIDEO',
            'run_label':report['scope'],'coverage':'SMOKE_ONLY' if smoke else 'FULL_24_CASE_INPUT_RECOVERY',
            'source_report_sha256':hashlib.sha256((run/'REPORT.json').read_bytes()).hexdigest(),
            'events_sha256':hashlib.sha256((run/'events.jsonl').read_bytes()).hexdigest(),
            'files_sha256':file_identity,'cases':cases,'network_sends':sends,'received':received,'ignored':ignored,
            'independent_model_written_bytes':rx.write_bytes,'independent_model_start_count':rx.start_count,
            'physical_core_start_observed':None,'hardware_image_identity_verified':False,
            'complete_video_acceptance':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--smoke-only',action='store_true');args=parser.parse_args()
    args.out_dir.mkdir(parents=True,exist_ok=False)
    try:report=audit(args.run,args.smoke_only)
    except Exception as exc:report={'status':'FAIL','error':repr(exc),'scope':'RAW_INPUT_PROTOCOL_AUDIT_NOT_BOARD'}
    report['auditor_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (args.out_dir/'INDEPENDENT_INPUT_PROTOCOL.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'out':str(args.out_dir),'error':report.get('error')}))
    return 0 if report['status'].startswith('PASS') else 1


if __name__=='__main__':raise SystemExit(main())
