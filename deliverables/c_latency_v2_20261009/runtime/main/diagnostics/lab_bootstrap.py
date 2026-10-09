"""Start stack capture before importing the lab entry and its dependencies."""
import sys
import time
import faulthandler

print('DIAG_BOOTSTRAP_ENTER monotonic_ns=' + str(time.monotonic_ns()), flush=True)
# This first timer covers argparse/runpy/helper imports. stderr is a real file
# owned by the external supervisor; it remains open for this process lifetime.
faulthandler.enable(file=sys.stderr, all_threads=True)
faulthandler.dump_traceback_later(30, repeat=True, file=sys.stderr, exit=False)

import argparse
import runpy
from pathlib import Path
import lab_diagnostics as diag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diag-prefix', required=True, type=Path)
    parser.add_argument('--stack-interval', type=float, default=30)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    diag.configure(args.diag_prefix, args.stack_interval)
    diag.stage('BOOTSTRAP_READY', target=str(args.target), python=sys.version)
    target_args = args.args[1:] if args.args[:1] == ['--'] else args.args
    sys.argv = [str(args.target), *target_args]
    code = 0
    try:
        diag.stage('TARGET_LOAD_BEGIN', file=str(args.target))
        runpy.run_path(str(args.target), run_name='__main__')
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        raise
    except BaseException:
        code = 1
        raise
    finally:
        diag.stage('TARGET_EXIT', exit_code=code)
        diag.shutdown()


if __name__ == '__main__':
    main()
