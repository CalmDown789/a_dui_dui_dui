"""Verify LAB UART/JTAG file binding; no electrical/network/video acceptance."""
from pathlib import Path
import argparse, json
from board_characterization_identity import verify_candidate, verify_capture

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--issued-manifest-sha256', required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--out-file', type=Path, required=True)
    a = p.parse_args()
    result = dict(scope='LAB_UART_JTAG_IDENTITY_AUDIT_ONLY', physical_IO_signoff=False,
                  network_video_permission=False, electrical_pass=False, video_pass=False)
    try:
        identity = verify_candidate(a.manifest, a.issued_manifest_sha256)
        result.update(status='LAB_STARTUP_IDENTITY_OBSERVED_ONLY', audited=verify_capture(identity, a.report))
    except Exception as exc:
        result.update(status='LAB_IDENTITY_AUDIT_REJECTED', error=repr(exc))
    with a.out_file.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps(dict(status=result['status'], error=result.get('error'))))
    return 0 if result['status'] == 'LAB_STARTUP_IDENTITY_OBSERVED_ONLY' else 1

if __name__ == '__main__':
    raise SystemExit(main())
