"""Verify saved post-JTAG PHY0 permission evidence before opening a UDP socket."""
from pathlib import Path
import hashlib,json,math,re
from parse_phy_startup_status import parse_packet

def sha(data):return hashlib.sha256(data).hexdigest()

def validate_startup_contract(m):
    required=m.get('startup_configuration')
    if required is None:return None
    allowed={'protocol','report_required','program_tcl_sha256'}
    if not isinstance(required,dict) or set(required)!=allowed or required.get('protocol')!='PHY0/v1/32B/CRC16-CCITT-FALSE' or required.get('report_required') is not True:
        raise ValueError('Invalid or unsupported startup proof contract')
    if not isinstance(required.get('program_tcl_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',required['program_tcl_sha256']):
        raise ValueError('Issued JTAG programmer hash required')
    if m.get('actual_PHY_RX_delay')!=1 or m.get('actual_PHY_TX_delay')!=0:raise ValueError('Startup image must select RX1/TX0')
    return required

def complete_packets(raw):
    locations=[i for i in range(len(raw)) if raw.startswith(b'PHY0',i) and i+32<=len(raw)]
    packets=[raw[i:i+32] for i in locations]
    decoded=[parse_packet(p) for p in packets]
    if packets and any(p!=packets[0] for p in packets):raise ValueError('Cached PHY0 packets differ')
    return packets,decoded,locations

def verified_file(base,item):
    if not isinstance(item,dict) or not isinstance(item.get('file'),str):raise ValueError('Missing evidence file identity')
    rel=Path(item['file']);f=(base/rel).resolve()
    if rel.is_absolute() or rel.drive or '..' in rel.parts or not f.is_relative_to(base):raise ValueError('Evidence path outside capture')
    data=f.read_bytes()
    if len(data)!=item.get('bytes') or sha(data)!=item.get('sha256'):raise ValueError('Evidence file changed')
    return data

def verify_startup_permission(image_identity,report_path=None):
    m=image_identity['manifest'];required=validate_startup_contract(m)
    if required is None:
        if report_path is not None:raise ValueError('Startup proof supplied to incompatible image')
        return None
    if report_path is None:raise ValueError('Post-JTAG startup capture report required before network')
    p=Path(report_path).resolve();r=json.loads(p.read_text(encoding='utf-8'));base=p.parent
    if r.get('scope')!='ACX750_VIDEO_PHY_STARTUP_CAPTURE_V1' or r.get('error') is not None or type(r.get('JTAG_exit_code')) is not int or r['JTAG_exit_code']!=0:
        raise ValueError('Startup/JTAG capture failed')
    if r.get('BIT_sha256')!=m['BIT']['sha256'] or r.get('image_manifest_sha256')!=image_identity['manifest_sha256']:
        raise ValueError('Capture belongs to a different issued image')
    if r.get('programmer_sha256')!=required['program_tcl_sha256']:raise ValueError('Different JTAG programmer used')
    raw=verified_file(base,r.get('raw'))
    log=verified_file(base,r.get('program_console'))
    marker=b'TEMPORARY_JTAG_VIDEO_CONFIG_STATUS_PASS_PENDING_ACTUAL_ETHERNET_TEST=YES'
    if marker not in log.splitlines():raise ValueError('JTAG successful configuration marker missing')
    offset=r.get('post_JTAG_raw_offset')
    if type(offset) is not int or not 0<=offset<=len(raw):raise ValueError('Invalid post-JTAG raw offset')
    events=r.get('events',[]);names=[x.get('event') for x in events]
    wanted=['UART_OPENED_BEFORE_JTAG','JTAG_PROCESS_START','JTAG_PROCESS_EXIT']
    indices=[]
    for name in wanted:
        if names.count(name)!=1:raise ValueError('Missing/duplicate capture ordering event')
        indices.append(names.index(name))
    if indices!=sorted(indices):raise ValueError('UART must open before JTAG')
    times=[events[i]['monotonic_seconds'] for i in indices]
    if not all(type(t) in (int,float) and math.isfinite(t) for t in times) or not times[0]<=times[1]<times[2]:raise ValueError('Capture timing order mismatch')
    exit_event=events[indices[-1]]
    if type(exit_event.get('exit_code')) is not int or exit_event['exit_code']!=0 or type(exit_event.get('raw_offset')) is not int or exit_event['raw_offset']!=offset:raise ValueError('JTAG exit event mismatch')
    packets,decoded,locations=complete_packets(raw[offset:])
    if len(packets)<2:raise ValueError('Two complete identical post-JTAG PHY0 records required')
    if not all(d['actual_success_rx1_tx0'] for d in decoded):raise ValueError('PHY startup permission closed')
    return dict(report_file=str(p),report_sha256=sha(p.read_bytes()),raw_sha256=sha(raw),
                post_JTAG_raw_offset=offset,record_offsets=[offset+i for i in locations],packet_count=len(packets),
                status=decoded[0],scope='RAW_UART_WITH_ISSUED_IMAGE_AND_JTAG_LOG_BINDING_NOT_BITSTREAM_READBACK')
