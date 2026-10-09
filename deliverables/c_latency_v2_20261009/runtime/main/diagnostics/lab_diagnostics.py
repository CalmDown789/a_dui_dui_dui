"""Observation only: no image permission, protocol, retry or acceptance changes."""
import faulthandler
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_prefix = None
_stack_file = None
_first_packet = False


def stage(event, **fields):
    print(json.dumps(dict(diagnostic=True, event=event, utc=datetime.now(timezone.utc).isoformat(),
                          monotonic_ns=time.monotonic_ns(), pid=os.getpid(), **fields),
                     ensure_ascii=True), flush=True)


def configure(prefix, interval):
    global _prefix, _stack_file
    if not 0 < interval <= 120:
        raise ValueError('Stack interval must be in (0, 120] seconds')
    _prefix = Path(prefix)
    worker = dict(scope='DIAGNOSTIC_BOOTSTRAP_WORKER_V2', pid=os.getpid(),
                  parent_pid=os.getppid(), executable=sys.executable, prefix=sys.prefix,
                  owner_token=os.environ.get('PLD_DIAGNOSTIC_OWNER_TOKEN'))
    with Path(str(_prefix) + '.worker.json').open('x', encoding='utf-8') as f:
        json.dump(worker, f, indent=2)
        f.write('\n')
        f.flush()
    stage('WORKER_IDENTITY_RECORDED', parent_pid=worker['parent_pid'], executable=sys.executable)
    auth_path = Path(str(_prefix) + '.worker.auth.json')
    auth_deadline = time.monotonic() + 10
    while time.monotonic() < auth_deadline:
        try:
            auth = json.loads(auth_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            time.sleep(.01)
            continue
        if (auth.get('scope') != 'DIAGNOSTIC_SUPERVISOR_AUTH_V2' or
                auth.get('owner_token') != worker['owner_token'] or
                auth.get('pid') != worker['pid'] or
                auth.get('executable') != worker['executable'] or
                auth.get('prefix') != worker['prefix']):
            raise RuntimeError('supervisor worker authentication record mismatch')
        supervisor_pid = auth.get('supervisor_pid')
        launcher_pid = auth.get('launcher_pid')
        expected_launcher = worker['pid'] if worker['parent_pid'] == supervisor_pid else worker['parent_pid']
        if launcher_pid != expected_launcher:
            raise RuntimeError('supervisor launch topology mismatch')
        stage('WORKER_IDENTITY_AUTHENTICATED', ownership_proof=auth.get('ownership_proof'))
        break
    else:
        raise TimeoutError('worker was not authenticated by the owned Job supervisor')
    _stack_file = Path(str(_prefix) + '.stacks.log').open('x', encoding='utf-8')
    faulthandler.cancel_dump_traceback_later()
    faulthandler.enable(file=_stack_file, all_threads=True)
    faulthandler.dump_traceback_later(interval, repeat=True, file=_stack_file, exit=False)
    stage('STACK_WATCHDOG_ARMED', interval_seconds=interval)


def first_packet_sent(byte_count, peer):
    global _first_packet
    if _first_packet:
        return
    _first_packet = True
    # A successful sendto means the OS accepted the datagram, not that the FPGA
    # received it or replied. Capture that distinction in both logs and marker.
    record = dict(scope='FIRST_UDP_SENDTO_RETURNED_OS_ACCEPTED_ONLY',
                  pid=os.getpid(), utc=datetime.now(timezone.utc).isoformat(),
                  monotonic_ns=time.monotonic_ns(), bytes=byte_count, peer=list(peer),
                  owner_token=os.environ.get('PLD_DIAGNOSTIC_OWNER_TOKEN'),
                  board_receive_or_reply_proven=False)
    stage('FIRST_UDP_SEND_RETURNED', **{k: v for k, v in record.items() if k not in ('pid', 'utc', 'monotonic_ns', 'owner_token')})
    if _prefix is not None:
        with Path(str(_prefix) + '.first_packet.json').open('x', encoding='utf-8') as f:
            json.dump(record, f, indent=2)
            f.write('\n')
            f.flush()
        faulthandler.cancel_dump_traceback_later()
        # Later stacks help diagnose host file waits as well, but the external
        # 120-second pre-packet deadline is disarmed after the marker is seen.
        faulthandler.dump_traceback_later(120, repeat=True, file=_stack_file, exit=False)


class ObservedSocket:
    """Delegate every socket operation; observe only the first sendto result."""
    def __init__(self, sock):
        self._socket = sock
        self._send_attempted = False

    def __getattr__(self, name):
        return getattr(self._socket, name)

    def sendto(self, payload, peer):
        if not self._send_attempted:
            self._send_attempted = True
            stage('FIRST_UDP_SEND_ENTER', bytes=len(payload), peer=list(peer))
        result = self._socket.sendto(payload, peer)
        first_packet_sent(result, peer)
        return result


def observe_client(client):
    client.sock = ObservedSocket(client.sock)
    stage('OUTPUT_DIRECTORY_AND_SOCKET_READY', out_dir=str(client.out))


def shutdown():
    global _stack_file
    faulthandler.cancel_dump_traceback_later()
    faulthandler.disable()
    if _stack_file is not None:
        _stack_file.close()
        _stack_file = None
