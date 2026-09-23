`timescale 1ns / 1ps

module dot9_pipeline #(
    parameter integer ACT_W = 8,
    parameter integer WGT_W = 8
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

    (* use_dsp = "no" *) output reg signed [ACT_W+WGT_W+3:0] dot9,
    output reg                            dot9_valid
);

    localparam integer PROD_W = ACT_W + WGT_W;
    localparam integer S1_W   = PROD_W + 1;
    localparam integer S2_W   = PROD_W + 2;
    localparam integer S3_W   = PROD_W + 3;
    localparam integer DOT_W  = PROD_W + 4;

    // Conservative mapping baseline: one signed multiply per DSP48E1.
    // This does not assume or implement dual-INT8 packing.
    (* use_dsp = "yes" *) reg signed [PROD_W-1:0] p0;
    (* use_dsp = "yes" *) reg signed [PROD_W-1:0] p1;
    (* use_dsp = "yes" *) reg signed [PROD_W-1:0] p2;
    (* use_dsp = "yes" *) reg signed [PROD_W-1:0] p3;
    (* use_dsp = "yes" *) reg signed [PROD_W-1:0] p4;
    (* use_dsp = "yes" *) reg signed [PROD_W-1:0] p5;
    (* use_dsp = "yes" *) reg signed [PROD_W-1:0] p6;
    (* use_dsp = "yes" *) reg signed [PROD_W-1:0] p7;
    (* use_dsp = "yes" *) reg signed [PROD_W-1:0] p8;
    reg valid_s0;

    (* use_dsp = "no" *) reg signed [S1_W-1:0] s1_0, s1_1, s1_2, s1_3;
    reg signed [PROD_W-1:0] p8_d1;
    reg valid_s1;

    (* use_dsp = "no" *) reg signed [S2_W-1:0] s2_0, s2_1;
    reg signed [PROD_W-1:0] p8_d2;
    reg valid_s2;

    (* use_dsp = "no" *) reg signed [S3_W-1:0] s3;
    reg signed [PROD_W-1:0] p8_d3;
    reg valid_s3;

    always @(posedge clk) begin
        if (rst) begin
            p0 <= 0; p1 <= 0; p2 <= 0; p3 <= 0; p4 <= 0;
            p5 <= 0; p6 <= 0; p7 <= 0; p8 <= 0;
            valid_s0 <= 1'b0;
        end else begin
            valid_s0 <= in_valid;
            if (in_valid) begin
                p0 <= x00 * k00; p1 <= x01 * k01; p2 <= x02 * k02;
                p3 <= x10 * k10; p4 <= x11 * k11; p5 <= x12 * k12;
                p6 <= x20 * k20; p7 <= x21 * k21; p8 <= x22 * k22;
            end
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            s1_0 <= 0; s1_1 <= 0; s1_2 <= 0; s1_3 <= 0;
            p8_d1 <= 0;
            valid_s1 <= 1'b0;
        end else begin
            s1_0 <= $signed({p0[PROD_W-1], p0}) + $signed({p1[PROD_W-1], p1});
            s1_1 <= $signed({p2[PROD_W-1], p2}) + $signed({p3[PROD_W-1], p3});
            s1_2 <= $signed({p4[PROD_W-1], p4}) + $signed({p5[PROD_W-1], p5});
            s1_3 <= $signed({p6[PROD_W-1], p6}) + $signed({p7[PROD_W-1], p7});
            p8_d1 <= p8;
            valid_s1 <= valid_s0;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            s2_0 <= 0; s2_1 <= 0;
            p8_d2 <= 0;
            valid_s2 <= 1'b0;
        end else begin
            s2_0 <= $signed({s1_0[S1_W-1], s1_0}) + $signed({s1_1[S1_W-1], s1_1});
            s2_1 <= $signed({s1_2[S1_W-1], s1_2}) + $signed({s1_3[S1_W-1], s1_3});
            p8_d2 <= p8_d1;
            valid_s2 <= valid_s1;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            s3 <= 0;
            p8_d3 <= 0;
            valid_s3 <= 1'b0;
        end else begin
            s3 <= $signed({s2_0[S2_W-1], s2_0}) + $signed({s2_1[S2_W-1], s2_1});
            p8_d3 <= p8_d2;
            valid_s3 <= valid_s2;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            dot9 <= 0;
            dot9_valid <= 1'b0;
        end else begin
            dot9 <= $signed({s3[S3_W-1], s3})
                  + $signed({{(DOT_W-PROD_W){p8_d3[PROD_W-1]}}, p8_d3});
            dot9_valid <= valid_s3;
        end
    end

endmodule
