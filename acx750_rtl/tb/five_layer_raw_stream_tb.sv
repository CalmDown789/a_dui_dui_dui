`timescale 1ns / 1ps

// 成员B工作 / Team member B: all five full 6x5 raw-INT32 layer streams.
// Each layer is independently fed with A-asset-based golden activations.
// Interlayer postprocessing/FIFOs are not connected in this test.
module raw_stream_case #(
    parameter integer ID=1,K=5,CIN=1,COUT=16,IN_PAR=1,OUT_PAR=2,
    parameter integer ACT_W=8,ACT_UNSIGNED=1,
    parameter INPUT_FILE="input_u8.mem",
    parameter RAW_FILE="feature_raw_int32.mem",
    parameter WEIGHT_FILE="feature_weights_packed.mem",
    parameter BIAS_FILE="feature_bias_packed.mem"
)(input wire clk,input wire rst,output reg done);
    localparam integer W=6,H=5;
    reg start=0,result_ready=0;
    reg [ACT_W-1:0] input_mem[0:W*H*CIN-1];
    reg [31:0] expected_mem[0:W*H*COUT-1];
    reg [COUT*CIN*K*K*8-1:0] weights_mem[0:0];
    reg [COUT*32-1:0] bias_mem[0:0];
    reg [CIN*ACT_W-1:0] source_pixel;
    wire in_ready,window_valid,window_ready,result_valid;
    wire [K*K*CIN*ACT_W-1:0] window_data;
    wire [COUT*32-1:0] result_data;
    wire busy;
    integer sent=0,received=0,cycle=0,c;
    reg held=0;
    reg [COUT*32-1:0] held_data;
    integer ix;
    always @*begin
        source_pixel=0;
        if(sent<W*H)
            for(ix=0;ix<CIN;ix=ix+1)
                source_pixel[ix*ACT_W+:ACT_W]=input_mem[sent*CIN+ix];
    end
    initial begin
        done=0;
        $readmemh(INPUT_FILE,input_mem);
        $readmemh(RAW_FILE,expected_mem);
        $readmemh(WEIGHT_FILE,weights_mem);
        $readmemh(BIAS_FILE,bias_mem);
        wait(!rst);
        @(negedge clk);start=1;
        @(negedge clk);start=0;
    end
    generate if(K==1)begin:g1
        assign busy=0;
        assign window_valid=(sent<W*H);
        assign in_ready=window_ready;
        assign window_data=source_pixel;
    end else begin:gk
        window_stream_frontend #(.DATA_W(CIN*ACT_W),.IMG_W(W),.IMG_H(H),
            .K(K),.FIFO_DEPTH(4)) frontend (
            .clk(clk),.rst(rst),.start(start),.busy(busy),
            .in_valid(sent<W*H),.in_ready(in_ready),.in_data(source_pixel),
            .window_valid(window_valid),.window_ready(window_ready),
            .window_data(window_data)
        );
    end endgenerate
    mac_issue_stage #(.K(K),.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),
        .OUT_PAR(OUT_PAR),.ACT_W(ACT_W),.ACT_UNSIGNED(ACT_UNSIGNED)) stage (
        .clk(clk),.rst(rst),.window_valid(window_valid),.window_ready(window_ready),
        .window_flat(window_data),.weight_flat(weights_mem[0]),.bias_flat(bias_mem[0]),
        .result_valid(result_valid),.result_ready(result_ready),.result_flat(result_data)
    );
    always @(negedge clk)if(!rst&&!done)begin
        cycle=cycle+1;
        result_ready=((cycle%13)!=4)&&((cycle%13)!=5)&&((cycle%13)!=6);
    end
    always @(posedge clk)if(!rst&&!done)begin
        if(sent<W*H&&in_ready)sent=sent+1;
        if(held&&(!result_valid||result_data!==held_data))
            $fatal(1,"L%0d result changed under stall",ID);
        held=result_valid&&!result_ready;
        if(held)held_data=result_data;
        if(result_valid&&result_ready)begin
            for(c=0;c<COUT;c=c+1)
                if(result_data[c*32+:32]!==expected_mem[received*COUT+c])
                    $fatal(1,"L%0d pixel=%0d ch=%0d got=%0d expected=%0d",ID,received,c,
                        $signed(result_data[c*32+:32]),$signed(expected_mem[received*COUT+c]));
            received=received+1;
            if(received==W*H)begin
                if(sent!=W*H)$fatal(1,"L%0d input count=%0d",ID,sent);
                done<=1;
            end
        end
        if(cycle>1800)$fatal(1,"L%0d timeout sent=%0d received=%0d",ID,sent,received);
    end
endmodule

module five_layer_raw_stream_tb;
    reg clk=0,rst=1;
    always #5 clk=~clk;
    wire d1,d2,d3,d4,d5;
    raw_stream_case #(.ID(1),.K(5),.CIN(1),.COUT(16),.IN_PAR(1),.OUT_PAR(2),
        .ACT_W(8),.ACT_UNSIGNED(1),.INPUT_FILE("input_u8.mem"),.RAW_FILE("feature_raw_int32.mem"),
        .WEIGHT_FILE("feature_weights_packed.mem"),.BIAS_FILE("feature_bias_packed.mem")) l1(.clk(clk),.rst(rst),.done(d1));
    raw_stream_case #(.ID(2),.K(1),.CIN(16),.COUT(8),.IN_PAR(2),.OUT_PAR(8),
        .ACT_W(16),.ACT_UNSIGNED(0),.INPUT_FILE("feature_out.mem"),.RAW_FILE("shrink_raw_int32.mem"),
        .WEIGHT_FILE("shrink_weights_packed.mem"),.BIAS_FILE("shrink_bias_packed.mem")) l2(.clk(clk),.rst(rst),.done(d2));
    raw_stream_case #(.ID(3),.K(3),.CIN(8),.COUT(8),.IN_PAR(1),.OUT_PAR(8),
        .ACT_W(16),.ACT_UNSIGNED(0),.INPUT_FILE("shrink_out.mem"),.RAW_FILE("mapping0_raw_int32.mem"),
        .WEIGHT_FILE("mapping0_weights_packed.mem"),.BIAS_FILE("mapping0_bias_packed.mem")) l3(.clk(clk),.rst(rst),.done(d3));
    raw_stream_case #(.ID(4),.K(1),.CIN(8),.COUT(16),.IN_PAR(1),.OUT_PAR(16),
        .ACT_W(16),.ACT_UNSIGNED(0),.INPUT_FILE("mapping0_out.mem"),.RAW_FILE("expand_raw_int32.mem"),
        .WEIGHT_FILE("expand_weights_packed.mem"),.BIAS_FILE("expand_bias_packed.mem")) l4(.clk(clk),.rst(rst),.done(d4));
    raw_stream_case #(.ID(5),.K(5),.CIN(16),.COUT(4),.IN_PAR(2),.OUT_PAR(4),
        .ACT_W(16),.ACT_UNSIGNED(0),.INPUT_FILE("expand_out.mem"),.RAW_FILE("subpixel_raw_int32.mem"),
        .WEIGHT_FILE("subpixel_weights_packed.mem"),.BIAS_FILE("subpixel_bias_packed.mem")) l5(.clk(clk),.rst(rst),.done(d5));
    initial begin
        repeat(3)@(negedge clk);rst=0;
        wait(d1&&d2&&d3&&d4&&d5);
        $display("ACX750_MEMBER_B_FIVE_LAYER_RAW_STREAM_BIT_EXACT_PASS size=6x5 values=1560");
        $finish;
    end
endmodule
