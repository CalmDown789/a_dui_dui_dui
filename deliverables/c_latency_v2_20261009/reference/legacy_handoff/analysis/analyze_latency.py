"""Offline journal timing analysis. No sockets, JTAG, or hardware access."""
from pathlib import Path
from collections import Counter
import argparse, hashlib, json, math, statistics, struct, zlib

RH = struct.Struct('!QIB4sH')
PH = struct.Struct('!4sBBH16sIIIIIHHIIII')

def stats(xs):
    xs = sorted(xs)
    if not xs:
        return {'count': 0}
    return dict(count=len(xs), median=statistics.median(xs),
                p95=xs[math.ceil(.95*len(xs))-1], max=xs[-1], min=xs[0])

def analyze(journal, frames_path):
    frames = {}; digest = hashlib.sha256(); records = 0; kinds = Counter()
    with journal.open('rb', buffering=4*1024*1024) as stream:
        magic = stream.read(8); assert magic == b'EVFJ\x02\x00\x00\x00'
        digest.update(magic)
        while head := stream.read(RH.size):
            assert len(head) == RH.size
            stamp, length, direction, ip, port = RH.unpack(head)
            assert direction in (0, 1) and 64 <= length <= 65535
            raw = stream.read(length); assert len(raw) == length
            digest.update(head); digest.update(raw); records += 1
            f = PH.unpack_from(raw)
            magic, version, kind, flags, session, frame, seq = f[:7]
            assert (magic, version) in ((b'EVF1',1),(b'EVF2',2))
            assert f[10] == len(raw)-64 and zlib.crc32(raw[:60]) == f[15]
            assert zlib.crc32(raw[64:]) == f[14]
            kinds[f'{direction}:{version}:{kind:02x}'] += 1
            row = frames.setdefault(frame, dict(sent={}, pending=set(), rtt=[], gaps=[],
                gaps_full=[], last_ack=None, outputs={}, output_gaps=[], last_output=None,
                input_retransmits=0, output_duplicates=0, commit=None, commit_ack=None))
            if direction == 0 and version == 1 and kind == 3:
                row['input_retransmits'] += seq in row['sent']
                row['sent'].setdefault(seq, stamp); row['pending'].add(seq)
            elif direction == 1 and version == 1 and kind == 0x83 and f[11] == 1:
                if seq in row['sent']: row['rtt'].append((stamp-row['sent'][seq])/1e6)
                if row['last_ack'] is not None:
                    gap = (stamp-row['last_ack'])/1e6
                    row['gaps'].append(gap)
                    if gap > .5: row['gaps_full'].append((gap, len(row['pending']) == 16))
                row['last_ack'] = stamp
                row['pending'].difference_update(q for q in tuple(row['pending']) if q <= seq)
            elif direction == 0 and version == 1 and kind == 4:
                row['commit'] = stamp
            elif direction == 1 and version == 1 and kind == 0x84:
                row['commit_ack'] = stamp
            elif direction == 1 and version == 2 and kind == 0x17:
                if seq in row['outputs']: row['output_duplicates'] += 1
                else:
                    row['outputs'][seq] = stamp
                    if row['last_output'] is not None:
                        row['output_gaps'].append((stamp-row['last_output'])/1e6)
                    row['last_output'] = stamp
    manifest = json.loads((journal.parent/'JOURNAL.json').read_text(encoding='utf-8-sig'))
    assert manifest['sha256'] == digest.hexdigest() and manifest['records'] == records
    if frames_path.suffix == '.jsonl':
        timings = [json.loads(line) for line in frames_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    else: timings = json.loads(frames_path.read_text(encoding='utf-8-sig'))
    rows=[]
    for timing in timings:
        fid=timing['frame']; r=frames[fid]; out=r['outputs']
        first=min(out.values()); last=max(out.values())
        rows.append(dict(frame=fid, stages_ms={k:v/1e6 for k,v in timing['timing_ns'].items()},
            input_packets=len(r['sent']), input_retransmits=r['input_retransmits'],
            input_ack_record_rtt_ms=stats(r['rtt']), input_ack_record_gaps_ms=stats(r['gaps']),
            input_ack_gaps_above_0_5ms=len(r['gaps_full']),
            input_ack_long_gap_sum_ms=sum(g for g,full in r['gaps_full']),
            input_ack_long_gaps_window_full=sum(full for g,full in r['gaps_full']),
            output_unique=len(out), output_duplicates=r['output_duplicates'],
            output_first_last_host_record_ms=(last-first)/1e6,
            commit_request_to_first_output_host_record_ms=(first-r['commit'])/1e6,
            commit_ack_to_first_output_host_record_ms=(first-r['commit_ack'])/1e6,
            output_record_gaps_ms=stats(r['output_gaps'])))
    return dict(scope='OFFLINE_HOST_JOURNAL_TIMESTAMPS_NOT_WIRE_RTT_OR_FPGA_APPLY_TIMESTAMPS',
        journal_sha256=digest.hexdigest(), journal_bytes=journal.stat().st_size, records=records,
        frame_count=len(rows), packet_kinds=dict(kinds),
        interpretation='TX stamps precede sendto; RX stamps follow recvfrom. Pending-window inference follows cumulative EVF1 ACK retirement. Gaps do not locate USB/NIC/OS/FPGA delay.',
        stages_ms={key:stats([r['stages_ms'][key] for r in rows]) for key in rows[0]['stages_ms']},
        input_ack_record_rtt_ms=stats([x for r in frames.values() for x in r['rtt']]),
        input_ack_gaps_above_0_5ms=sum(r['input_ack_gaps_above_0_5ms'] for r in rows),
        input_ack_long_gaps_window_full=sum(r['input_ack_long_gaps_window_full'] for r in rows),
        input_ack_long_gap_sum_per_frame_ms=stats([r['input_ack_long_gap_sum_ms'] for r in rows]),
        output_first_last_host_record_ms=stats([r['output_first_last_host_record_ms'] for r in rows]),
        input_retransmits=sum(r['input_retransmits'] for r in rows),
        output_duplicates=sum(r['output_duplicates'] for r in rows), frames=rows)

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--journal',type=Path,required=True)
    p.add_argument('--frames',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); result=analyze(a.journal,a.frames)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'frames'},ensure_ascii=False))
