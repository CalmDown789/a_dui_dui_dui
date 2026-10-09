"""Streaming audit of finite live evidence; memory is bounded to one wire frame.

4K event hashes are compared with independent references; only the final 4K raw
image is stored. Runtime performs a full pixel comparison for every generated
image. Application submission records do not certify physical panel refresh.
"""
from pathlib import Path
import argparse, hashlib, json, struct, sys, zlib
from live4k import guard, load, sha, HERE


def audit(package, run):
    report = json.loads((run/'REPORT.json').read_text(encoding='utf-8'))
    assert report['status']=='COMPLETE_MEASUREMENT'
    binding, cfg = guard(package, None, True)
    from board_characterization_identity import verify_capture
    from binary_journal import records
    from audit_protocol import parse
    observed = verify_capture(binding['candidate_identity'], run/'startup_evidence/REPORT.json')
    assert report['candidate_BIT_sha256']==cfg['candidate_BIT_sha256']
    assert report['supplement_manifest_sha256']==sha(HERE/'SUPPLEMENT_MANIFEST.json')
    assert (run/'SOURCE_MANIFEST.json').read_bytes()==binding['sequence_path'].read_bytes()
    assert (run/'IMAGE_MANIFEST.json').read_bytes()==binding['candidate_path'].read_bytes()
    result=audit_payloads(run,report,binding['prepared'],tuple(binding['release']['peer']),tuple(binding['release']['local']))
    result['actual_startup_reaudited']=True
    result['scope']='RAW_BOARD_BYTES_AND_RUNTIME_4K_APP_EVENTS_NOT_PANEL_REFRESH_OR_AUTOMATIC_GOAL_ACCEPTANCE'
    return result


