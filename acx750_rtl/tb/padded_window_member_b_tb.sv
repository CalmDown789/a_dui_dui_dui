`timescale 1ns / 1ps

// 成员B工作 / Team member B: verify SAME-pad output against BRAM windows.
module padded_window_case #(
    parameter integer K = 5
)(input wire clk, input wire rst, output reg done);
    localparam integer W=6,H=5,P=(K-1)/2,PW=W+2*P;
    reg start=0;
    reg out_ready=0;
    reg [7:0] source_count=0;
    wire busy,in_ready,pad_valid,pad_last;
    wire [7:0] pad_data;
    wire [K*K*8-1:0] window_flat;
    wire window_valid;
    wire pad_fire=pad_valid&&out_ready;
    integer cycle=0,outputs=0, oy,ox,ky,kx,iy,ix,expected,tap;

    same_pad_raster #(.DATA_W(8),.IMG_W(W),.IMG_H(H),.PAD(P)) pad (
        .clk(clk),.rst(rst),.start(start),.busy(busy),
        .in_valid(1'b1),.in_ready(in_ready),.in_data(source_count+8'd1),
        .out_valid(pad_valid),.out_ready(out_ready),.out_data(pad_data),.out_last(pad_last)
    );
    generate if(K==5) begin:g5
        window5x5_bram #(.DATA_W(8),.IMG_W(PW)) win (
            .clk(clk),.rst(rst),.pixel_in(pad_data),.pixel_valid(pad_fire),
            .window_flat(window_flat),.window_valid(window_valid)
        );
    end else begin:g3
        window3x3_bram #(.DATA_W(8),.IMG_W(PW)) win (
            .clk(clk),.rst(rst),.pixel_in(pad_data),.pixel_valid(pad_fire),
            .w00(window_flat[0+:8]),.w01(window_flat[8+:8]),.w02(window_flat[16+:8]),
            .w10(window_flat[24+:8]),.w11(window_flat[32+:8]),.w12(window_flat[40+:8]),
            .w20(window_flat[48+:8]),.w21(window_flat[56+:8]),.w22(window_flat[64+:8]),
            .window_valid(window_valid)
        );
    end endgenerate

    initial begin
        done=0;
        wait(!rst);
        @(negedge clk);start=1;
        @(negedge clk);start=0;
    end
    always @(negedge clk) begin
        if(!rst && !done) begin
            cycle=cycle+1;
            out_ready=((cycle%9)!=3)&&((cycle%9)!=4)&&((cycle%9)!=5);
        end
    end
    always @(posedge clk) begin
        if(!rst && !done) begin
            if(in_ready)source_count<=source_count+1'b1;
            if(window_valid)begin
                oy=outputs/W;ox=outputs%W;
                for(ky=0;ky<K;ky=ky+1)begin
                    for(kx=0;kx<K;kx=kx+1)begin
                        iy=oy+ky-P;ix=ox+kx-P;
                        expected=0;
                        if(iy>=0 && iy<H && ix>=0 && ix<W)
                            expected=iy*W+ix+1;
                        tap=window_flat[((ky*K+kx)*8)+:8];
                        if(tap!=expected)
                            $fatal(1,"K=%0d out=%0d tap=(%0d,%0d) got=%0d want=%0d",K,outputs,ky,kx,tap,expected);
                    end
                end
                outputs=outputs+1;
                if(outputs==W*H)done<=1;
            end
            if(cycle>700)$fatal(1,"K=%0d timeout outputs=%0d",K,outputs);
        end
    end
endmodule

module padded_window_member_b_tb;
    reg clk=0,rst=1;
    always #5 clk=~clk;
    wire done3,done5;
    padded_window_case #(.K(3)) c3(.clk(clk),.rst(rst),.done(done3));
    padded_window_case #(.K(5)) c5(.clk(clk),.rst(rst),.done(done5));
    initial begin
        repeat(3)@(negedge clk);
        rst=0;
        wait(done3 && done5);
        $display("ACX750_MEMBER_B_PADDED_WINDOW_PASS k3/k5 size=6x5");
        $finish;
    end
endmodule
