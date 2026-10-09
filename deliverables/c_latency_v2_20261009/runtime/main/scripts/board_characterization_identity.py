"""Independent LAB identity/evidence checks; never grant formal video permission."""
from pathlib import Path
import hashlib, json, math, re
from parse_phy_startup_status import parse_packet

SCOPE = 'ACX750_BOARD_CHARACTERIZATION_IMAGE'
STAGE = 'BOARD_CHARACTERIZATION_ONLY'
SOURCE_DCP_SHA = '47e5a1ece0b669fa45597ab3ae4b7ca826fc1857cd8c3d43d4a7d009a84b68da'
C_SOURCE = 'C_INTEGRATED_STEPS01_04_RETRY_EDGE_20261009_a4bc4b7c3f0a8438'
B_SOURCE = 'B_THREE_SLOT_20261007_b8042e6673892647'
MARKER = b'CHARACTERIZATION_ONLY_JTAG_CONFIG_STATUS=YES'
TOOLS = {'board_characterization_identity.py', 'preflight_board_characterization.py',
         'capture_board_characterization.py', 'verify_board_characterization_capture.py',
         'parse_phy_startup_status.py', 'program_board_characterization.tcl',
         'run_c_characterization.ps1', 'zip_evidence.py'}
HISTORICAL_BITS = {
    'a907a50af0528d2149b369a404eb0eade3b282a14e1e9b1e7419acf66b43c0cd',
    '5080a27bf5f2f0ad362179a40e61e5903fd847db5801e029cbc5ea704ec6aae1',
    '29a28d27516dfc408ac84a5f2a8a19e2ae1de975ce6bee67b1668de4c213c91e',
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def valid_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None

def file_item(base, item):
    if not isinstance(item, dict) or not isinstance(item.get('file'), str) or not item['file']:
        raise ValueError('File identity absent')
    rel = Path(item['file'])
    path = (base / rel).resolve()
    if rel.is_absolute() or rel.drive or '..' in rel.parts or not path.is_relative_to(base):
        raise ValueError('File path escapes package/evidence')
    if not valid_sha(item.get('sha256')) or not path.is_file():
        raise ValueError('Real file and SHA256 required: ' + str(path))
    data = path.read_bytes()
    if not data or sha(data) != item['sha256']:
        raise ValueError('File empty or SHA256 differs: ' + str(path))
    return path, data

def verify_characterization_manifest(path, issued_manifest_sha256):
    if not valid_sha(issued_manifest_sha256):
        raise ValueError('Root-issued real manifest SHA256 required; pending/unissued is rejected')
    path = Path(path).resolve()
    data = path.read_bytes()
    if sha(data) != issued_manifest_sha256:
        raise ValueError('Manifest differs from independently published root SHA256')
    m = json.loads(data.decode('utf-8-sig'))
    if not isinstance(m, dict) or m.get('scope') != SCOPE or m.get('release_stage') != STAGE:
        raise ValueError('Only independent BOARD_CHARACTERIZATION scope accepted')
    if m.get('physical_IO_signoff') is not False or m.get('network_video_permission') is not False:
        raise ValueError('Characterization must explicitly deny physical signoff and network/video permission')
    if m.get('electrical_status') != 'UNVERIFIED' or m.get('root_issued_for_characterization') is not True:
        raise ValueError('Root must issue an explicitly electrical-unverified characterization candidate')
    if m.get('source_routed_DCP_sha256') != SOURCE_DCP_SHA:
        raise ValueError('Source routed DCP differs from root-selected candidate')
    if m.get('part') != 'xc7a200tfbg484-2' or m.get('C_source') != C_SOURCE or m.get('B_source') != B_SOURCE:
        raise ValueError('Frozen device/model source identity differs')
    for name, value in [('core_MHz', 150), ('pause', 0), ('actual_PHY_RX_delay', 1), ('actual_PHY_TX_delay', 0)]:
        if type(m.get(name)) is not int or m[name] != value:
            raise ValueError('Frozen characterization parameter differs: ' + name)
    tools = m.get('tools_sha256')
    if not isinstance(tools, dict) or set(tools) != TOOLS:
        raise ValueError('All eight independent tools must be bound to the root release')
    for name, expected in tools.items():
        actual_file = Path(__file__).resolve().parent / name
        if not valid_sha(expected) or not actual_file.is_file() or sha(actual_file.read_bytes()) != expected:
            raise ValueError('Characterization tool SHA256 mismatch: ' + name)
    if not valid_sha(m.get('program_tcl_sha256')) or m['program_tcl_sha256'] != tools['program_board_characterization.tcl']:
        raise ValueError('Issued candidate JTAG programmer contract differs')
    bit_path, bit_data = file_item(path.parent, m.get('BIT'))
    if bit_path.suffix.lower() != '.bit' or sha(bit_data) in HISTORICAL_BITS:
        raise ValueError('Historical/non-BIT file is not the root candidate')
    _, routed_data = file_item(path.parent, m.get('routed_DCP'))
    if sha(routed_data) != SOURCE_DCP_SHA:
        raise ValueError('Actual routed checkpoint differs')
    source_base = path.parent.parent / 'rtl'
    sources = m.get('COMM_source_manifest')
    if not isinstance(sources, dict) or not sources:
        raise ValueError('Source manifest required')
    for name, digest in sources.items():
        file_item(source_base, {'file': name, 'sha256': digest})
    review_path, review_data = file_item(path.parent, m.get('digital_review'))
    review = json.loads(review_data.decode('utf-8-sig'))
    if (not isinstance(review, dict) or review.get('source_routed_DCP_sha256') != SOURCE_DCP_SHA
        or review.get('status') != 'PASS_DIGITAL_IMPLEMENTATION_ONLY_ELECTRICAL_UNVERIFIED'
        or review.get('approved_for_characterization_only') is not True
        or review.get('physical_IO_signoff') is not False):
        raise ValueError('Root digital review has not approved this exact source for characterization only')
    for key in ['LTX']:
        if m.get(key) is not None:
            file_item(path.parent, m[key])
    return dict(scope='LOCAL_LAB_FILES_ROOT_DECLARATION_ONLY_NOT_HARDWARE_READBACK',
                manifest=m, manifest_file=str(path), manifest_sha256=sha(data),
                BIT_file=str(bit_path), BIT_sha256=sha(bit_data),
                digital_review_file=str(review_path), digital_review_sha256=sha(review_data),
                source_routed_DCP_sha256=SOURCE_DCP_SHA, programmer_sha256=m['program_tcl_sha256'],
                physical_IO_signoff=False, network_video_permission=False)

def post_exit_records(raw, offset):
    if type(offset) is not int or not 0 <= offset <= len(raw):
        raise ValueError('Strict integer post-JTAG offset required')
    tail = raw[offset:]
    positions = [i for i in range(len(tail)) if tail.startswith(b'PHY0', i) and i + 32 <= len(tail)]
    packets = [tail[i:i + 32] for i in positions]
    decoded = [parse_packet(p) for p in packets]
    if packets and any(p != packets[0] for p in packets):
        raise ValueError('Cached post-JTAG PHY0 records differ')
    if decoded and not all(p['actual_success_rx1_tx0'] for p in decoded):
        raise ValueError('Startup failed or actual RX1/TX0 not observed')
    return packets, decoded, [offset + i for i in positions]

def audit_capture_payload(report, base, expected):
    """Audit raw data binding only. This helper never creates an image permission."""
    if (report.get('scope') != 'ACX750_BOARD_CHARACTERIZATION_UART_CAPTURE_V1'
        or report.get('release_stage') != STAGE or report.get('error') is not None
        or report.get('physical_IO_signoff') is not False or report.get('network_video_permission') is not False):
        raise ValueError('Not a successful independent characterization capture')
    for field in ['manifest_sha256', 'BIT_sha256', 'programmer_sha256', 'source_routed_DCP_sha256']:
        if report.get(field) != expected[field]:
            raise ValueError('Capture belongs to different root selection: ' + field)
    if type(report.get('JTAG_exit_code')) is not int or report['JTAG_exit_code'] != 0:
        raise ValueError('Actual successful JTAG exit required')
    _, raw = file_item(base, report.get('raw'))
    _, log = file_item(base, report.get('program_console'))
    _, events_raw = file_item(base, report.get('events_file'))
    for item, payload in [(report['raw'], raw), (report['program_console'], log), (report['events_file'], events_raw)]:
        if type(item.get('bytes')) is not int or item['bytes'] != len(payload):
            raise ValueError('Evidence byte length differs')
    if MARKER not in log.splitlines():
        raise ValueError('Independent LAB JTAG success marker missing')
    events = [json.loads(line) for line in events_raw.decode('utf-8').splitlines()]
    if events != report.get('events'):
        raise ValueError('REPORT event list differs from original events.jsonl')
    names = [e.get('event') for e in events]
    required = ['UART_OPENED_BEFORE_JTAG', 'JTAG_PROCESS_START', 'JTAG_PROCESS_EXIT']
    if any(names.count(name) != 1 for name in required):
        raise ValueError('Missing/duplicate UART/JTAG ordering event')
    indices = [names.index(name) for name in required]
    times = [events[i].get('monotonic_seconds') for i in indices]
    if (indices != sorted(indices) or not all(type(t) in (int, float) and math.isfinite(t) for t in times)
        or not times[0] <= times[1] < times[2]):
        raise ValueError('UART must precede JTAG and successful exit')
    offset = report.get('post_JTAG_raw_offset')
    exit_event = events[indices[-1]]
    if (type(exit_event.get('exit_code')) is not int or exit_event['exit_code'] != 0
        or type(exit_event.get('raw_offset')) is not int or exit_event['raw_offset'] != offset):
        raise ValueError('Exit event/offset differs from capture')
    packets, decoded, locations = post_exit_records(raw, offset)
    if len(packets) < 2:
        raise ValueError('Two complete identical successful post-JTAG PHY0 records required')
    return dict(scope='LAB_UART_FILE_BINDING_ONLY_NO_RUNTIME_OR_VIDEO_PERMISSION',
                record_count=len(packets), record_offsets=locations, status=decoded[0],
                raw_sha256=sha(raw), console_sha256=sha(log), events_sha256=sha(events_raw),
                physical_IO_signoff=False, network_video_permission=False,
                electrical_pass=False, video_pass=False, complete_stage_acceptance=False)

def verify_capture_bundle(identity, report_path):
    report_path = Path(report_path).resolve()
    report = json.loads(report_path.read_text(encoding='utf-8'))
    audited = audit_capture_payload(report, report_path.parent, identity)
    return dict(audited, report_sha256=sha(report_path.read_bytes()),
                manifest_sha256=identity['manifest_sha256'], BIT_sha256=identity['BIT_sha256'],
                source_routed_DCP_sha256=identity['source_routed_DCP_sha256'])

def verify_candidate(manifest_path, issued_manifest_sha256):
    """Stable public API: verify the actual root-issued LAB candidate, never a formal image."""
    return verify_characterization_manifest(manifest_path, issued_manifest_sha256)

def verify_capture(candidate_identity, report_path):
    """Stable public API: recheck actual candidate files then audit saved raw LAB capture."""
    if not isinstance(candidate_identity, dict) or candidate_identity.get('scope') != 'LOCAL_LAB_FILES_ROOT_DECLARATION_ONLY_NOT_HARDWARE_READBACK':
        raise ValueError('Use identity returned by verify_candidate, not a constructed formal identity')
    current = verify_candidate(candidate_identity['manifest_file'], candidate_identity['manifest_sha256'])
    for field in ['BIT_sha256', 'source_routed_DCP_sha256', 'programmer_sha256', 'digital_review_sha256']:
        if current[field] != candidate_identity[field]:
            raise ValueError('Candidate identity changed before saved capture audit: ' + field)
    return verify_capture_bundle(current, report_path)
