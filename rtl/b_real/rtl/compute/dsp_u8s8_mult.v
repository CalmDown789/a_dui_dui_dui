`timescale 1ns / 1ps

// Team member B: first-layer unsigned-activation DSP primitive.

// First-layer multiplier for the frozen model contract:
// uint8 activation (zero point 0) times signed INT8 weight.
module dsp_u8s8_mult #(
    parameter integer ACT_W = 8,
    parameter integer WGT_W = 8
)(
    input  wire                              clk,
    input  wire                              rst,
    input  wire                              enable,
    input  wire        [ACT_W-1:0]            activation,
    input  wire signed [WGT_W-1:0]            weight,
    (* use_dsp = "yes" *) output reg signed [(ACT_W+WGT_W)-1:0] product
);

    // The leading zero prevents uint8 values 128..255 from being interpreted
    // as negative. The mathematical uint8*sint8 range still fits in 16 bits.
    wire signed [ACT_W:0] activation_signed;
    assign activation_signed = $signed({1'b0, activation});

    always @(posedge clk) begin
        if (rst)
            product <= 0;
        else if (enable)
            product <= activation_signed * weight;
    end

endmodule
