if {[llength $argv] != 1} { error "usage: stage6_synth_setup030.tcl <fresh_stage_directory>" }
set stage [file normalize [lindex $argv 0]]
if {![file isdirectory $stage] || ![file isfile "$stage/stage6_build_manifest.json"]} { error "stage directory or manifest missing: $stage" }
if {[file exists "$stage/placed_setup030.dcp"]} { error "refusing to overwrite placed DCP: $stage/placed_setup030.dcp" }
set here [file normalize [file dirname [info script]]]
set candidate [file normalize [file join $here ..]]
set job [file normalize [file join $candidate ..]]
set b_root [file join $job b_repro_reference]
set c_rtl "$candidate/overlay/multiframe/rtl"
set xdc "$candidate/overlay/multiframe/constr/c_top.xdc"
set out "$stage/reports"
cd $stage

set c_files [list \
    "$c_rtl/c_config.vh" "$c_rtl/input_rom.v" "$c_rtl/input_stream.v" \
    "$c_rtl/stripe_buffer.v" "$c_rtl/pingpong_buffer.v" "$c_rtl/output_stream.v" \
    "$c_rtl/uart_tx.v" "$c_rtl/readback_ctrl.v" "$c_rtl/c_ctrl.v" \
    "$c_rtl/b_core_stub.v" "$c_rtl/b_core_if.v" "$c_rtl/c_core.v" \
    "$c_rtl/c_observation.v" "$c_rtl/c_protocol_assertions.v" "$c_rtl/uart_rx.v" \
    "$c_rtl/uart_frame_loader.v" "$c_rtl/c_multiframe_top.v" "$c_rtl/c_multiframe_synth_top.v" \
]
set exp "$b_root/experiments/l5_splitmem_20260924/rtl/b"
set b_real "$b_root/rtl/b_real_ae29515/stream"
set b_files [list \
    "$b_real/same_pad_raster.sv" "$exp/elastic_fifo.sv" \
    "$b_real/window_kminus1_bram.sv" "$b_real/window_stream_frontend.sv" \
    "$b_real/eight_phase_issue.sv" "$exp/phase_mac_pipeline.sv" \
    "$exp/phase_accumulator_36.sv" "$exp/mac_issue_stage.sv" \
    "$exp/vector_postprocess_shared.sv" "$exp/fsrcnn_stream_layer.sv" \
    "$b_real/pixel_shuffle2x_row_banks.sv" "$exp/fsrcnn_network_core.sv" \
    "$b_real/fsrcnn_network_mem_top.sv" "$b_real/b_core_real.sv" \
    "$exp/prelu_requantize.sv" \
]
foreach f [concat $c_files $b_files [list $xdc "$stage/ip/ila_obs_snapshot/ila_obs_snapshot.xci" "$stage/ip/vio_obs_snapshot_ctrl/vio_obs_snapshot_ctrl.xci"]] {
    if {![file isfile $f]} { error "missing fresh-build input: $f" }
}
read_verilog -verbose $c_files
read_verilog -sv -verbose $b_files
set_part xc7a200tfbg484-2
read_ip [list "$stage/ip/ila_obs_snapshot/ila_obs_snapshot.xci" "$stage/ip/vio_obs_snapshot_ctrl/vio_obs_snapshot_ctrl.xci"]
if {[llength [get_ips]] != 2} { error "expected freshly imported ILA and VIO IPs" }
generate_target all [get_ips]
synth_ip [get_ips]
read_xdc -verbose $xdc

puts "STAGE6_TOP=c_multiframe_synth_top PART=xc7a200tfbg484-2 B_COMMIT=6cc8ea4173d2a720f741e80b7cbd9279558ee93a"
puts "STAGE6_XDC=$xdc SHA256_INPUT_MANIFEST=$stage/stage6_build_manifest.json"
synth_design -top c_multiframe_synth_top -part xc7a200tfbg484-2 \
    -generic CORE_CLK_HZ=150000000 \
    -generic CLKOUT0_DIVIDE_F=8.0 \
    -generic OBS_TEST_PAUSE_ENABLE=0 \
    -flatten_hierarchy rebuilt -verilog_define C_USE_B_REAL

