`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

// C integration wrapper for one-outstanding, framed UART input and raw UART
// output. A frame is fully staged in the existing 524288-byte input BRAM before
// C starts reading it; no BRAM writes occur while inference/output is active.
module c_multiframe_top #(
    parameter integer IMG_W = `C_IMG_W,
    parameter integer IMG_H = `C_IMG_H,
    parameter integer OUT_W = `C_OUT_W,
    parameter integer OUT_H = `C_OUT_H,
    parameter integer STRIPE_H = `C_STRIPE_H,
    parameter integer PIXEL_W = `C_PIXEL_W,
    parameter integer ROM_ADDR_W = `C_ROM_ADDR_W,
    parameter integer ROM_DEPTH = `C_ROM_DEPTH_POW2,
    parameter integer USE_MMCM = 0,
    parameter integer CLK_HZ = 100000000,
    parameter integer UART_BAUD = `C_UART_BAUD,
    parameter real CLKOUT0_DIVIDE_F = 12.0
) (
    input  wire       sys_clk,
    input  wire       rst_n,
    input  wire       uart_rx,
    output wire [7:0] led,
    output wire       uart_tx,
    output wire       dbg_frame_start,
    output wire       dbg_frame_done,
    output wire       dbg_frame_active,
    output wire [31:0] dbg_expected_frame_id,
    output wire [31:0] dbg_frame_error_count,
    output wire [31:0] dbg_uart_bytes,
    output wire       dbg_core_busy,
    output wire       dbg_core_done
);
    localparam integer FRAME_PIXELS = IMG_W * IMG_H;
    localparam integer OUTPUT_BYTES = OUT_W * OUT_H;

    wire core_clk;
    wire mmcm_locked;
    generate
        if (USE_MMCM != 0) begin : g_mmcm
            wire clkfb;
            wire clkout_unbuf;

            MMCME2_BASE #(
                .BANDWIDTH          ("OPTIMIZED"),
                .CLKFBOUT_MULT_F    (24.0),
                .CLKFBOUT_PHASE     (0.0),
                .CLKIN1_PERIOD      (20.0),
                .CLKOUT0_DIVIDE_F   (CLKOUT0_DIVIDE_F),
                .CLKOUT0_DUTY_CYCLE (0.5),
                .CLKOUT0_PHASE      (0.0),
                .DIVCLK_DIVIDE      (1),
                .REF_JITTER1        (0.010),
                .STARTUP_WAIT       ("FALSE")
            ) u_mmcm (
                .CLKOUT0   (clkout_unbuf),
                .CLKOUT0B  (), .CLKOUT1 (), .CLKOUT1B (),
                .CLKOUT2   (), .CLKOUT2B (), .CLKOUT3 (), .CLKOUT3B (),
                .CLKOUT4   (), .CLKOUT5 (), .CLKOUT6 (),
                .CLKFBOUT  (clkfb), .CLKFBOUTB (),
                .LOCKED    (mmcm_locked),
                .CLKIN1    (sys_clk),
                .PWRDWN    (1'b0),
                .RST       (~rst_n),
                .CLKFBIN   (clkfb)
            );
            BUFG u_clk_bufg (.I(clkout_unbuf), .O(core_clk));
        end else begin : g_bypass
            assign core_clk = sys_clk;
            assign mmcm_locked = 1'b1;
        end
    endgenerate

    wire core_rst_n = rst_n & mmcm_locked;
    wire [ROM_ADDR_W-1:0] frame_wr_addr;
    wire [PIXEL_W-1:0] frame_wr_data;
    wire frame_wr_en;
    wire core_busy, core_done;
    wire [31:0] uart_bytes;
    wire uart_tx_busy, readback_busy;
    wire [15:0] stripe_count, stripes_sent;
    wire [1:0] buf_state;
    wire proto_err, overflow_err;
    wire in_done, b_busy, b_done_seen;
    wire [15:0] in_x, in_y, out_x, out_y;
    wire [31:0] uart_framing_errors;
    wire protocol_error;
    wire [31:0] frame_error_count;
    wire [31:0] expected_frame_id;
    wire frame_start, frame_done, frame_active;

    uart_frame_loader #(
        .CLK_HZ         (CLK_HZ),
        .UART_BAUD      (UART_BAUD),
        .BAUD_DIV       ((CLK_HZ / UART_BAUD < 1) ? 1 : (CLK_HZ / UART_BAUD)),
        .FRAME_PIXELS   (FRAME_PIXELS),
        .OUTPUT_BYTES   (OUTPUT_BYTES),
        .ADDR_W         (ROM_ADDR_W)
    ) u_frame_loader (
        .clk                     (core_clk),
        .rst_n                   (core_rst_n),
        .uart_rx_pin             (uart_rx),
        .frame_wr_en             (frame_wr_en),
        .frame_wr_addr           (frame_wr_addr),
        .frame_wr_data           (frame_wr_data),
        .frame_start             (frame_start),
        .frame_done              (frame_done),
        .frame_active            (frame_active),
        .expected_frame_id       (expected_frame_id),
        .frame_error_count       (frame_error_count),
        .uart_framing_error_count(uart_framing_errors),
        .protocol_error          (protocol_error),
        .core_busy               (core_busy),
        .core_done               (core_done),
        .core_uart_bytes         (uart_bytes),
        .core_uart_tx_busy       (uart_tx_busy),
        .core_readback_busy      (readback_busy)
    );

    c_core #(
        .IMG_W          (IMG_W),
        .IMG_H          (IMG_H),
        .OUT_W          (OUT_W),
        .OUT_H          (OUT_H),
        .STRIPE_H       (STRIPE_H),
        .PIXEL_W        (PIXEL_W),
        .ROM_ADDR_W     (ROM_ADDR_W),
        .ROM_DEPTH      (ROM_DEPTH),
        .ROM_INIT_MODE  (0),
        .ROM_INIT_EN    (0),
        .ROM_INIT_FILE  (""),
        .CLK_HZ         (CLK_HZ),
        .UART_BAUD      (UART_BAUD)
    ) u_core (
        .clk                 (core_clk),
        .rst_n               (core_rst_n),
        .start               (frame_start),
        .busy                (core_busy),
        .done                (core_done),
        .rb_enable            (1'b1),
        .uart_tx              (uart_tx),
        .frame_wr_en          (frame_wr_en),
        .frame_wr_addr        (frame_wr_addr),
        .frame_wr_data        (frame_wr_data),
        .dbg_buf_state        (buf_state),
        .dbg_stripe_cnt       (stripe_count),
        .dbg_uart_bytes       (uart_bytes),
        .dbg_stripes_sent     (stripes_sent),
        .dbg_proto_err        (proto_err),
        .dbg_overflow_err     (overflow_err),
        .dbg_in_done          (in_done),
        .dbg_b_busy           (b_busy),
        .dbg_b_done_seen      (b_done_seen),
        .dbg_uart_tx_busy     (uart_tx_busy),
        .dbg_readback_busy    (readback_busy),
        .dbg_in_x             (in_x),
        .dbg_in_y             (in_y),
        .dbg_out_x            (out_x),
        .dbg_out_y            (out_y)
    );

    reg done_latch_q;
    reg [25:0] heartbeat_q;
    always @(posedge core_clk or negedge core_rst_n) begin
        if (!core_rst_n) begin
            done_latch_q <= 1'b0;
            heartbeat_q <= 26'd0;
        end else begin
            if (frame_done) done_latch_q <= 1'b1;
            heartbeat_q <= heartbeat_q + 1'b1;
        end
    end

    assign led[0] = frame_active | core_busy;
    assign led[1] = done_latch_q;
    assign led[2] = heartbeat_q[25];
    assign led[3] = protocol_error | proto_err;
    assign led[4] = overflow_err;
    assign led[5] = buf_state[0];
    assign led[6] = buf_state[1];
    assign led[7] = (stripes_sent != 16'd0);

    assign dbg_frame_start = frame_start;
    assign dbg_frame_done = frame_done;
    assign dbg_frame_active = frame_active;
    assign dbg_expected_frame_id = expected_frame_id;
    assign dbg_frame_error_count = frame_error_count;
    assign dbg_uart_bytes = uart_bytes;
    assign dbg_core_busy = core_busy;
    assign dbg_core_done = core_done;
endmodule

`default_nettype wire
