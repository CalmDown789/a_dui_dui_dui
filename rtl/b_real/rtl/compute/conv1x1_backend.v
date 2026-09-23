`timescale 1ns / 1ps

module conv1x1_backend #(
    parameter integer ACT_W = 8,
    parameter integer WGT_W = 8,
    parameter integer ACC_W = 32,
    parameter integer CHANNELS = 1
)(
    input  wire                         clk,
    input  wire                         rst,
    input  wire                         in_valid,
    input  wire signed [ACT_W-1:0]      x,
    input  wire signed [WGT_W-1:0]      k,
    input  wire signed [ACC_W-1:0]      bias,
    output wire signed [ACC_W-1:0]      result,
    output wire                         result_valid
);

    localparam integer PROD_W=ACT_W+WGT_W;
    wire signed [PROD_W-1:0] product;
    reg product_valid;
    reg signed [ACC_W-1:0] bias_d;

    dsp_signed_mult #(.A_W(ACT_W),.B_W(WGT_W)) u_mult(
        .clk(clk),.rst(rst),.enable(in_valid),.a(x),.b(k),.product(product));

    always @(posedge clk) begin
        if(rst)begin product_valid<=0;bias_d<=0;end
        else begin
            product_valid<=in_valid;
            if(in_valid)bias_d<=bias;
        end
    end

    channel_accumulator #(
        .DOT_W(PROD_W),.ACC_W(ACC_W),.CHANNELS(CHANNELS)
    ) u_accumulator(
        .clk(clk),.rst(rst),.dot_valid(product_valid),.dot_value(product),
        .bias(bias_d),.result(result),.result_valid(result_valid));
endmodule
