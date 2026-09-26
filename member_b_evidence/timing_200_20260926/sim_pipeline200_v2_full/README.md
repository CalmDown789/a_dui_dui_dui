# v2 simulation evidence

Status: PASS for the explicitly selected tests below.

- `tb_b_real_full`: RESULT: PASS  (full-frame 1920x1080 integer Golden, byte-exact 2073600/2073600)

Raw log files are copied byte-for-byte with `.log.txt` names. Exact collected RTL/TB/runner text is under `source_snapshots/`. The summary records raw/canonical hashes, compiler paths, staging checks and counter scope. Hashes are collected now and guarded by file timestamps; see `provenance_boundary` and the supplied manifest's timestamp relation. No Git commit is substituted for uncommitted source identity. Simulation PASS does not establish timing closure or board validation.
