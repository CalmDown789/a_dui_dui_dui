`timescale 1ns / 1ps

// Team member B: first-layer convolution backend.

// First-layer 5x5 backend. Unlike conv5x5_backend, activation samples are
// explicitly unsigned so the input range 128..255 remains positive.
module conv5x5_u8s8_backend #(
    parameter integer ACT_W = 8,
    parameter integer WGT_W = 8,
    parameter integer ACC_W = 32,
    parameter integer CHANNELS = 1
)(
    input  wire                              clk,
    input  wire                              rst,
    input  wire                              in_valid,
    input  wire        [(25*ACT_W)-1:0]       x_flat,
    input  wire signed [(25*WGT_W)-1:0]       k_flat,
    input  wire signed [ACC_W-1:0]            bias,
    output wire signed [ACC_W-1:0]            result,
    output wire                              result_valid
);

    localparam integer DOT_W = ACT_W + WGT_W + 5;

    wire signed [DOT_W-1:0] dot25;
    wire dot25_valid;
    reg signed [ACC_W-1:0] bias_d0, bias_d1, bias_d2;
    reg signed [ACC_W-1:0] bias_d3, bias_d4, bias_d5;

    always @(posedge clk) begin
        if (rst) begin
            bias_d0<=0; bias_d1<=0; bias_d2<=0;
            bias_d3<=0; bias_d4<=0; bias_d5<=0;
        end else begin
            if (in_valid)
                bias_d0<=bias;
            bias_d1<=bias_d0;
            bias_d2<=bias_d1;
            bias_d3<=bias_d2;
            bias_d4<=bias_d3;
            bias_d5<=bias_d4;
        end
    end

    dot25_u8s8_pipeline #(
        .ACT_W(ACT_W),
        .WGT_W(WGT_W)
    ) u_dot25 (
        .clk(clk), .rst(rst), .in_valid(in_valid),
        .x_flat(x_flat), .k_flat(k_flat),
        .dot25(dot25), .dot25_valid(dot25_valid)
    );

    channel_accumulator #(
        .DOT_W(DOT_W),
        .ACC_W(ACC_W),
        .CHANNELS(CHANNELS)
    ) u_accumulator (
        .clk(clk), .rst(rst),
        .dot_valid(dot25_valid), .dot_value(dot25),
        .bias(bias_d5),
        .result(result), .result_valid(result_valid)
    );

endmodule
