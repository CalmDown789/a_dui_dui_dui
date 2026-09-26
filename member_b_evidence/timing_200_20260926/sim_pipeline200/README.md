# v1 simulation evidence

Status: PASS for the explicitly selected tests below.

- `tb_b_real_backpressure`: RESULT: PASS  (B real five-layer under heavy back-pressure: 3/3 frames bit-exact)
- `tb_b_real_bit_exact`: RESULT: PASS  (96x54 bit-exact vs A integer Golden, 4/4 cases)
- `tb_b_real_full`: RESULT: PASS  (full-frame 1920x1080 integer Golden, byte-exact 2073600/2073600)
- `tb_ready_valid`: RESULT: PASS  (all A~K scenarios, 0 error)
- `tb_c_top`: RESULT: PASS  (Part A 全尺寸边界 + Part B c_top 冒烟, 0 error)

Raw log files are copied byte-for-byte with `.log.txt` names. Exact collected RTL/TB/runner text is under `source_snapshots/`. The summary records raw/canonical hashes, compiler paths, staging checks and counter scope. Hashes are collected now and guarded by file timestamps; see `provenance_boundary` and the supplied manifest's timestamp relation. No Git commit is substituted for uncommitted source identity. Simulation PASS does not establish timing closure or board validation.
