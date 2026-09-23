`timescale 1ns / 1ps
`ifndef TB_W
`define TB_W 6
`endif
`ifndef TB_H
`define TB_H 5
`endif

// 成员B工作 / Team member B: ROM-initialized C-B top, byte/sideband scoreboard.
module fsrcnn_network_mem_top_tb;
    localparam integer W=`TB_W,H=`TB_H,N=W*H;
    reg clk=0,rst_n=0,start=0,out_ready=0;
    always #5 clk=~clk;
    reg [7:0] input_mem[0:N-1],output_mem[0:4*N-1];
    wire busy,done,in_ready,out_valid,stripe_last,frame_last;
    wire [7:0] out_data;
    integer sent=0,received=0,cycle=0;
    integer invalid_run=0,max_invalid_run=0;
    reg held=0;
    reg [7:0] held_data;
    reg held_stripe,held_frame;
    initial begin
        $readmemh("input_u8.mem",input_mem);$readmemh("output_u8.mem",output_mem);
        repeat(3)@(negedge clk);rst_n=1;
        if(in_ready!==0)$fatal(1,"input ready before start");
        @(negedge clk);start=1;
        @(negedge clk);start=0;
        wait(received==4*N);
        @(negedge clk);
        if(sent!=N||busy||!done)$fatal(1,"completion sent=%0d busy=%b done=%b",sent,busy,done);
        $display("ACX750_MEMBER_B_ROM_TOP_BIT_EXACT_PASS size=%0dx%0d output_bytes=%0d cycles=%0d max_out_invalid_gap=%0d",W,H,4*N,cycle,max_invalid_run);
        $finish;
    end
    fsrcnn_network_mem_top #(.IMG_W(W),.IMG_H(H),.STRIPE_ROWS(64)) dut (
        .clk_200(clk),.rst_n(rst_n),.start(start),.busy(busy),.done(done),
        .in_valid(sent<N),.in_ready(in_ready),.in_data(input_mem[sent]),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),
        .stripe_last(stripe_last),.frame_last(frame_last)
    );
    always @(negedge clk)if(rst_n)begin
        cycle=cycle+1;
`ifdef TB_ALWAYS_READY
        out_ready=1;
`else
        out_ready=((cycle%17)!=3)&&((cycle%17)!=4)&&((cycle%17)!=5);
`endif
    end
    always @(posedge clk)if(rst_n)begin
        if(received>0&&received<4*N&&!out_valid)begin
            invalid_run=invalid_run+1;
            if(invalid_run>max_invalid_run)max_invalid_run=invalid_run;
        end else invalid_run=0;
        if(in_ready&&sent<N)sent=sent+1;
        if(held&&(!out_valid||out_data!==held_data||stripe_last!==held_stripe||frame_last!==held_frame))
            $fatal(1,"output changed under stall");
        held=out_valid&&!out_ready;
        if(held)begin held_data=out_data;held_stripe=stripe_last;held_frame=frame_last;end
        if(out_valid&&out_ready)begin
            if(out_data!==output_mem[received])$fatal(1,"output byte=%0d",received);
            if(frame_last!==(received==4*N-1))$fatal(1,"frame_last byte=%0d",received);
            if(stripe_last!==(((received%(2*W))==2*W-1)&&
                ((((received/(2*W)+1)%64)==0)||(received==4*N-1))))
                $fatal(1,"stripe_last byte=%0d",received);
            received=received+1;
        end
        if(cycle>24*N+2000)$fatal(1,"ROM top timeout");
    end
endmodule
