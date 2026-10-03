`timescale 1ns/1ps
module issue_head_case #(parameter integer DW=6400,ID=0)(output reg complete=0);
    reg clk=0;always #2.5 clk=~clk;
    reg rst=1,ready=0;
    reg [31:0] rng=32'h89a4837c+ID;
    reg [1:0] source_valid=0;
    wire [1:0] source_ready,output_valid,last_phase;
    wire [DW-1:0] source_data[0:1],output_data[0:1];
    wire [2:0] phase[0:1];
    integer sent[0:1],received[0:1],stalls[0:1],wraps[0:1];
    integer cycles=0,epoch=0,round=0,n;
    reg [1:0] held=0;
    reg [DW-1:0] held_data[0:1];
    reg [2:0] held_phase[0:1];
    function automatic [DW-1:0] pattern(input integer token,input integer generation);
        integer bit_index;
        reg [31:0] value;
        begin
            for(bit_index=0;bit_index<DW;bit_index=bit_index+1) begin
                value=(32'h9e3779b9*(token+1)) ^ (32'h5e239a17*(bit_index/32+1)) ^ generation;
                pattern[bit_index]=value[bit_index%32];
            end
        end
    endfunction
    assign source_data[0]=pattern(sent[0],epoch);
    assign source_data[1]=pattern(sent[1],epoch);
    eight_phase_issue_reference #(.DATA_W(DW)) old(.clk(clk),.rst(rst),
        .in_valid(source_valid[0]),.in_ready(source_ready[0]),.in_window(source_data[0]),
        .out_valid(output_valid[0]),.out_ready(ready),.out_window(output_data[0]),
        .out_phase(phase[0]),.out_last_phase(last_phase[0]));
    eight_phase_issue #(.DATA_W(DW)) dut(.clk(clk),.rst(rst),
        .in_valid(source_valid[1]),.in_ready(source_ready[1]),.in_window(source_data[1]),
        .out_valid(output_valid[1]),.out_ready(ready),.out_window(output_data[1]),
        .out_phase(phase[1]),.out_last_phase(last_phase[1]));
    always @(negedge clk) begin
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
        ready=(rng[3:0]!=0) && ((cycles%97)<71);
        if(rst) source_valid=0;
        else for(n=0;n<2;n=n+1) if(!source_valid[n] && sent[n]<64 && rng[5+n]) source_valid[n]=1;
    end
    always @(posedge clk) begin
        cycles=cycles+1;
        if(rst) begin
            held=0;
            for(integer p=0;p<2;p=p+1) begin sent[p]=0; received[p]=0; end
        end else begin
            for(integer p=0;p<2;p=p+1) begin
                if(held[p] && (!output_valid[p] || output_data[p]!==held_data[p] || phase[p]!==held_phase[p]))
                    $fatal(1,"ISSUE_HEAD output hold ID=%0d side=%0d",ID,p);
                if(output_valid[p] && ready) begin
                    if(received[p]>=512 || output_data[p]!==pattern(received[p]/8,epoch) ||
                       phase[p]!==3'(received[p]%8) || last_phase[p]!==(received[p]%8==7))
                        $fatal(1,"ISSUE_HEAD sequence ID=%0d side=%0d sample=%0d phase=%0d",ID,p,received[p],phase[p]);
                    if(phase[p]==7) wraps[p]=wraps[p]+1;
                    received[p]=received[p]+1;
                end
                held[p]=output_valid[p] && !ready;
                if(held[p]) begin held_data[p]=output_data[p];held_phase[p]=phase[p];stalls[p]=stalls[p]+1;end
                // Nonblocking producer updates avoid races with the DUT at this edge.
                if(source_valid[p] && source_ready[p]) begin
                    sent[p]<=sent[p]+1; source_valid[p]<=0;
                end
            end
        end
    end
    initial begin
        for(integer p=0;p<2;p=p+1) begin sent[p]=0;received[p]=0;stalls[p]=0;wraps[p]=0;end
        repeat(4) @(negedge clk);rst=0;
        // Reset under mid-window activity; both streams restart at token/phase zero.
        repeat(37) @(negedge clk);rst=1;epoch=epoch+1;
        repeat(4) @(negedge clk);rst=0;
        for(round=0;round<3;round=round+1) begin
            wait(received[0]==512 && received[1]==512);
            @(negedge clk);
            if(sent[0]!=64 || sent[1]!=64) $fatal(1,"ISSUE_HEAD input consumption mismatch");
            if(round<2) begin rst=1;epoch=epoch+1;repeat(4) @(negedge clk);rst=0;end
        end
        if(stalls[0]==0 || stalls[1]==0 || wraps[0]<192 || wraps[1]<192)
            $fatal(1,"ISSUE_HEAD coverage missing");
        $display("ISSUE_HEAD_CASE_PASS id=%0d width=%0d rounds=3 windows_each=64 samples_each=512 cycles=%0d old_stalls=%0d new_stalls=%0d",ID,DW,cycles,stalls[0],stalls[1]);
        complete=1;
    end
    initial begin #2000000;$fatal(1,"ISSUE_HEAD timeout ID=%0d",ID);end
endmodule
module tb_issue_head;
    wire [2:0] complete;
    issue_head_case #(.DW(1),.ID(0)) c0(complete[0]);
    issue_head_case #(.DW(256),.ID(1)) c1(complete[1]);
    issue_head_case #(.DW(6400),.ID(2)) c2(complete[2]);
    initial begin wait(&complete);$display("ISSUE_HEAD_UNIT_PASS cases=3 rounds_each=3");$finish;end
endmodule
