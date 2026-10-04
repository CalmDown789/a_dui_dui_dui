`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

// ACX750 physical wrapper for the multi-frame UART test.
// Profile is selected by the build script: 100 MHz / divide 12 or 150 MHz / divide 8.
module c_multiframe_synth_top #(
    parameter integer CORE_CLK_HZ = 100000000,
    parameter real CLKOUT0_DIVIDE_F = 12.0
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
        .CLKOUT0_DIVIDE_F   (CLKOUT0_DIVIDE_F)
    ) u_multiframe (
        .sys_clk                 (sys_clk),
        .rst_n                   (rst_n),
        .uart_rx                 (uart_rx),
        .led                     (led),
        .uart_tx                 (uart_tx),
        .dbg_frame_start         (dbg_frame_start),
        .dbg_frame_done          (dbg_frame_done),
        .dbg_frame_active        (dbg_frame_active),
        .dbg_expected_frame_id  (dbg_expected_frame_id),
        .dbg_frame_error_count  (dbg_frame_error_count),
        .dbg_uart_bytes          (dbg_uart_bytes),
        .dbg_core_busy           (dbg_core_busy),
        .dbg_core_done           (dbg_core_done)
    );
endmodule

`default_nettype wire
