`timescale 1ns / 1ps

// Team member B: first-layer uint8 x signed-INT8 dot-product pipeline.

// Row-major flattened 5x5 dot product for the first network layer.
// Activations are unsigned because the frozen input contract is uint8 with
// zero point 0; weights are signed INT8.
module dot25_u8s8_pipeline #(
    parameter integer ACT_W = 8,
    parameter integer WGT_W = 8
)(
    input  wire                              clk,
    input  wire                              rst,
    input  wire                              in_valid,
    input  wire        [(25*ACT_W)-1:0]       x_flat,
    input  wire signed [(25*WGT_W)-1:0]       k_flat,
    (* use_dsp = "no" *) output reg signed [ACT_W+WGT_W+4:0] dot25,
    output reg                               dot25_valid
);

    localparam integer PROD_W = ACT_W + WGT_W;
    localparam integer S1_W = PROD_W + 1;
    localparam integer S2_W = PROD_W + 2;
    localparam integer S3_W = PROD_W + 3;
    localparam integer S4_W = PROD_W + 4;

    wire signed [PROD_W-1:0] products [0:24];
    genvar product_index;
    generate
        for (product_index=0; product_index<25; product_index=product_index+1) begin : g_mult
            dsp_u8s8_mult #(
                .ACT_W(ACT_W),
                .WGT_W(WGT_W)
            ) u_mult (
                .clk(clk), .rst(rst), .enable(in_valid),
                .activation(x_flat[(product_index*ACT_W) +: ACT_W]),
                .weight(k_flat[(product_index*WGT_W) +: WGT_W]),
                .product(products[product_index])
            );
        end
    endgenerate

    (* use_dsp = "no" *) reg signed [S1_W-1:0] s1 [0:11];
    (* use_dsp = "no" *) reg signed [S2_W-1:0] s2 [0:5];
    (* use_dsp = "no" *) reg signed [S3_W-1:0] s3 [0:2];
    (* use_dsp = "no" *) reg signed [S4_W-1:0] s4_0, s4_1;
    reg signed [PROD_W-1:0] p24_d1, p24_d2, p24_d3;
    reg valid_s0, valid_s1, valid_s2, valid_s3, valid_s4;

    integer i;
    always @(posedge clk) begin
        if (rst)
            valid_s0 <= 1'b0;
        else
            valid_s0 <= in_valid;
    end

    always @(posedge clk) begin
        if (rst) begin
            for (i=0; i<12; i=i+1)
                s1[i] <= 0;
            p24_d1 <= 0;
            valid_s1 <= 1'b0;
        end else begin
            for (i=0; i<12; i=i+1)
                s1[i] <= $signed({products[2*i][PROD_W-1], products[2*i]})
                       + $signed({products[2*i+1][PROD_W-1], products[2*i+1]});
            p24_d1 <= products[24];
            valid_s1 <= valid_s0;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            for (i=0; i<6; i=i+1)
                s2[i] <= 0;
            p24_d2 <= 0;
            valid_s2 <= 1'b0;
        end else begin
            for (i=0; i<6; i=i+1)
                s2[i] <= $signed({s1[2*i][S1_W-1], s1[2*i]})
                       + $signed({s1[2*i+1][S1_W-1], s1[2*i+1]});
            p24_d2 <= p24_d1;
            valid_s2 <= valid_s1;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            for (i=0; i<3; i=i+1)
                s3[i] <= 0;
            p24_d3 <= 0;
            valid_s3 <= 1'b0;
        end else begin
            for (i=0; i<3; i=i+1)
                s3[i] <= $signed({s2[2*i][S2_W-1], s2[2*i]})
                       + $signed({s2[2*i+1][S2_W-1], s2[2*i+1]});
            p24_d3 <= p24_d2;
            valid_s3 <= valid_s2;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            s4_0 <= 0;
            s4_1 <= 0;
            valid_s4 <= 1'b0;
        end else begin
            s4_0 <= $signed({s3[0][S3_W-1], s3[0]})
                  + $signed({s3[1][S3_W-1], s3[1]});
            s4_1 <= $signed({s3[2][S3_W-1], s3[2]})
                  + $signed({{(S4_W-PROD_W){p24_d3[PROD_W-1]}}, p24_d3});
            valid_s4 <= valid_s3;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            dot25 <= 0;
            dot25_valid <= 1'b0;
        end else begin
            dot25 <= $signed({s4_0[S4_W-1], s4_0})
                   + $signed({s4_1[S4_W-1], s4_1});
            dot25_valid <= valid_s4;
        end
    end

endmodule
