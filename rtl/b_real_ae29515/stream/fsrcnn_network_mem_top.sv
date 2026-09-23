`timescale 1ns / 1ps

// 成员B工作 / Team member B: C-B v0.2 top with packed parameter init files.
// File names refer to member A's audited integers repacked by member B's
// generate_small_network_golden.py. ROM banking/resource mapping is pending.
module fsrcnn_network_mem_top #(
    parameter integer IMG_W=96,
    parameter integer IMG_H=54,
    parameter integer STRIPE_ROWS=64
)(
    input  wire       clk_200,
    input  wire       rst_n,
    input  wire       start,
    output wire       busy,
    output wire       done,
    input  wire       in_valid,
    output wire       in_ready,
    input  wire [7:0] in_data,
    output wire       out_valid,
    input  wire       out_ready,
    output wire [7:0] out_data,
    output wire       stripe_last,
    output wire       frame_last
);
    reg [16*1*25*8-1:0] w1[0:0];
    reg [8*16*8-1:0] w2[0:0];
    reg [8*8*9*8-1:0] w3[0:0];
    reg [16*8*8-1:0] w4[0:0];
    reg [4*16*25*8-1:0] w5[0:0];
    reg [16*32-1:0] b1[0:0],b4[0:0],q1[0:0],q4[0:0];
    reg [8*32-1:0] b2[0:0],b3[0:0],q2[0:0],q3[0:0];
    reg [4*32-1:0] b5[0:0],q5[0:0];
    reg [16*16-1:0] p1[0:0],p4[0:0];
    reg [8*16-1:0] p2[0:0],p3[0:0];
    initial begin
        $readmemh("feature_weights_packed.mem",w1);$readmemh("feature_bias_packed.mem",b1);
        $readmemh("feature_prelu_packed.mem",p1);$readmemh("feature_q31_packed.mem",q1);
        $readmemh("shrink_weights_packed.mem",w2);$readmemh("shrink_bias_packed.mem",b2);
        $readmemh("shrink_prelu_packed.mem",p2);$readmemh("shrink_q31_packed.mem",q2);
        $readmemh("mapping0_weights_packed.mem",w3);$readmemh("mapping0_bias_packed.mem",b3);
        $readmemh("mapping0_prelu_packed.mem",p3);$readmemh("mapping0_q31_packed.mem",q3);
        $readmemh("expand_weights_packed.mem",w4);$readmemh("expand_bias_packed.mem",b4);
        $readmemh("expand_prelu_packed.mem",p4);$readmemh("expand_q31_packed.mem",q4);
        $readmemh("subpixel_weights_packed.mem",w5);$readmemh("subpixel_bias_packed.mem",b5);
        $readmemh("subpixel_q31_packed.mem",q5);
    end
    fsrcnn_network_core #(.IMG_W(IMG_W),.IMG_H(IMG_H),
        .STRIPE_ROWS(STRIPE_ROWS)) core (
        .clk_200(clk_200),.rst_n(rst_n),.start(start),.busy(busy),.done(done),
        .in_valid(in_valid),.in_ready(in_ready),.in_data(in_data),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),
        .stripe_last(stripe_last),.frame_last(frame_last),
        .w1(w1[0]),.w2(w2[0]),.w3(w3[0]),.w4(w4[0]),.w5(w5[0]),
        .b1(b1[0]),.b2(b2[0]),.b3(b3[0]),.b4(b4[0]),.b5(b5[0]),
        .p1(p1[0]),.p2(p2[0]),.p3(p3[0]),.p4(p4[0]),
        .q1(q1[0]),.q2(q2[0]),.q3(q3[0]),.q4(q4[0]),.q5(q5[0])
    );
endmodule
