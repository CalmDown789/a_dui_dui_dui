`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

// Physical wrapper for the C multi-frame endpoint and its 2025.2 debug cores.
// VIO control defaults to zero: record index 0 and no controlled pause.
module c_multiframe_synth_top #(
    parameter integer CORE_CLK_HZ = 100000000,
    parameter real CLKOUT0_DIVIDE_F = 12.0,
    parameter integer OBS_TEST_PAUSE_ENABLE = 0
) (
    input  wire       sys_clk,
    input  wire       rst_n,
    input  wire       uart_rx,
    output wire [7:0] led,
    output wire       uart_tx
);
    wire dbg_frame_start;
    wire dbg_frame_done;
    wire dbg_frame_active;
    wire [31:0] dbg_expected_frame_id;
    wire [31:0] dbg_frame_error_count;
    wire [31:0] dbg_uart_bytes;
    wire dbg_core_busy;
    wire dbg_core_done;
    wire [4:0] dbg_obs_control;
    wire [933:0] dbg_obs_snapshot_data;
    wire dbg_obs_snapshot_valid;
    wire [4:0] dbg_obs_snapshot_count;
    wire dbg_obs_snapshot_overflow;
    wire dbg_obs_pause_effective;
    wire dbg_obs_pause_forced_block;
    wire dbg_obs_clk;

    c_multiframe_top #(
        .IMG_W              (`C_IMG_W),
        .IMG_H              (`C_IMG_H),
        .OUT_W              (`C_OUT_W),
        .OUT_H              (`C_OUT_H),
        .STRIPE_H           (`C_STRIPE_H),
        .PIXEL_W            (`C_PIXEL_W),
        .ROM_ADDR_W         (`C_ROM_ADDR_W),
        .ROM_DEPTH          (`C_ROM_DEPTH_POW2),
        .USE_MMCM           (1),
        .CLK_HZ             (CORE_CLK_HZ),
        .UART_BAUD          (`C_UART_BAUD),
        .CLKOUT0_DIVIDE_F   (CLKOUT0_DIVIDE_F),
        .OBS_TEST_PAUSE_ENABLE (OBS_TEST_PAUSE_ENABLE)
    ) u_multiframe (
        .sys_clk                    (sys_clk),
        .rst_n                      (rst_n),
        .uart_rx                    (uart_rx),
        .led                        (led),
        .uart_tx                    (uart_tx),
        .dbg_frame_start            (dbg_frame_start),
        .dbg_frame_done             (dbg_frame_done),
        .dbg_frame_active           (dbg_frame_active),
        .dbg_expected_frame_id      (dbg_expected_frame_id),
        .dbg_frame_error_count      (dbg_frame_error_count),
        .dbg_uart_bytes             (dbg_uart_bytes),
        .dbg_core_busy              (dbg_core_busy),
        .dbg_core_done              (dbg_core_done),
        .dbg_obs_control            (dbg_obs_control),
        .dbg_obs_snapshot_data      (dbg_obs_snapshot_data),
        .dbg_obs_snapshot_valid     (dbg_obs_snapshot_valid),
        .dbg_obs_snapshot_count    (dbg_obs_snapshot_count),
        .dbg_obs_snapshot_overflow  (dbg_obs_snapshot_overflow),
        .dbg_obs_pause_effective    (dbg_obs_pause_effective),
        .dbg_obs_pause_forced_block (dbg_obs_pause_forced_block),
        .dbg_obs_clk                (dbg_obs_clk)
    );

    vio_obs_snapshot_ctrl u_obs_vio (
        .clk        (dbg_obs_clk),
        .probe_in0  (dbg_obs_snapshot_data[255:0]),
        .probe_in1  (dbg_obs_snapshot_data[511:256]),
        .probe_in2  (dbg_obs_snapshot_data[767:512]),
        .probe_in3  (dbg_obs_snapshot_data[933:768]),
        .probe_in4  (dbg_obs_snapshot_valid),
        .probe_in5  (dbg_obs_snapshot_count),
        .probe_out0 (dbg_obs_control)
    );

    ila_obs_snapshot u_obs_ila (
        .clk     (dbg_obs_clk),
        .probe0  (dbg_obs_snapshot_valid),
        .probe1  (dbg_obs_snapshot_data),
        .probe2  (dbg_obs_control[3:0]),
        .probe3  (dbg_frame_start),
        .probe4  (dbg_core_busy),
        .probe5  (dbg_core_done),
        .probe6  (dbg_frame_done),
        .probe7  (dbg_obs_pause_effective),
        .probe8  (dbg_obs_pause_forced_block),
        .probe9  (dbg_obs_snapshot_overflow)
    );
endmodule

`default_nettype wire
