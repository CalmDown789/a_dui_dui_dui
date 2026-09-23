`timescale 1ns / 1ps
`include "conv1x1_counts.vh"

module conv1x1_member_a_tb;
    reg clk;
    reg rst;

    reg shrink_valid;
    reg signed [15:0] shrink_x;
    reg signed [7:0] shrink_k;
    reg signed [31:0] shrink_bias;
    reg signed [15:0] shrink_alpha;
    reg signed [31:0] shrink_multiplier;
    wire signed [31:0] shrink_accum;
    wire shrink_accum_valid;
    wire [15:0] shrink_out;
    wire shrink_out_valid;

    reg expand_valid;
    reg signed [15:0] expand_x;
    reg signed [7:0] expand_k;
    reg signed [31:0] expand_bias;
    reg signed [15:0] expand_alpha;
    reg signed [31:0] expand_multiplier;
    wire signed [31:0] expand_accum;
    wire expand_accum_valid;
    wire [15:0] expand_out;
    wire expand_out_valid;

    reg [23:0] shrink_contributions [0:(`SHRINK_GROUP_COUNT*`SHRINK_CHANNELS)-1];
    reg [127:0] shrink_groups [0:`SHRINK_GROUP_COUNT-1];
    reg [23:0] expand_contributions [0:(`EXPAND_GROUP_COUNT*`EXPAND_CHANNELS)-1];
    reg [127:0] expand_groups [0:`EXPAND_GROUP_COUNT-1];
    integer group_index;
    integer channel_index;
    integer shrink_accum_seen;
    integer shrink_out_seen;
    integer expand_accum_seen;
    integer expand_out_seen;
    integer errors;

    conv1x1_backend #(.ACT_W(16), .WGT_W(8), .ACC_W(32), .CHANNELS(`SHRINK_CHANNELS)) shrink_conv (
        .clk(clk), .rst(rst), .in_valid(shrink_valid), .x(shrink_x), .k(shrink_k),
        .bias(shrink_bias), .result(shrink_accum), .result_valid(shrink_accum_valid)
    );
    prelu_requantize #(.OUT_W(16), .OUT_SIGNED(1), .APPLY_PRELU(1)) shrink_post (
        .clk(clk), .rst(rst), .in_valid(shrink_accum_valid),
        .accumulator_int32(shrink_accum), .prelu_q15(shrink_alpha),
        .multiplier_q31(shrink_multiplier), .out_data(shrink_out), .out_valid(shrink_out_valid)
    );

    conv1x1_backend #(.ACT_W(16), .WGT_W(8), .ACC_W(32), .CHANNELS(`EXPAND_CHANNELS)) expand_conv (
        .clk(clk), .rst(rst), .in_valid(expand_valid), .x(expand_x), .k(expand_k),
        .bias(expand_bias), .result(expand_accum), .result_valid(expand_accum_valid)
    );
    prelu_requantize #(.OUT_W(16), .OUT_SIGNED(1), .APPLY_PRELU(1)) expand_post (
        .clk(clk), .rst(rst), .in_valid(expand_accum_valid),
        .accumulator_int32(expand_accum), .prelu_q15(expand_alpha),
        .multiplier_q31(expand_multiplier), .out_data(expand_out), .out_valid(expand_out_valid)
    );

    initial begin clk=0; forever #5 clk=~clk; end

    always @(posedge clk) begin
        #1;
        if (shrink_accum_valid) begin
            if (shrink_accum !== shrink_groups[shrink_accum_seen][47:16]) errors=errors+1;
            shrink_accum_seen=shrink_accum_seen+1;
        end
        if (shrink_out_valid) begin
            if (shrink_out !== shrink_groups[shrink_out_seen][15:0]) errors=errors+1;
            shrink_out_seen=shrink_out_seen+1;
        end
        if (expand_accum_valid) begin
            if (expand_accum !== expand_groups[expand_accum_seen][47:16]) errors=errors+1;
            expand_accum_seen=expand_accum_seen+1;
        end
        if (expand_out_valid) begin
            if (expand_out !== expand_groups[expand_out_seen][15:0]) errors=errors+1;
            expand_out_seen=expand_out_seen+1;
        end
    end

    initial begin
        $readmemh("shrink_contributions.mem", shrink_contributions);
        $readmemh("shrink_groups.mem", shrink_groups);
        $readmemh("expand_contributions.mem", expand_contributions);
        $readmemh("expand_groups.mem", expand_groups);
        rst=1; shrink_valid=0; shrink_x=0; shrink_k=0; shrink_bias=0; shrink_alpha=0; shrink_multiplier=0;
        expand_valid=0; expand_x=0; expand_k=0; expand_bias=0; expand_alpha=0; expand_multiplier=0;
        shrink_accum_seen=0; shrink_out_seen=0; expand_accum_seen=0; expand_out_seen=0; errors=0;
        repeat(3) @(posedge clk); @(negedge clk); rst=0;

        for(group_index=0; group_index<`SHRINK_GROUP_COUNT; group_index=group_index+1) begin
            shrink_bias=shrink_groups[group_index][127:96];
            shrink_alpha=shrink_groups[group_index][95:80];
            shrink_multiplier=shrink_groups[group_index][79:48];
            for(channel_index=0; channel_index<`SHRINK_CHANNELS; channel_index=channel_index+1) begin
                @(negedge clk);
                shrink_x=shrink_contributions[group_index*`SHRINK_CHANNELS+channel_index][23:8];
                shrink_k=shrink_contributions[group_index*`SHRINK_CHANNELS+channel_index][7:0];
                shrink_valid=1;
            end
            @(negedge clk); shrink_valid=0;
            while(shrink_out_seen<=group_index) @(posedge clk);
        end

        for(group_index=0; group_index<`EXPAND_GROUP_COUNT; group_index=group_index+1) begin
            expand_bias=expand_groups[group_index][127:96];
            expand_alpha=expand_groups[group_index][95:80];
            expand_multiplier=expand_groups[group_index][79:48];
            for(channel_index=0; channel_index<`EXPAND_CHANNELS; channel_index=channel_index+1) begin
                @(negedge clk);
                expand_x=expand_contributions[group_index*`EXPAND_CHANNELS+channel_index][23:8];
                expand_k=expand_contributions[group_index*`EXPAND_CHANNELS+channel_index][7:0];
                expand_valid=1;
            end
            @(negedge clk); expand_valid=0;
            while(expand_out_seen<=group_index) @(posedge clk);
        end

        if ((shrink_accum_seen!=`SHRINK_GROUP_COUNT) || (shrink_out_seen!=`SHRINK_GROUP_COUNT) ||
            (expand_accum_seen!=`EXPAND_GROUP_COUNT) || (expand_out_seen!=`EXPAND_GROUP_COUNT)) errors=errors+1;
        if(errors==0)
            $display("ACX750_CONV1X1_MEMBER_A_BIT_EXACT_PASS shrink=%0d expand=%0d", shrink_out_seen, expand_out_seen);
        else
            $display("ACX750_CONV1X1_MEMBER_A_BIT_EXACT_FAIL errors=%0d", errors);
        #10; $finish;
    end
endmodule