set_property SEVERITY Error [get_drc_checks {NSTD-1 UCIO-1}]
set n_real [llength [get_cells -quiet -hier -filter {REF_NAME =~ b_core_real*}]]
set n_stub [llength [get_cells -quiet -hier -filter {REF_NAME =~ b_core_stub*}]]
set n_top [llength [get_cells -quiet -hier -filter {REF_NAME =~ fsrcnn_network_mem_top*}]]
set n_layer [llength [get_cells -quiet -hier -filter {REF_NAME =~ fsrcnn_stream_layer*}]]
set n_pshuf [llength [get_cells -quiet -hier -filter {REF_NAME =~ pixel_shuffle2x_row_banks*}]]
set n_fifo [llength [get_cells -quiet -hier -filter {REF_NAME =~ elastic_fifo*}]]
set n_ila [llength [get_cells -quiet -hier -filter {REF_NAME == ila_obs_snapshot}]]
set n_vio [llength [get_cells -quiet -hier -filter {REF_NAME == vio_obs_snapshot_ctrl}]]
puts "STAGE6_HIERARCHY b_core_real=$n_real b_core_stub=$n_stub network=$n_top layers=$n_layer pixel_shuffle=$n_pshuf fifo=$n_fifo ila=$n_ila vio=$n_vio"
if {$n_real != 1 || $n_stub != 0 || $n_top != 1 || $n_layer != 5 || $n_pshuf != 1 || $n_fifo < 4 || $n_ila != 1 || $n_vio != 1} {
    error "fresh candidate hierarchy self-check failed"
}

set l5_regs [get_cells -quiet -hier -filter {NAME =~ *l5/mac/issue/out_phase_reg*}]
set l5_q [get_pins -quiet -of_objects $l5_regs -filter {REF_PIN_NAME == Q}]
set l5_nets [get_nets -quiet -of_objects $l5_q]
if {[llength $l5_regs] == 0 || [llength $l5_regs] > 64 || [llength $l5_nets] == 0} { error "B standard L5 phase fanout collection unexpected" }
set bounded 0
foreach n $l5_nets {
    set loads [get_pins -quiet -of_objects $n -filter {DIRECTION == IN}]
    if {[llength $loads] > 48} { set_property MAX_FANOUT 48 $n; incr bounded }
}
puts "STAGE6_B_FANOUT_STANDARD regs=[llength $l5_regs] qpins=[llength $l5_q] nets=[llength $l5_nets] bounded=$bounded max_fanout=48"

report_utilization -file "$out/utilization_synth.rpt"
report_utilization -hierarchical -file "$out/utilization_synth_hier.rpt"
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 30 -file "$out/timing_summary_synth.rpt"
report_clocks -file "$out/clocks_synth.rpt"
report_io -file "$out/io_synth.rpt"
report_exceptions -coverage -file "$out/exceptions_synth.rpt"
report_drc -file "$out/drc_synth.rpt"
catch {report_ram_utilization -file "$out/ram_utilization_synth.rpt"}

set cp [get_pins -quiet {u_multiframe/g_mmcm.u_mmcm/CLKOUT0}]
set cc [get_clocks -quiet -of_objects $cp]
if {[llength $cp] != 1 || [llength $cc] != 1 || abs([get_property PERIOD $cc] - 1000.0/150.0) > 0.001} {
    error "expected one 150 MHz MMCM CLKOUT0 clock on candidate top"
}
report_clocks -file "$out/clocks_original.xdc.rpt"
write_xdc -force "$out/constraints_original.xdc"
set_clock_uncertainty -setup -from $cc -to $cc 0.300
update_timing
report_clocks -file "$out/clocks_setup030.rpt"
write_checkpoint -force "$stage/synth_setup030.dcp"
opt_design
place_design -directive ExtraNetDelay_high
phys_opt_design -directive AggressiveExplore
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 30 -file "$out/timing_placed_setup030.rpt"
write_checkpoint -force "$stage/placed_setup030.dcp"
puts "STAGE6_PLACEMENT_SETUP030_COMPLETE=$stage/placed_setup030.dcp"
