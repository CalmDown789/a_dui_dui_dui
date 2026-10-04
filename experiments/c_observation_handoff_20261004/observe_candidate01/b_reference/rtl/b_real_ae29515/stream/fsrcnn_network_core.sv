`timescale 1ns / 1ps

// 成员B工作 / Team member B: C-B v0.2 functional network core.
// Five independent streaming layers, four 32-token FIFOs, and two PixelShuffle
// row banks. Parameters are packed B-internal buses supplied by a ROM wrapper.
// MAC products and balanced reduction are elastic stages; postprocess uses
// 13 shared multiplier lanes. Target timing/resource mapping remains pending.
module fsrcnn_network_core #(
    parameter integer IMG_W=96,
    parameter integer IMG_H=54,
    parameter integer STRIPE_ROWS=64
)(
    input  wire               clk_200,
    input  wire               rst_n,
    input  wire               start,
    output wire               busy,
    output wire               done,
    input  wire               in_valid,
    output wire               in_ready,
    input  wire [7:0]         in_data,
    output wire               out_valid,
    input  wire               out_ready,
    output wire [7:0]         out_data,
    output wire               stripe_last,
    output wire               frame_last,
    input  wire [16*1*25*8-1:0] w1,
    input  wire [8*16*1*8-1:0]  w2,
    input  wire [8*8*9*8-1:0]   w3,
    input  wire [16*8*1*8-1:0]  w4,
    input  wire [4*16*25*8-1:0] w5,
    input  wire [16*32-1:0] b1,
    input  wire [8*32-1:0]  b2,
    input  wire [8*32-1:0]  b3,
    input  wire [16*32-1:0] b4,
    input  wire [4*32-1:0]  b5,
    input  wire [16*16-1:0] p1,
    input  wire [8*16-1:0]  p2,
    input  wire [8*16-1:0]  p3,
    input  wire [16*16-1:0] p4,
    input  wire [16*32-1:0] q1,
    input  wire [8*32-1:0]  q2,
    input  wire [8*32-1:0]  q3,
    input  wire [16*32-1:0] q4,
    input  wire [4*32-1:0]  q5
);
    wire rst=!rst_n;
    wire start_accept=start&&!busy;
    wire v1,r1,v12,r12,v2,r2,v23,r23,v3,r3,v34,r34,v4,r4,v45,r45,v5,r5;
    wire [255:0] d1,d12,d4,d45;
    wire [127:0] d2,d23,d3,d34;
    wire [31:0] d5;
    fsrcnn_stream_layer #(.IMG_W(IMG_W),.IMG_H(IMG_H),.K(5),.CIN(1),.COUT(16),
        .IN_PAR(1),.OUT_PAR(2),.ACT_W(8),.ACT_UNSIGNED(1),.OUT_W(16)) l1 (
        .clk(clk_200),.rst(rst),.start(start_accept),.in_valid(in_valid),.in_ready(in_ready),.in_pixel(in_data),
        .weight_flat(w1),.bias_flat(b1),.prelu_flat(p1),.q31_flat(q1),
        .out_valid(v1),.out_ready(r1),.out_pixel(d1)
    );
    elastic_fifo #(.DATA_W(256),.DEPTH(32)) f12 (
        .clk(clk_200),.rst(rst),.in_valid(v1),.in_ready(r1),.in_data(d1),
        .out_valid(v12),.out_ready(r12),.out_data(d12),.occupancy()
    );
    fsrcnn_stream_layer #(.IMG_W(IMG_W),.IMG_H(IMG_H),.K(1),.CIN(16),.COUT(8),
        .IN_PAR(2),.OUT_PAR(8),.ACT_W(16),.ACT_UNSIGNED(0),.OUT_W(16)) l2 (
        .clk(clk_200),.rst(rst),.start(start_accept),.in_valid(v12),.in_ready(r12),.in_pixel(d12),
        .weight_flat(w2),.bias_flat(b2),.prelu_flat(p2),.q31_flat(q2),
        .out_valid(v2),.out_ready(r2),.out_pixel(d2)
    );
    elastic_fifo #(.DATA_W(128),.DEPTH(32)) f23 (
        .clk(clk_200),.rst(rst),.in_valid(v2),.in_ready(r2),.in_data(d2),
        .out_valid(v23),.out_ready(r23),.out_data(d23),.occupancy()
    );
    fsrcnn_stream_layer #(.IMG_W(IMG_W),.IMG_H(IMG_H),.K(3),.CIN(8),.COUT(8),
        .IN_PAR(1),.OUT_PAR(8),.ACT_W(16),.ACT_UNSIGNED(0),.OUT_W(16)) l3 (
        .clk(clk_200),.rst(rst),.start(start_accept),.in_valid(v23),.in_ready(r23),.in_pixel(d23),
        .weight_flat(w3),.bias_flat(b3),.prelu_flat(p3),.q31_flat(q3),
        .out_valid(v3),.out_ready(r3),.out_pixel(d3)
    );
    elastic_fifo #(.DATA_W(128),.DEPTH(32)) f34 (
        .clk(clk_200),.rst(rst),.in_valid(v3),.in_ready(r3),.in_data(d3),
        .out_valid(v34),.out_ready(r34),.out_data(d34),.occupancy()
    );
    fsrcnn_stream_layer #(.IMG_W(IMG_W),.IMG_H(IMG_H),.K(1),.CIN(8),.COUT(16),
        .IN_PAR(1),.OUT_PAR(16),.ACT_W(16),.ACT_UNSIGNED(0),.OUT_W(16)) l4 (
        .clk(clk_200),.rst(rst),.start(start_accept),.in_valid(v34),.in_ready(r34),.in_pixel(d34),
        .weight_flat(w4),.bias_flat(b4),.prelu_flat(p4),.q31_flat(q4),
        .out_valid(v4),.out_ready(r4),.out_pixel(d4)
    );
    elastic_fifo #(.DATA_W(256),.DEPTH(32)) f45 (
        .clk(clk_200),.rst(rst),.in_valid(v4),.in_ready(r4),.in_data(d4),
        .out_valid(v45),.out_ready(r45),.out_data(d45),.occupancy()
    );
    fsrcnn_stream_layer #(.IMG_W(IMG_W),.IMG_H(IMG_H),.K(5),.CIN(16),.COUT(4),
        .IN_PAR(2),.OUT_PAR(4),.ACT_W(16),.ACT_UNSIGNED(0),.OUT_W(8),.APPLY_PRELU(0)) l5 (
        .clk(clk_200),.rst(rst),.start(start_accept),.in_valid(v45),.in_ready(r45),.in_pixel(d45),
        .weight_flat(w5),.bias_flat(b5),.prelu_flat(64'b0),.q31_flat(q5),
        .out_valid(v5),.out_ready(r5),.out_pixel(d5)
    );
    pixel_shuffle2x_row_banks #(.IMG_W(IMG_W),.IMG_H(IMG_H),
        .STRIPE_ROWS(STRIPE_ROWS)) shuffle (
        .clk(clk_200),.rst(rst),.start(start_accept),.busy(busy),.done(done),
        .in_valid(v5),.in_ready(r5),.in_phases(d5),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),
        .stripe_last(stripe_last),.frame_last(frame_last)
    );
endmodule
