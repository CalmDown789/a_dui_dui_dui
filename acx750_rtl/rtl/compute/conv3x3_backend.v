`timescale 1ns / 1ps

module conv3x3_backend #(
    parameter integer ACT_W    = 8,
    parameter integer WGT_W    = 8,
    parameter integer ACC_W    = 32,
    parameter integer CHANNELS = 1
)(
    input  wire clk,
    input  wire rst,
    input  wire in_valid,

    input  wire signed [ACT_W-1:0] x00, x01, x02,
    input  wire signed [ACT_W-1:0] x10, x11, x12,
    input  wire signed [ACT_W-1:0] x20, x21, x22,
    input  wire signed [WGT_W-1:0] k00, k01, k02,
    input  wire signed [WGT_W-1:0] k10, k11, k12,
    input  wire signed [WGT_W-1:0] k20, k21, k22,
    input  wire signed [ACC_W-1:0] bias,

    output wire signed [ACC_W-1:0] result,
    output wire                    result_valid
);

    localparam integer DOT_W = ACT_W + WGT_W + 4;

    wire signed [DOT_W-1:0] dot9;
    wire dot9_valid;

    // dot9 becomes visible after five registered arithmetic stages. Bias is
    // delayed by the same number of input-to-output stages so consecutive
    // groups may carry different bias values without relying on a stable port.
    reg signed [ACC_W-1:0] bias_d0, bias_d1, bias_d2, bias_d3, bias_d4;

    always @(posedge clk) begin
        if (rst) begin
            bias_d0 <= 0; bias_d1 <= 0; bias_d2 <= 0;
            bias_d3 <= 0; bias_d4 <= 0;
        end else begin
            if (in_valid)
                bias_d0 <= bias;
            bias_d1 <= bias_d0;
            bias_d2 <= bias_d1;
            bias_d3 <= bias_d2;
            bias_d4 <= bias_d3;
        end
    end

    dot9_pipeline #(
        .ACT_W(ACT_W),
        .WGT_W(WGT_W)
    ) u_dot9 (
        .clk(clk), .rst(rst), .in_valid(in_valid),
        .x00(x00), .x01(x01), .x02(x02),
        .x10(x10), .x11(x11), .x12(x12),
        .x20(x20), .x21(x21), .x22(x22),
        .k00(k00), .k01(k01), .k02(k02),
        .k10(k10), .k11(k11), .k12(k12),
        .k20(k20), .k21(k21), .k22(k22),
        .dot9(dot9), .dot9_valid(dot9_valid)
    );

    channel_accumulator #(
        .DOT_W(DOT_W),
        .ACC_W(ACC_W),
        .CHANNELS(CHANNELS)
    ) u_accumulator (
        .clk(clk), .rst(rst),
        .dot_valid(dot9_valid),
        .dot_value(dot9),
        .bias(bias_d4),
        .result(result),
        .result_valid(result_valid)
    );

endmodule
