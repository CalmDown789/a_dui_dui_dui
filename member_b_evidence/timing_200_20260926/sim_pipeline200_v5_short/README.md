# v5 simulation evidence

Status: PASS for the explicitly selected tests below.

- `tb_b_real_backpressure`: RESULT: PASS  (B real five-layer under heavy back-pressure: 3/3 frames bit-exact)
- `tb_b_real_bit_exact`: RESULT: PASS  (96x54 bit-exact vs A integer Golden, 4/4 cases)

Raw log files are copied byte-for-byte with `.log.txt` names. Exact collected RTL/TB/runner text is under `source_snapshots/`. The summary records raw/canonical hashes, compiler paths, staging checks and counter scope. Hashes are collected now and guarded by file timestamps; see `provenance_boundary` and the supplied manifest's timestamp relation. No Git commit is substituted for uncommitted source identity. Simulation PASS does not establish timing closure or board validation.
