`timescale 1ns / 1ps

// 成员B工作 / Team member B: small-frame handshake and padding regression.
module pad_case #(
    parameter integer PAD = 2
)(input wire clk, input wire rst, output reg done);
    localparam integer W=4, H=3, PW=W+2*PAD, PH=H+2*PAD;
    reg start, out_ready;
    reg [7:0] source_count;
    wire busy, in_ready, out_valid, out_last;
    wire [7:0] out_data;
    integer cycle, received, x, y, expected;
    reg held;
    reg [7:0] held_data;
    reg held_last;

    same_pad_raster #(.DATA_W(8),.IMG_W(W),.IMG_H(H),.PAD(PAD)) dut (
        .clk(clk),.rst(rst),.start(start),.busy(busy),
        .in_valid(1'b1),.in_ready(in_ready),.in_data(source_count+8'd1),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),
        .out_last(out_last)
    );

    initial begin
        start=0; out_ready=0; source_count=0; done=0;
        cycle=0; received=0; held=0;
        wait(!rst);
        @(negedge clk); start=1;
        @(negedge clk); start=0;
    end
    always @(negedge clk) begin
        if (!rst && !done) begin
            cycle=cycle+1;
            out_ready=((cycle % 7) != 2) && ((cycle % 7) != 3);
        end
    end
    always @(posedge clk) begin
        if (!rst && !done) begin
            if (held && (!out_valid || out_data !== held_data || out_last !== held_last))
                $fatal(1,"pad=%0d output changed during stall",PAD);
            held = out_valid && !out_ready;
            if (held) begin held_data=out_data; held_last=out_last; end
            if (out_valid && out_ready) begin
                x=received % PW; y=received / PW;
                expected=0;
                if (x>=PAD && x<PAD+W && y>=PAD && y<PAD+H)
                    expected=(y-PAD)*W+(x-PAD)+1;
                if (out_data !== expected[7:0])
                    $fatal(1,"pad=%0d index=%0d got=%0d expected=%0d",PAD,received,out_data,expected);
                if (out_last !== (received==PW*PH-1))
                    $fatal(1,"pad=%0d last mismatch index=%0d",PAD,received);
                received=received+1;
                if (received==PW*PH) done<=1;
            end
            if (in_ready) source_count<=source_count+1'b1;
            if (cycle>500) $fatal(1,"pad=%0d timeout",PAD);
        end
    end
    final begin
        if (done && source_count!=W*H)
            $fatal(1,"pad=%0d source count=%0d",PAD,source_count);
    end
endmodule

module stream_control_tb;
    reg clk=0, rst=1;
    always #5 clk=~clk;
    wire done0,done1,done2;
    pad_case #(.PAD(0)) p0(.clk(clk),.rst(rst),.done(done0));
    pad_case #(.PAD(1)) p1(.clk(clk),.rst(rst),.done(done1));
    pad_case #(.PAD(2)) p2(.clk(clk),.rst(rst),.done(done2));

    reg in_valid=0, out_ready=0;
    reg [15:0] in_data=0;
    wire in_ready,out_valid;
    wire [15:0] out_data;
    integer cycle=0, sent=0, received=0;
    reg fifo_done=0;
    reg held=0;
    reg [15:0] held_data;
    elastic_fifo #(.DATA_W(16),.DEPTH(3)) fifo (
        .clk(clk),.rst(rst),.in_valid(in_valid),.in_ready(in_ready),
        .in_data(in_data),.out_valid(out_valid),.out_ready(out_ready),.out_data(out_data)
    );
    initial begin
        repeat(3) @(negedge clk);
        rst=0;
        wait(done0 && done1 && done2 && fifo_done);
        $display("ACX750_MEMBER_B_STREAM_CONTROL_PASS pad=0/1/2 fifo=3");
        $finish;
    end
    always @(negedge clk) begin
        if (!rst && !fifo_done) begin
            cycle=cycle+1;
            in_valid=(sent<40) && ((cycle%5)!=1);
            in_data=16'h4000+sent;
            out_ready=((cycle%7)!=2) && ((cycle%7)!=3);
        end
    end
    always @(posedge clk) begin
        if (!rst && !fifo_done) begin
            if (held && (!out_valid || out_data !== held_data))
                $fatal(1,"FIFO output changed during stall");
            held=out_valid && !out_ready;
            if (held) held_data=out_data;
            if (out_valid && out_ready) begin
                if (out_data !== (16'h4000+received))
                    $fatal(1,"FIFO index=%0d got=%h",received,out_data);
                received=received+1;
                if(received==40) fifo_done<=1;
            end
            if(in_valid && in_ready) sent=sent+1;
            if(cycle>500) $fatal(1,"FIFO timeout");
        end
    end
endmodule
