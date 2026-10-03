`timescale 1ns/1ps
module pad_flag_case #(parameter W=7, H=5, P=2, ID=1)(input wire clk, output reg done=0);
    reg rst=1, start=0, in_valid=0, out_ready=0;
    reg [15:0] in_data=0;
    wire a_busy,a_ready,a_valid,a_last,b_busy,b_ready,b_valid,b_last;
    wire [15:0] a_data,b_data;
    integer cycles=0,frames=0,stalls=0,resets=0;
    reg accepted=0;
    reg [31:0] rng=32'h76543210 ^ ID;
    same_pad_raster #(.DATA_W(16),.IMG_W(W),.IMG_H(H),.PAD(P)) dut (
        .clk(clk),.rst(rst),.start(start),.busy(a_busy),.in_valid(in_valid),
        .in_ready(a_ready),.in_data(in_data),.out_valid(a_valid),
        .out_ready(out_ready),.out_data(a_data),.out_last(a_last));
    same_pad_raster_reference #(.DATA_W(16),.IMG_W(W),.IMG_H(H),.PAD(P)) ref_dut (
        .clk(clk),.rst(rst),.start(start),.busy(b_busy),.in_valid(in_valid),
        .in_ready(b_ready),.in_data(in_data),.out_valid(b_valid),
        .out_ready(out_ready),.out_data(b_data),.out_last(b_last));
    always @(posedge clk) begin
        accepted = in_valid && a_ready;
        if (!rst && !done) begin
            if ({a_busy,a_ready,a_valid,a_last,a_data} !==
                {b_busy,b_ready,b_valid,b_last,b_data})
                $fatal(1,"PAD_FLAG_EQUIVALENCE_FAIL id=%0d cycle=%0d",ID,cycles);
            if (a_valid && !out_ready) stalls=stalls+1;
            if (a_valid && out_ready && a_last) frames=frames+1;
        end
    end
    initial begin
        repeat(3) @(negedge clk);
        rst=0;
        while(frames<3) begin
            @(negedge clk);
            cycles=cycles+1;
            rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
            rst=(cycles==192 || cycles==705);
            if(rst) begin
                resets=resets+1;
                in_valid=0; start=0;
            end else begin
                // A start while busy is deliberately covered and must be ignored.
                start=(!a_busy) || (cycles%347==0);
                if(!in_valid || accepted) begin
                    in_valid=(rng[1:0]!=0);
                    in_data=rng[31:16]^cycles;
                end
            end
            out_ready=(rng[3:2]!=0) && !(cycles%1000>=400 && cycles%1000<470);
            if(cycles>12000000) $fatal(1,"PAD_FLAG_UNIT_TIMEOUT id=%0d",ID);
        end
        if(stalls==0) $fatal(1,"PAD_FLAG_UNIT_MISSING_STALL id=%0d",ID);
        $display("PAD_FLAG_CASE_PASS id=%0d W=%0d H=%0d PAD=%0d cycles=%0d frames=%0d stalls=%0d resets=%0d",
                  ID,W,H,P,cycles,frames,stalls,resets);
        done=1;
    end
endmodule
module tb_pad_flags;
    reg clk=0;
    always #2.5 clk=~clk;
    wire [3:0] done;
    pad_flag_case #(.W(7),.H(5),.P(2),.ID(1)) a(clk,done[0]);
    pad_flag_case #(.W(1),.H(1),.P(1),.ID(2)) b(clk,done[1]);
    pad_flag_case #(.W(9),.H(7),.P(0),.ID(3)) c(clk,done[2]);
    pad_flag_case #(.W(960),.H(540),.P(2),.ID(4)) d(clk,done[3]);
    initial begin
        wait(&done);
        $display("PAD_FLAG_REFERENCE_EQUIVALENCE_PASS cases=4 frames_each=3");
        $finish;
    end
endmodule
