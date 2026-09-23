`timescale 1ns / 1ps

// 成员B工作 / Team member B: full 6x5 L1 window+8-phase MAC vs A tensors.
module feature_stream_member_a_tb;
    localparam integer W=6,H=5,COUT=16;
    reg clk=0,rst=1,start=0,result_ready=0;
    always #5 clk=~clk;
    reg [7:0] input_mem[0:W*H-1];
    reg [31:0] expected_mem[0:W*H*COUT-1];
    reg [25*16*8-1:0] weights_mem[0:0];
    reg [16*32-1:0] bias_mem[0:0];
    integer sent=0,received=0,cycle=0,c;
    reg held=0;
    reg [COUT*32-1:0] held_data;
    wire busy,in_ready,window_valid,window_ready,result_valid;
    wire [25*8-1:0] window_data;
    wire [COUT*32-1:0] result_data;
    initial begin
        $readmemh("input_u8.mem",input_mem);
        $readmemh("feature_raw_int32.mem",expected_mem);
        $readmemh("feature_weights_packed.mem",weights_mem);
        $readmemh("feature_bias_packed.mem",bias_mem);
        repeat(3)@(negedge clk);rst=0;
        @(negedge clk);start=1;
        @(negedge clk);start=0;
        wait(received==W*H);
        if(sent!=W*H)$fatal(1,"input count=%0d",sent);
        $display("ACX750_MEMBER_B_FEATURE_STREAM_BIT_EXACT_PASS size=6x5 outputs=480");
        $finish;
    end
    window_stream_frontend #(.DATA_W(8),.IMG_W(W),.IMG_H(H),.K(5),.FIFO_DEPTH(4)) frontend (
        .clk(clk),.rst(rst),.start(start),.busy(busy),
        .in_valid(sent<W*H),.in_ready(in_ready),.in_data(input_mem[sent]),
        .window_valid(window_valid),.window_ready(window_ready),.window_data(window_data)
    );
    mac_issue_stage #(.K(5),.CIN(1),.COUT(16),.IN_PAR(1),.OUT_PAR(2),
        .ACT_W(8),.ACT_UNSIGNED(1)) stage (
        .clk(clk),.rst(rst),.window_valid(window_valid),.window_ready(window_ready),
        .window_flat(window_data),.weight_flat(weights_mem[0]),.bias_flat(bias_mem[0]),
        .result_valid(result_valid),.result_ready(result_ready),.result_flat(result_data)
    );
    always @(negedge clk)if(!rst)begin
        cycle=cycle+1;
        result_ready=((cycle%13)!=4)&&((cycle%13)!=5)&&((cycle%13)!=6);
    end
    always @(posedge clk)if(!rst)begin
        if(in_ready&&sent<W*H)sent=sent+1;
        if(held&&(!result_valid||result_data!==held_data))
            $fatal(1,"feature result changed under stall");
        held=result_valid&&!result_ready;
        if(held)held_data=result_data;
        if(result_valid&&result_ready)begin
            for(c=0;c<COUT;c=c+1)begin
                if(result_data[c*32+:32]!==expected_mem[received*COUT+c])
                    $fatal(1,"feature pixel=%0d ch=%0d got=%0d expected=%0d",received,c,
                        $signed(result_data[c*32+:32]),$signed(expected_mem[received*COUT+c]));
            end
            received=received+1;
        end
        if(cycle>1500)$fatal(1,"feature stream timeout sent=%0d received=%0d",sent,received);
    end
endmodule