def audit_payloads(run,report,pairs,expected_peer,expected_local,module=None,reference=None):
    # Shared pure evidence core for offline fault tests. It never supplies or
    # certifies real startup identity; main audit() always performs that guard.
    from binary_journal import records
    from audit_protocol import parse
    measure = json.loads((run/'measurement/RESULTS.json').read_text(encoding='utf-8'))
    assert sha(run/'measurement/RESULTS.json')==report['measurement_result_sha256']
    assert measure['status']=='COMPLETE_MEASUREMENT'
    n = report['offered_slots']; assert 1<=n<=18000 and measure['offered_slots']==n
    events = [json.loads(s) for s in (run/'measurement/accepted.jsonl').read_text(encoding='utf-8').splitlines()]
    generated = [json.loads(s) for s in (run/'measurement/outputs.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(events)==len(generated)==n
    assert [r['frame_id'] for r in events]==[r['frame_id'] for r in generated]==list(range(n))
    inputs_crc=[zlib.crc32(x) for x,_ in pairs]; outputs_crc=[zlib.crc32(g) for _,g in pairs]
    source_sha=[hashlib.sha256(g).hexdigest() for _,g in pairs]
    if module is None: module=load('audit_bound_pipeline',HERE/'pc4k/pipeline.py')
    if reference is None: reference=load('audit_bound_reference',HERE/'pc4k/reference.py')
    expected=[reference.integer_reference(module.np.frombuffer(g,dtype=module.np.uint8).reshape(1080,1920)) for _,g in pairs]
    expected_sha=[hashlib.sha256(a).hexdigest() for a in expected]
    for event,row in zip(events,generated):
        f=row['frame_id']; s=f%len(pairs)
        assert event['source_frame_id']==row['source_frame_id']==s
        assert event['input_sha256']==source_sha[s]
        assert row['generated_4k_sha256']==expected_sha[s] and row['mismatch_pixels']==0
        assert row['shape']==[2160,3840] and row['bytes']==8294400
        assert event['received_verified_ns']==row['received_verified_ns']
        assert event['begin_ns']<=row['received_verified_ns']<=row['processing_start_ns']<=row['processing_complete_ns']<=row['preview_submitted_ns']
    last=module.np.fromfile(run/'measurement/last_generated_4k.bin',dtype=module.np.uint8)
    assert last.size==8294400 and module.np.array_equal(last.reshape(2160,3840),expected[(n-1)%len(pairs)])
    session=bytes.fromhex(report['session']); peer=tuple(report['peer'])
    assert peer==expected_peer and tuple(report['local'])==expected_local
    cap=struct.pack('!HHB3x',1024,128,0x17); offered=negotiated=False
    active=None; done=0; input_packets=set(); output_packets=set(); sent_input={}; proofs={}
    input_ack=0; committed=False; final_sent=False; duplicates=invalid=wrong_source=final_requests=0
    for stamp,direction,raw,source in records(run/'traffic/datagrams.bin'):
        if source!=peer:
            assert direction==1; wrong_source+=1; continue
        try: version,p=parse(raw)
        except ValueError:
            assert direction==1; invalid+=1; continue
        if p.session!=session or p.reserved:
            assert direction==1; invalid+=1; continue
        if direction==0 and version==2 and p.type==1:
            assert p.payload==cap and p.frame_bytes==2073600; offered=True; continue
        if direction==1 and version==2 and p.type==0x81:
            assert offered and p.payload==cap and p.status==0; negotiated=True; continue
        f=p.frame_id
        if not 0<=f<n:
            assert direction==1; invalid+=1; continue
        pixels,golden=pairs[f%len(pairs)]; source_id=f%len(pairs)
        if direction==0 and version==1 and p.type==2:
            assert negotiated and f==done and (active is None or active==f)
            assert p.frame_crc==inputs_crc[source_id] and p.frame_bytes==len(pixels) and not p.payload
            assert p.sequence==p.offset==p.flags==p.status==p.next_offset==0
            if active is None:
                active=f; input_packets.clear(); output_packets.clear(); sent_input.clear(); proofs.clear()
                input_ack=0; committed=final_sent=False
        elif direction==0 and version==1 and p.type==3:
            assert f==active and p.offset==p.sequence*1024 and p.sequence<input_ack+16
            assert p.payload==pixels[p.offset:p.offset+1024] and p.frame_crc==inputs_crc[source_id]
            assert p.frame_bytes==len(pixels) and not p.flags
            input_packets.add(p.sequence); sent_input[p.sequence]=p
        elif direction==1 and version==1 and p.type==0x83 and p.status==1:
            if f!=active: invalid+=1; continue
            original=sent_input[p.sequence]
            assert p.offset==original.offset and p.frame_crc==original.frame_crc and not p.payload
            assert p.frame_bytes==len(pixels) and p.next_offset==p.offset+len(original.payload)
            input_ack=max(input_ack,p.sequence+1)
        elif direction==0 and version==1 and p.type==4:
            assert f==active and input_ack==(len(pixels)+1023)//1024
            assert input_packets==set(range(input_ack)) and p.frame_crc==inputs_crc[source_id]
            assert p.sequence==input_ack and p.offset==len(pixels) and not p.payload
        elif direction==1 and version==1 and p.type==0x84 and p.status==2:
            assert f==active and p.frame_crc==inputs_crc[source_id] and p.frame_bytes==len(pixels)
            assert p.offset==p.next_offset==len(pixels) and not p.payload; committed=True
        elif direction==1 and version==2 and p.type==0x17:
            if f!=active: invalid+=1; continue
            at=p.sequence*1024; last_packet=at+len(p.payload)==len(golden)
            if (p.status!=1 or p.offset!=at or p.frame_bytes!=len(golden) or not p.payload or
                    p.payload!=golden[at:at+1024] or p.flags!=int(last_packet) or p.next_offset or
                    p.frame_crc!=(outputs_crc[source_id] if last_packet else 0)):
                invalid+=1; continue
            duplicates+=p.sequence in output_packets; output_packets.add(p.sequence); proofs[p.sequence]=p.payload_crc
        elif direction==0 and version==2 and p.type==0x97:
            assert f==active and p.status==1 and p.frame_bytes==len(golden) and not p.frame_crc
            batch=list(struct.iter_unpack('!II',p.payload))
            assert 1<=len(batch)<=128 and len({q for q,c in batch})==len(batch)
            for q,c in batch: assert proofs[q]==c
        elif direction==0 and version==2 and p.type==9:
            assert f==active and committed and output_packets==set(range((len(golden)+1023)//1024))
            assert p.frame_crc==outputs_crc[source_id] and p.frame_bytes==p.offset==len(golden) and not p.payload
            assert events[f]['accepted_ns']<=stamp, 'PC queue acceptance must precede final ACK'
            final_sent=True; final_requests+=1
        elif direction==1 and version==2 and p.type==0x89 and p.status==4:
            if f<done: continue  # delayed previous completed-frame reply
            assert f==active==done and final_sent
            assert p.frame_crc==outputs_crc[source_id] and p.next_offset==p.offset==len(golden)
            assert p.frame_bytes==len(golden) and not p.payload
            done+=1; active=None
    assert negotiated and done==n and active is None
    return dict(status='PASS_STREAMED_RAW_GOLDEN_RELEASE_AND_4K_EVENT_REFERENCE_AUDIT',frames=n,
        Golden_bytes=n*2073600,Golden_mismatches=0,duplicates_checked=duplicates,invalid_retained=invalid,
        wrong_source_retained=wrong_source,final_requests_checked=final_requests,
        raw_journal_sha256=sha(run/'traffic/datagrams.bin'),actual_startup_reaudited=False,
        bounded_wire_frame_state=True,generated_4k_event_hashes_match_independent_reference=True,
        full_last_4k_raw_reference_zero_difference=True,all_4k_raw_frames_saved=False,
        physical_display_refresh_measured=False,whole_system_4K30_achieved=False,
        scope='PURE_MATERIALIZED_PROTOCOL_AND_4K_EVENT_AUDIT_STARTUP_NOT_CERTIFIED')


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--package',type=Path,required=True)
    ap.add_argument('--run',type=Path,required=True); ap.add_argument('--out-dir',type=Path,required=True)
    a=ap.parse_args(); a.out_dir.mkdir(parents=True,exist_ok=False)
    try: result=audit(a.package.resolve(),a.run.resolve()); code=0
    except BaseException as exc: result=dict(status='FAIL_PRESERVE_RAW_AUDIT',error=repr(exc),socket_created=False); code=1
    (a.out_dir/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False)); return code


if __name__=='__main__': raise SystemExit(main())
