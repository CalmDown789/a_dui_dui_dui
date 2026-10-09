"""Read-only independent candidate preflight; no UART/JTAG/network or installs."""
from pathlib import Path
import argparse, json, sys
from board_characterization_identity import verify_characterization_manifest

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--issued-manifest-sha256', required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--check-com3', action='store_true')
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=False)
    result = dict(scope='BOARD_CHARACTERIZATION_LOCAL_PREFLIGHT_ONLY',
                  serial_opened=False, JTAG_started=False, socket_opened=False,
                  physical_IO_signoff=False, network_video_permission=False,
                  electrical_pass=False, video_pass=False)
    try:
        identity = verify_characterization_manifest(a.manifest, a.issued_manifest_sha256)
        if sys.version_info < (3, 9):
            raise ValueError('Use existing Python >=3.9')
        import serial
        from serial.tools import list_ports
        ports = [dict(device=p.device, description=p.description, hwid=p.hwid) for p in list_ports.comports()]
        if a.check_com3 and sum(p['device'].upper() == 'COM3' for p in ports) != 1:
            raise ValueError('COM3 not uniquely enumerated; no UART opened')
        result.update(status='LAB_LOCAL_FILES_READY_NOT_ELECTRICAL_OR_VIDEO_PASS', identity=identity,
                      python=sys.executable, version=sys.version,
                      pyserial_version=getattr(serial, '__version__', None), ports=ports)
    except Exception as exc:
        result.update(status='LAB_PREFLIGHT_REJECTED_NO_EXTERNAL_ACTION', error=repr(exc))
    (a.out_dir / 'PREFLIGHT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'error': result.get('error')}))
    return 0 if result['status'] == 'LAB_LOCAL_FILES_READY_NOT_ELECTRICAL_OR_VIDEO_PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
