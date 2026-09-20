`timescale 1ns / 1ps

// DSP-mapping experiment for Day 12.
// The arithmetic and interface are identical to mapping_backend_core.
// Only the USE_DSP attributes inside dot9_pipelined_dsp are different.
module mapping_backend_core_dsp #(
    parameter integer ACT_W    = 8,
    parameter integer WGT_W    = 8,
    parameter integer ACC_W    = 24,
    parameter integer CHANNELS = 12
)(
    input  wire clk,
    input  wire rst,
    input  wire in_valid,

    input  wire signed [ACT_W-1:0] x00,
    input  wire signed [ACT_W-1:0] x01,
    input  wire signed [ACT_W-1:0] x02,
    input  wire signed [ACT_W-1:0] x10,
    input  wire signed [ACT_W-1:0] x11,
    input  wire signed [ACT_W-1:0] x12,
    input  wire signed [ACT_W-1:0] x20,
    input  wire signed [ACT_W-1:0] x21,
    input  wire signed [ACT_W-1:0] x22,

    input  wire signed [WGT_W-1:0] k00,
    input  wire signed [WGT_W-1:0] k01,
    input  wire signed [WGT_W-1:0] k02,
    input  wire signed [WGT_W-1:0] k10,
    input  wire signed [WGT_W-1:0] k11,
    input  wire signed [WGT_W-1:0] k12,
    input  wire signed [WGT_W-1:0] k20,
    input  wire signed [WGT_W-1:0] k21,
    input  wire signed [WGT_W-1:0] k22,

    input  wire signed [ACC_W-1:0] bias,

    output wire signed [ACT_W+WGT_W+3:0] dot9,
    output wire                              dot9_valid,
    output wire signed [ACC_W-1:0]           result,
    output wire                              result_valid
);

    localparam integer DOT_W = ACT_W + WGT_W + 4;

    // This instance selects the synthesis-directed dot9 implementation.
    dot9_pipelined_dsp #(
        .ACT_W(ACT_W),
        .WGT_W(WGT_W)
    ) u_dot9 (
        .clk(clk),
        .rst(rst),
        .in_valid(in_valid),
        .x00(x00), .x01(x01), .x02(x02),
        .x10(x10), .x11(x11), .x12(x12),
        .x20(x20), .x21(x21), .x22(x22),
        .k00(k00), .k01(k01), .k02(k02),
        .k10(k10), .k11(k11), .k12(k12),
        .k20(k20), .k21(k21), .k22(k22),
        .dot9(dot9),
        .dot9_valid(dot9_valid)
    );

    channel12_accumulator #(
        .DOT_W(DOT_W),
        .ACC_W(ACC_W),
        .CHANNELS(CHANNELS)
    ) u_accumulator (
        .clk(clk),
        .rst(rst),
        .dot9_valid(dot9_valid),
        .dot9(dot9),
        .bias(bias),
        .result(result),
        .result_valid(result_valid)
    );

endmodule
