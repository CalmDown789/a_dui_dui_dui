# C-side synthesis patch for the locked B RTL

These C-side overrides are derived from the byte-locked B sources below; the upstream copies remain unchanged:

- `phase_mac_pipeline.sv` from `rtl/b_real_ae29515/stream/phase_mac_pipeline.sv`, upstream commit `ae29515945fbb6e9566626d7f2d28660ac94d5c4`, SHA-256 `90274c20abafdb13b8550c9efc20ab6632e4b5fdf2f16690788b5a30ea9a6a4c`.
- `vector_postprocess_shared.sv` from `rtl/b_real_ae29515/stream/vector_postprocess_shared.sv`, upstream commit `ae29515945fbb6e9566626d7f2d28660ac94d5c4`, SHA-256 `1203bb7cfb7b491ca5a2c43abb08c74d9ddcaeb133f10f7b8b913035f5d72bb8`.

The MAC rewrite replaces the run-time `in_phase` arithmetic used to select
`act` and `weight` from packed buses with an eight-way `case`. Each case arm
uses a constant phase number, so its packed-bus part-select is fixed at
elaboration. The formula still supports every legal eight-phase layer
configuration guarded by the module's existing parameter check.

The postprocess rewrite registers the slot/channel-selected operands before
the PReLU DSP cascade and extends its metadata delay by one cycle. It adds one
pipeline stage without changing arithmetic or accepting a lower vector rate.

The MAC change avoids a general wide variable-index mux per multiplier lane.
The postprocess change removes the issue-slot selection mux from the DSP input
path. `scripts/run_sim.tcl` and `scripts/synth_bc_real.tcl` both use these files
so simulation and synthesis exercise the same implementation.

The isolated L5 probe completed with the selector rewrite while the original
dynamic selector probe did not complete within the guarded run. Integrated
regression, synthesis, and implementation results are recorded in
`docs/RTL_SYNTHESIS_MEMORY_AUDIT.md`.
