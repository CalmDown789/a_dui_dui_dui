`timescale 1ns / 1ps

module dsp_signed_mult #(
    parameter integer A_W = 8,
    parameter integer B_W = 8
)(
    input  wire                         clk,
    input  wire                         rst,
    input  wire                         enable,
    input  wire signed [A_W-1:0]        a,
    input  wire signed [B_W-1:0]        b,
    (* use_dsp = "yes" *) output reg signed [(A_W+B_W)-1:0] product
);

    always @(posedge clk) begin
        if (rst)
            product <= 0;
        else if (enable)
            product <= a * b;
    end

endmodule
