"""Prepare reviewable host-only candidate; do not mutate the paired package."""
from pathlib import Path
import difflib,hashlib,json,shutil,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
LIVE=Path(r'C:\t6dup09\main')

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    assert sha(LIVE/'PACKAGE_MANIFEST.json')=='4870f3ea9aca185fcdeebb9bf0074a715559a3b488dfad1152d3fbc4e1393de8'
    rows=[]
    rels=['streaming/streaming_client.py','streaming/timing_diagnostics.py','streaming/stream_receiver.py',
          'streaming/binary_journal.py','streaming/audit_protocol.py','host/video_protocol.py',
          'proof/host_regression.py','proof/check_host_window128.py']
    for rel in rels:
        for prefix in ['main','baseline']:
            dest=HERE/prefix/rel;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(LIVE/rel,dest)
        rows.append(dict(file=rel,source=str(LIVE/rel),baseline_sha256=sha(LIVE/rel)))
    client=HERE/'main/streaming/streaming_client.py'
    old=client.read_text()
    import_line='from video_protocol import Packet,decode,InvalidPacket'
    assert old.count(import_line)==1
    start=old.index('def decode_any(raw):\n');end=old.index('\nclass FrameDeadlineError',start)
    direct='''def decode_any(raw):
    if raw[:5]==b'EVF1\\x01':return 1,decode(raw)
    if raw[:5]!=b'EVF2\\x02' or len(raw)<64:
        raise InvalidPacket('version/header CRC')
    (magic,version,kind,flags,session,frame_id,sequence,offset,frame_bytes,frame_crc,
     count,status,next_offset,reserved,payload_crc,header_crc)=HEADER.unpack_from(raw)
    if zlib.crc32(raw[:60])!=header_crc:
        raise InvalidPacket('version/header CRC')
    if len(raw)>64+CHUNK_BYTES:raise InvalidPacket('LENGTH')
    # Validate the original EVF2 bytes once; avoid constructing an EVF1 surrogate.
    packet=Packet(kind,session,frame_id,sequence,offset,frame_bytes,frame_crc,
                  raw[64:],status,next_offset,flags,reserved)
    if count!=len(raw)-64:raise InvalidPacket('LENGTH',packet)
    if zlib.crc32(packet.payload)!=payload_crc:raise InvalidPacket('PAYLOAD_CRC',packet)
    return version,packet
'''
    new=old[:start]+direct+old[end:]
    new=new.replace(import_line,import_line+',HEADER,CHUNK_BYTES')
    client.write_text(new,encoding='utf-8')
    timing=HERE/'main/streaming/timing_diagnostics.py';old_t=timing.read_text();new_t=old_t
    replacements=[('min(31, wall_ns.bit_length() - 1)','min(31, max(0, wall_ns.bit_length() - 1))'),
                  ('item = (-wall_ns, self._sequence, event)','item = (wall_ns, self._sequence, event)'),
                  ('wall_ns > -self._slow[0][0]','wall_ns > self._slow[0][0]'),
                  ('sorted(self._slow)','sorted(self._slow, reverse=True)')]
    for before,after in replacements:
        assert new_t.count(before)==1;new_t=new_t.replace(before,after)
    timing.write_text(new_t,encoding='utf-8')
    patch=''
    for rel in ['streaming/streaming_client.py','streaming/timing_diagnostics.py']:
        before=(HERE/'baseline'/rel).read_text();after=(HERE/'main'/rel).read_text()
        patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
            fromfile='baseline/'+rel,tofile='main/'+rel))
    (HERE/'host_changes.patch').write_text(patch,encoding='utf-8')
    for row in rows:row['candidate_sha256']=sha(HERE/'main'/row['file'])
    data=HERE/'main/data';data.mkdir(exist_ok=True)
    m=json.loads((LIVE/'data/ETHERNET_SEQUENCE_MANIFEST.json').read_text())
    # Preserve the original manifest; only two explicitly selected frozen pairs are copied.
    shutil.copyfile(LIVE/'data/ETHERNET_SEQUENCE_MANIFEST.json',data/'ETHERNET_SEQUENCE_MANIFEST.json')
    assets=[]
    for frame in m['frames'][:2]:
        for kind in ['input','golden']:
            rel=frame[kind+'_file'];src=LIVE/'data'/rel;assert sha(src)==frame[kind+'_sha256']
            dst=data/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
            assets.append(dict(file=rel,source=str(src),sha256=sha(src)))
    validation=HERE/'validation';validation.mkdir(exist_ok=True)
    # Keep the corrected review-local fixtures on repeat preparation. Copying
    # the older adaptation here would restore its duplicate-window flood bug.
    for name in ['run_host_regression.py','protocol_edge_regression.py','injected_sender.py','run_window128.py']:
        assert (validation/name).is_file(), 'missing review-local validation fixture: '+name
    manifest=dict(status='ISOLATED_STEP02_HOST_CANDIDATE_NOT_PAIRED_RELEASE',files=rows,test_assets=assets,
        copied_frozen_frame_ids=[0,1],all_manifest_frames_included=False,
        changed_functional_files=['streaming/streaming_client.py','streaming/timing_diagnostics.py'],
        unchanged_release_identities={rel:sha(LIVE/rel) for rel in ['PACKAGE_MANIFEST.json',
            'rtl/evf2_result_window.sv','image/COMM_window128_150_lab_candidate.bit']},
        step01_candidate_sha256=sha(WORK/'output/RTL_STEP01_RETRY_20261009/rtl/evf2_result_window.sv'),
        board_io=False,RTL_changed=False,BIT_generated=False,
        nonblocking_receive_loop_implemented=False)
    save(HERE/'SOURCE_MANIFEST.json',manifest)
    print(json.dumps(dict(status='PREPARED',changed_files=manifest['changed_functional_files']),ensure_ascii=False))

if __name__=='__main__':main()
