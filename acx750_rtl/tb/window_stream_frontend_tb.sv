`timescale 1ns / 1ps

// 成员B工作 / Team member B: full backpressure through padded BRAM window.
module window_stream_case #(
    parameter integer K=5
)(input wire clk,input wire rst,output reg done);
    localparam integer W=6,H=5,P=(K-1)/2;
    reg start=0,window_ready=0;
    reg [7:0] source_count=0;
    wire busy,in_ready,window_valid;
    wire [K*K*8-1:0] window_data;
    integer cycle=0,outputs=0,local_output,oy,ox,ky,kx,iy,ix,expected,tap;
    reg held=0;
    reg [K*K*8-1:0] held_window;
    window_stream_frontend #(.DATA_W(8),.IMG_W(W),.IMG_H(H),.K(K),.FIFO_DEPTH(3)) dut (
        .clk(clk),.rst(rst),.start(start),.busy(busy),
        .in_valid(1'b1),.in_ready(in_ready),.in_data(source_count+8'd1),
        .window_valid(window_valid),.window_ready(window_ready),.window_data(window_data)
    );
    initial begin
        done=0;wait(!rst);
        @(negedge clk);start=1;
        @(negedge clk);start=0;
        wait(outputs==W*H);
        wait(!busy);
        @(negedge clk);source_count=0;start=1;
        @(negedge clk);start=0;
    end
    always @(negedge clk)if(!rst&&!done)begin
        cycle=cycle+1;
        window_ready=(cycle%8==0) && !(cycle>=60&&cycle<90);
    end
    always @(posedge clk)if(!rst&&!done)begin
        if(in_ready)source_count<=source_count+1'b1;
        if(held&&(!window_valid||window_data!==held_window))
            $fatal(1,"K=%0d window changed while stalled",K);
        held=window_valid&&!window_ready;
        if(held)held_window=window_data;
        if(window_valid&&window_ready)begin
            local_output=outputs%(W*H);
            oy=local_output/W;ox=local_output%W;
            for(ky=0;ky<K;ky=ky+1)for(kx=0;kx<K;kx=kx+1)begin
                iy=oy+ky-P;ix=ox+kx-P;
                expected=0;
                if(iy>=0&&iy<H&&ix>=0&&ix<W)expected=iy*W+ix+1;
                tap=window_data[(ky*K+kx)*8+:8];
                if(tap!=expected)
                    $fatal(1,"K=%0d out=%0d tap=(%0d,%0d) got=%0d expected=%0d",K,outputs,ky,kx,tap,expected);
            end
            outputs=outputs+1;
            if(outputs==2*W*H)done<=1;
        end
        if(cycle>1600)$fatal(1,"K=%0d timeout outputs=%0d",K,outputs);
    end
endmodule

module window_stream_frontend_tb;
    reg clk=0,rst=1;
    always #5 clk=~clk;
    wire done3,done5;
    window_stream_case #(.K(3)) c3(.clk(clk),.rst(rst),.done(done3));
    window_stream_case #(.K(5)) c5(.clk(clk),.rst(rst),.done(done5));
    initial begin
        repeat(3)@(negedge clk);rst=0;
        wait(done3&&done5);
        $display("ACX750_MEMBER_B_WINDOW_STREAM_PASS k3/k5 size=6x5 frames=2 depth=3");
        $finish;
    end
endmodule
