"""Independent raw EVF1/EVF2 lab audit; never imports StreamingClient state."""
from pathlib import Path
import argparse, hashlib, json, struct, sys, zlib

PACKAGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE / 'lab'))
sys.path.insert(0, str(PACKAGE / 'host')); sys.path.insert(0, str(PACKAGE / 'scripts'))
sys.path.insert(0, str(PACKAGE / 'streaming'))
from video_sequence_identity import verify_sequence
from binary_journal import records
from audit_protocol import parse
from streaming_board_lab import streaming_selection
from board_characterization_identity import verify_capture

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def audit(run):
    report = json.loads((run / 'REPORT.json').read_text(encoding='utf-8'))
    assert report['success'] is True and report['status'] == 'COMPLETE_PROTOCOL_BYTES_PENDING_INDEPENDENT_RAW_AUDIT'
    # File-only root identity checks are repeated, independently of runtime.
    binding, cfg, cfg_sha = streaming_selection(report['mode'], None, True, report['output_window'])
    assert cfg_sha == report['streaming_selection_sha256']
    assert report['candidate_BIT_sha256'] == binding['candidate_identity']['BIT_sha256']
    assert (run / 'IMAGE_MANIFEST.json').read_bytes() == binding['candidate_path'].read_bytes()
    assert (run / 'SOURCE_MANIFEST.json').read_bytes() == binding['sequence_path'].read_bytes()
    observed = verify_capture(binding['candidate_identity'], run / 'startup_evidence/REPORT.json')
    pairs = binding['prepared']; n = len(pairs); session = bytes.fromhex(report['session']); peer = tuple(report['peer'])
    assert peer == tuple(binding['release']['peer']) and tuple(report['local']) == tuple(binding['release']['local'])
    events = [json.loads(s) for s in (run / 'frame_events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [e['frame_id'] for e in events] == list(range(n)) and all(e['event'] == 'VALIDATED_FRAME_ACCEPTED' for e in events)
    accepted_ns = {e['frame_id']: e['monotonic_ns'] for e in events}
    sent_inputs = {}; input_coverage = [set() for _ in pairs]; input_ack = [0]*n
    output_coverage = [set() for _ in pairs]; proofs = {}; done = set(); committed = set()
    actual = [bytearray(len(g)) for _, g in pairs]
    invalid = wrong_source = duplicates = final_requests = 0; negotiated = offered = False
    active = None; final_sent = set()
    input_crc = [zlib.crc32(x) for x, _ in pairs]; output_crc = [zlib.crc32(g) for _, g in pairs]
    cap = struct.pack('!HHB3x', 1024, report['output_window'], 0x17)
    for stamp, direction, raw, source in records(run / 'traffic/datagrams.bin'):
        if source != peer:
            assert direction == 1; wrong_source += 1; continue
        try: version, p = parse(raw)
        except ValueError:
            assert direction == 1; invalid += 1; continue
        if p.session != session or p.reserved:
            assert direction == 1; invalid += 1; continue
        if direction == 0 and version == 2 and p.type == 1:
            assert p.payload == cap and p.frame_bytes == 2073600 and p.frame_id == p.sequence == p.offset == p.frame_crc == p.next_offset == p.status == p.flags == 0
            offered = True; continue
        if direction == 1 and version == 2 and p.type == 0x81:
            assert offered and p.status == 0 and p.payload == cap and p.frame_bytes == 2073600
            assert p.frame_id == p.sequence == p.offset == p.frame_crc == p.next_offset == p.flags == 0
            negotiated = True; continue
        if not 0 <= p.frame_id < n:
            assert direction == 1; invalid += 1; continue
        f = p.frame_id; pixels, golden = pairs[f]
        if direction == 0 and version == 1 and p.type == 2:
            assert negotiated and p.frame_crc == input_crc[f] and p.frame_bytes == len(pixels) and not p.payload
            assert f == len(done) and (active is None or active == f)
            assert p.sequence == p.offset == p.status == p.next_offset == p.flags == 0
            active = f
        elif direction == 0 and version == 1 and p.type == 3:
            assert f == active
            assert p.offset == p.sequence*1024 and p.payload == pixels[p.offset:p.offset+1024]
            assert p.frame_crc == input_crc[f] and p.frame_bytes == len(pixels) and not p.flags
            assert p.sequence < input_ack[f]+16
            input_coverage[f].add(p.sequence); sent_inputs[(f,p.sequence)] = p
        elif direction == 1 and version == 1 and p.type == 0x83 and p.status == 1:
            original = sent_inputs[(f,p.sequence)]
            assert p.offset == original.offset and p.frame_crc == original.frame_crc and not p.payload and not p.flags
            assert p.frame_bytes == len(pixels)
            assert p.next_offset == p.offset+len(original.payload)
            input_ack[f] = max(input_ack[f],p.sequence+1)
        elif direction == 0 and version == 1 and p.type == 4:
            assert f == active
            assert input_ack[f] == (len(pixels)+1023)//1024 and p.frame_crc == input_crc[f]
            assert p.sequence == input_ack[f] and p.offset == len(pixels) and not p.payload
            assert p.frame_bytes == len(pixels) and p.flags == p.status == p.next_offset == 0
        elif direction == 1 and version == 1 and p.type == 0x84 and p.status == 2:
            assert p.frame_crc == input_crc[f] and p.frame_bytes == len(pixels)
            assert p.offset == p.next_offset == len(pixels) and p.sequence == (len(pixels)+1023)//1024 and not p.payload and not p.flags
            committed.add(f)
        elif direction == 1 and version == 2 and p.type == 0x17:
            if f != active: invalid += 1; continue
            at = p.sequence*1024
            if p.status != 1 or p.offset != at or p.frame_bytes != len(golden) or p.payload != golden[at:at+1024] or not p.payload:
                invalid += 1; continue
            last = at+len(p.payload) == len(golden)
            if p.flags != int(last) or p.frame_crc != (output_crc[f] if last else 0) or p.next_offset:
                invalid += 1; continue
            duplicates += p.sequence in output_coverage[f]
            output_coverage[f].add(p.sequence); proofs[(f,p.sequence)] = p.payload_crc
            actual[f][at:at+len(p.payload)] = p.payload
        elif direction == 0 and version == 2 and p.type == 0x97:
            assert f == active and p.frame_bytes == len(golden)
            assert p.status == 1 and not p.flags and p.sequence == 0 and p.offset == 0 and p.frame_crc == 0
            batch = list(struct.iter_unpack('!II',p.payload))
            assert 1 <= len(batch) <= report['output_window'] and len({q for q,c in batch}) == len(batch)
            for q,c in batch: assert proofs[(f,q)] == c
        elif direction == 0 and version == 2 and p.type == 9:
            assert f == active and p.frame_bytes == len(golden) and p.flags == p.status == p.next_offset == 0
            assert f in committed and output_coverage[f] == set(range((len(golden)+1023)//1024))
            assert p.frame_crc == output_crc[f] and p.offset == len(golden) and p.sequence == len(golden)//1024 and not p.payload
            assert accepted_ns[f] <= stamp, 'Frame acceptance must precede final ACK'
            final_requests += 1; final_sent.add(f)
        elif direction == 1 and version == 2 and p.type == 0x89 and p.status == 4:
            assert f in final_sent and p.frame_crc == output_crc[f] and p.next_offset == len(golden)
            assert p.offset == len(golden) and p.sequence == (len(golden)+1023)//1024 and p.frame_bytes == len(golden) and not p.flags and not p.payload
            done.add(f)
            if active == f: active = None
    assert negotiated and done == set(range(n))
    for f,(pixels,golden) in enumerate(pairs):
        assert input_coverage[f] == set(range((len(pixels)+1023)//1024)) and actual[f] == golden
        item = report['outputs'][f]; q = run/item['file']
        assert item['frame_id'] == f and item['bytes'] == len(golden) and sha(q) == item['sha256']
        assert q.read_bytes() == golden
        assert events[f]['identity']['integrity_sha256'] == hashlib.sha256(golden).hexdigest()
    return dict(status='PASS_INDEPENDENT_RAW_PROTOCOL_GOLDEN_AUDIT', frames=n, Golden_bytes=sum(len(g) for _,g in pairs),
                Golden_mismatches=0, duplicates_checked=duplicates, invalid_records_retained=invalid,
                wrong_source_records_retained=wrong_source, final_requests_checked=final_requests,
                source_manifest_sha256=sha(run/'SOURCE_MANIFEST.json'), raw_journal_sha256=sha(run/'traffic/datagrams.bin'),
                scope='LAB_RAW_PROTOCOL_BYTES_NOT_CORE_TIMING_ELECTRICAL_PC4K_OR_DISPLAY_ACCEPTANCE',
                audit_uses_client_state=False, board_programmed_by_auditor=False, socket_created=False,
                actual_startup_reaudited=True, whole_system_4K30_achieved=False)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True);ap.add_argument('--out-dir',type=Path,required=True)
    a=ap.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    try: result=audit(a.run.resolve());code=0
    except Exception as exc: result=dict(status='FAIL_RAW_AUDIT',error=repr(exc),socket_created=False);code=1
    (a.out_dir/'AUDIT.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result));return code
if __name__=='__main__':raise SystemExit(main())
