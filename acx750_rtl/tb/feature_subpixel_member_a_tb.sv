`timescale 1ns / 1ps
`include "feature_subpixel_counts.vh"

module feature_subpixel_member_a_tb;

    reg clk;
    reg rst;

    reg feature_valid;
    reg [199:0] feature_x;
    reg signed [199:0] feature_k;
    reg signed [31:0] feature_bias;
    reg signed [15:0] feature_alpha;
    reg signed [31:0] feature_multiplier;
    wire signed [31:0] feature_accum;
    wire feature_accum_valid;
    wire [15:0] feature_out;
    wire feature_out_valid;

    reg sub_valid;
    reg signed [399:0] sub_x;
    reg signed [199:0] sub_k;
    reg signed [31:0] sub_bias;
    reg signed [31:0] sub_multiplier;
    wire signed [31:0] sub_accum;
    wire sub_accum_valid;
    wire [7:0] sub_out;
    wire sub_out_valid;

    reg [399:0] feature_contributions [0:`FEATURE_GROUP_COUNT-1];
    reg [127:0] feature_groups [0:`FEATURE_GROUP_COUNT-1];
    reg [599:0] sub_contributions [0:(`SUBPIXEL_GROUP_COUNT*`SUBPIXEL_CHANNELS)-1];
    reg [103:0] sub_groups [0:`SUBPIXEL_GROUP_COUNT-1];
    integer group_index;
    integer channel_index;
    integer feature_accum_seen;
    integer feature_out_seen;
    integer sub_accum_seen;
    integer sub_out_seen;
    integer errors;

    conv5x5_u8s8_backend #(
        .ACT_W(8), .WGT_W(8), .ACC_W(32), .CHANNELS(1)
    ) feature_conv (
        .clk(clk), .rst(rst), .in_valid(feature_valid),
        .x_flat(feature_x), .k_flat(feature_k), .bias(feature_bias),
        .result(feature_accum), .result_valid(feature_accum_valid)
    );
    prelu_requantize #(
        .OUT_W(16), .OUT_SIGNED(1), .APPLY_PRELU(1)
    ) feature_post (
        .clk(clk), .rst(rst), .in_valid(feature_accum_valid),
        .accumulator_int32(feature_accum), .prelu_q15(feature_alpha),
        .multiplier_q31(feature_multiplier),
        .out_data(feature_out), .out_valid(feature_out_valid)
    );

    conv5x5_backend #(
        .ACT_W(16), .WGT_W(8), .ACC_W(32), .CHANNELS(`SUBPIXEL_CHANNELS)
    ) sub_conv (
        .clk(clk), .rst(rst), .in_valid(sub_valid),
        .x_flat(sub_x), .k_flat(sub_k), .bias(sub_bias),
        .result(sub_accum), .result_valid(sub_accum_valid)
    );
    prelu_requantize #(
        .OUT_W(8), .OUT_SIGNED(0), .APPLY_PRELU(0)
    ) sub_post (
        .clk(clk), .rst(rst), .in_valid(sub_accum_valid),
        .accumulator_int32(sub_accum), .prelu_q15(16'sd0),
        .multiplier_q31(sub_multiplier),
        .out_data(sub_out), .out_valid(sub_out_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    always @(posedge clk) begin
        #1;
        if (feature_accum_valid) begin
            if (feature_accum !== feature_groups[feature_accum_seen][47:16]) begin
                $display("FEATURE_ACCUM_MISMATCH group=%0d", feature_accum_seen);
                errors=errors+1;
            end
            feature_accum_seen=feature_accum_seen+1;
        end
        if (feature_out_valid) begin
            if (feature_out !== feature_groups[feature_out_seen][15:0]) begin
                $display("FEATURE_POST_MISMATCH group=%0d", feature_out_seen);
                errors=errors+1;
            end
            feature_out_seen=feature_out_seen+1;
        end
        if (sub_accum_valid) begin
            if (sub_accum !== sub_groups[sub_accum_seen][39:8]) begin
                $display("SUBPIXEL_ACCUM_MISMATCH group=%0d", sub_accum_seen);
                errors=errors+1;
            end
            sub_accum_seen=sub_accum_seen+1;
        end
        if (sub_out_valid) begin
            if (sub_out !== sub_groups[sub_out_seen][7:0]) begin
                $display("SUBPIXEL_POST_MISMATCH group=%0d", sub_out_seen);
                errors=errors+1;
            end
            sub_out_seen=sub_out_seen+1;
        end
    end

    initial begin
        $readmemh("feature_contributions.mem", feature_contributions);
        $readmemh("feature_groups.mem", feature_groups);
        $readmemh("subpixel_contributions.mem", sub_contributions);
        $readmemh("subpixel_groups.mem", sub_groups);
        rst=1'b1;
        feature_valid=0; feature_x=0; feature_k=0; feature_bias=0; feature_alpha=0; feature_multiplier=0;
        sub_valid=0; sub_x=0; sub_k=0; sub_bias=0; sub_multiplier=0;
        feature_accum_seen=0; feature_out_seen=0; sub_accum_seen=0; sub_out_seen=0; errors=0;
        repeat (3) @(posedge clk);
        @(negedge clk); rst=1'b0;

        for (group_index=0; group_index<`FEATURE_GROUP_COUNT; group_index=group_index+1) begin
            feature_bias=feature_groups[group_index][127:96];
            feature_alpha=feature_groups[group_index][95:80];
            feature_multiplier=feature_groups[group_index][79:48];
            @(negedge clk);
            feature_x=feature_contributions[group_index][399:200];
            feature_k=feature_contributions[group_index][199:0];
            feature_valid=1'b1;
            @(negedge clk); feature_valid=1'b0;
            while (feature_out_seen <= group_index)
                @(posedge clk);
        end

        for (group_index=0; group_index<`SUBPIXEL_GROUP_COUNT; group_index=group_index+1) begin
            sub_bias=sub_groups[group_index][103:72];
            sub_multiplier=sub_groups[group_index][71:40];
            for (channel_index=0; channel_index<`SUBPIXEL_CHANNELS; channel_index=channel_index+1) begin
                @(negedge clk);
                sub_x=sub_contributions[group_index*`SUBPIXEL_CHANNELS+channel_index][599:200];
                sub_k=sub_contributions[group_index*`SUBPIXEL_CHANNELS+channel_index][199:0];
                sub_valid=1'b1;
            end
            @(negedge clk); sub_valid=1'b0;
            while (sub_out_seen <= group_index)
                @(posedge clk);
        end

        if ((feature_accum_seen != `FEATURE_GROUP_COUNT) || (feature_out_seen != `FEATURE_GROUP_COUNT) ||
            (sub_accum_seen != `SUBPIXEL_GROUP_COUNT) || (sub_out_seen != `SUBPIXEL_GROUP_COUNT)) begin
            $display("FEATURE_SUBPIXEL_COUNT_MISMATCH");
            errors=errors+1;
        end
        if (errors == 0)
            $display("ACX750_FEATURE_SUBPIXEL_MEMBER_A_BIT_EXACT_PASS feature=%0d subpixel=%0d",
                     feature_out_seen, sub_out_seen);
        else
            $display("ACX750_FEATURE_SUBPIXEL_MEMBER_A_BIT_EXACT_FAIL errors=%0d", errors);
        #10; $finish;
    end

endmodule
