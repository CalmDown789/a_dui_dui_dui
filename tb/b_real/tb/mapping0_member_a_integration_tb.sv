`timescale 1ns / 1ps
`include "mapping0_vector_counts.vh"

module mapping0_member_a_integration_tb;

    reg clk;
    reg rst;
    reg in_valid;
    reg signed [143:0] x_flat;
    reg signed [71:0] k_flat;
    reg signed [31:0] bias;
    reg signed [15:0] alpha;
    reg signed [31:0] multiplier;
    wire signed [31:0] conv_result;
    wire conv_result_valid;
    wire [15:0] post_result;
    wire post_result_valid;

    reg [215:0] contributions [0:(`MAPPING0_GROUP_COUNT*`MAPPING0_CHANNELS)-1];
    reg [127:0] groups [0:`MAPPING0_GROUP_COUNT-1];
    integer group_index;
    integer channel_index;
    integer conv_seen;
    integer post_seen;
    integer errors;
    integer timeout_count;

    conv3x3_backend #(
        .ACT_W(16), .WGT_W(8), .ACC_W(32), .CHANNELS(`MAPPING0_CHANNELS)
    ) conv_dut (
        .clk(clk), .rst(rst), .in_valid(in_valid),
        .x00(x_flat[15:0]),    .x01(x_flat[31:16]),   .x02(x_flat[47:32]),
        .x10(x_flat[63:48]),   .x11(x_flat[79:64]),   .x12(x_flat[95:80]),
        .x20(x_flat[111:96]),  .x21(x_flat[127:112]), .x22(x_flat[143:128]),
        .k00(k_flat[7:0]),     .k01(k_flat[15:8]),    .k02(k_flat[23:16]),
        .k10(k_flat[31:24]),   .k11(k_flat[39:32]),   .k12(k_flat[47:40]),
        .k20(k_flat[55:48]),   .k21(k_flat[63:56]),   .k22(k_flat[71:64]),
        .bias(bias), .result(conv_result), .result_valid(conv_result_valid)
    );

    prelu_requantize #(
        .OUT_W(16), .OUT_SIGNED(1), .APPLY_PRELU(1)
    ) post_dut (
        .clk(clk), .rst(rst), .in_valid(conv_result_valid),
        .accumulator_int32(conv_result), .prelu_q15(alpha),
        .multiplier_q31(multiplier),
        .out_data(post_result), .out_valid(post_result_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    always @(posedge clk) begin
        #1;
        if (conv_result_valid) begin
            if (conv_result !== groups[conv_seen][47:16]) begin
                $display("MAPPING0_ACCUM_MISMATCH group=%0d got=%0d expected=%0d",
                         conv_seen, conv_result, $signed(groups[conv_seen][47:16]));
                errors=errors+1;
            end
            conv_seen=conv_seen+1;
        end
        if (post_result_valid) begin
            if (post_result !== groups[post_seen][15:0]) begin
                $display("MAPPING0_POST_MISMATCH group=%0d got=%0d expected=%0d",
                         post_seen, $signed(post_result), $signed(groups[post_seen][15:0]));
                errors=errors+1;
            end
            post_seen=post_seen+1;
        end
    end

    initial begin
        $readmemh("mapping0_contributions.mem", contributions);
        $readmemh("mapping0_groups.mem", groups);
        rst=1'b1; in_valid=1'b0; x_flat=0; k_flat=0;
        bias=0; alpha=0; multiplier=0;
        group_index=0; channel_index=0; conv_seen=0; post_seen=0;
        errors=0; timeout_count=0;
        repeat (3) @(posedge clk);
        @(negedge clk); rst=1'b0;

        for (group_index=0; group_index<`MAPPING0_GROUP_COUNT; group_index=group_index+1) begin
            bias=groups[group_index][127:96];
            alpha=groups[group_index][95:80];
            multiplier=groups[group_index][79:48];
            for (channel_index=0; channel_index<`MAPPING0_CHANNELS; channel_index=channel_index+1) begin
                @(negedge clk);
                x_flat=contributions[group_index*`MAPPING0_CHANNELS+channel_index][215:72];
                k_flat=contributions[group_index*`MAPPING0_CHANNELS+channel_index][71:0];
                in_valid=1'b1;
            end
            @(negedge clk); in_valid=1'b0;
            while (post_seen <= group_index)
                @(posedge clk);
        end

        while ((post_seen < `MAPPING0_GROUP_COUNT) && (timeout_count < 40)) begin
            @(posedge clk);
            timeout_count=timeout_count+1;
        end
        if ((conv_seen != `MAPPING0_GROUP_COUNT) || (post_seen != `MAPPING0_GROUP_COUNT)) begin
            $display("MAPPING0_COUNT_MISMATCH conv=%0d post=%0d", conv_seen, post_seen);
            errors=errors+1;
        end
        if (errors == 0)
            $display("ACX750_MAPPING0_MEMBER_A_BIT_EXACT_PASS groups=%0d contributions=%0d",
                     post_seen, post_seen*`MAPPING0_CHANNELS);
        else
            $display("ACX750_MAPPING0_MEMBER_A_BIT_EXACT_FAIL errors=%0d", errors);
        #10; $finish;
    end

endmodule
