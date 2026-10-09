"""External experiment: retain sealed LAB guards and protocol implementation."""
from pathlib import Path
import argparse, hashlib, json, sys
sys.dont_write_bytecode = True
PACKAGE = Path(r'C:\t6int09\main')
sys.path.insert(0, str(PACKAGE / 'lab'))
import streaming_board_lab as lab

BaseClient = lab.StreamingClient


def client_class(batch):
    class InputBatchClient(BaseClient):
        def input_packets(self, pixels, frame, crc):
            if self.io is None:
                raise ValueError('Input batch experiment requires nonblocking IO')
            if self.io.pending is not None or self.io.ready:
                raise ValueError('Input phase begins with pending transport state')
            if self.io.batch_packets != 32 or self.io.batch_budget_ns != 200_000:
                raise ValueError('Baseline output receive configuration differs')
            self.io.batch_packets = batch
            try:
                return super().input_packets(pixels, frame, crc)
            finally:
                self.io.batch_packets = 32
    return InputBatchClient


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--input-batch', type=int, choices=(1, 4, 8, 32), required=True)
    ap.add_argument('--experiment-manifest', type=Path, required=True)
    args, remaining = ap.parse_known_args()
    manifest = json.loads(args.experiment_manifest.read_text(encoding='utf-8'))
    for name, digest in manifest['experiment_sources_sha256'].items():
        if hashlib.sha256((args.experiment_manifest.parent / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Experiment source changed: ' + name)
    if manifest['candidate_BIT_sha256'] != 'cefe3ba044bb208a08969714f48144870f5c00efc6879edb063ac1f358ef1ea5':
        raise ValueError('Wrong selected BIT')
    lab.StreamingClient = client_class(args.input_batch)
    sys.argv = [str(PACKAGE / 'lab/streaming_board_lab.py'), *remaining]
    result = lab.main()
    out = Path(remaining[remaining.index('--out-dir') + 1])
    if (out / 'REPORT.json').exists():
        report = json.loads((out / 'REPORT.json').read_text(encoding='utf-8'))
        report['experiment_runtime'] = dict(input_receive_batch_packets=args.input_batch,
            output_receive_batch_packets=32, receive_batch_budget_ns=200_000,
            phase_switch='Only input_packets; restore output batch in finally',
            base_protocol_and_guards_unchanged=True,
            experiment_manifest_sha256=hashlib.sha256(args.experiment_manifest.read_bytes()).hexdigest(),
            driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        (out / 'REPORT.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    raise SystemExit(main())
