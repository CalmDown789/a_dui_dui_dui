`timescale 1ns / 1ps
`ifndef TB_W
`define TB_W 6
`endif
`ifndef TB_H
`define TB_H 5
`endif

// 成员B工作 / Team member B: C-B v0.2 top-level bit-exact and handshake.
module fsrcnn_network_core_tb;
    localparam integer W=`TB_W,H=`TB_H,N=W*H;
    reg clk=0,rst_n=0,start=0,out_ready=0;
    always #5 clk=~clk;
    reg [7:0] input_mem[0:N-1],output_mem[0:4*N-1];
    reg [16*1*25*8-1:0] w1[0:0];reg [8*16*8-1:0] w2[0:0];
    reg [8*8*9*8-1:0] w3[0:0];reg [16*8*8-1:0] w4[0:0];
    reg [4*16*25*8-1:0] w5[0:0];
    reg [16*32-1:0] b1[0:0],b4[0:0],q1[0:0],q4[0:0];
    reg [8*32-1:0] b2[0:0],b3[0:0],q2[0:0],q3[0:0];
    reg [4*32-1:0] b5[0:0],q5[0:0];
    reg [16*16-1:0] p1[0:0],p4[0:0];
    reg [8*16-1:0] p2[0:0],p3[0:0];
    wire busy,done,in_ready,out_valid,stripe_last,frame_last;
    wire [7:0] out_data;
    integer sent=0,received=0,cycle=0;
    reg held=0;
    reg [7:0] held_data;
    reg held_stripe,held_frame;
    initial begin
        $readmemh("input_u8.mem",input_mem);$readmemh("output_u8.mem",output_mem);
        $readmemh("feature_weights_packed.mem",w1);$readmemh("feature_bias_packed.mem",b1);
        $readmemh("feature_prelu_packed.mem",p1);$readmemh("feature_q31_packed.mem",q1);
        $readmemh("shrink_weights_packed.mem",w2);$readmemh("shrink_bias_packed.mem",b2);
        $readmemh("shrink_prelu_packed.mem",p2);$readmemh("shrink_q31_packed.mem",q2);
        $readmemh("mapping0_weights_packed.mem",w3);$readmemh("mapping0_bias_packed.mem",b3);
        $readmemh("mapping0_prelu_packed.mem",p3);$readmemh("mapping0_q31_packed.mem",q3);
        $readmemh("expand_weights_packed.mem",w4);$readmemh("expand_bias_packed.mem",b4);
        $readmemh("expand_prelu_packed.mem",p4);$readmemh("expand_q31_packed.mem",q4);
        $readmemh("subpixel_weights_packed.mem",w5);$readmemh("subpixel_bias_packed.mem",b5);
        $readmemh("subpixel_q31_packed.mem",q5);
        repeat(3)@(negedge clk);rst_n=1;
        if(in_ready!==0)$fatal(1,"input ready before start");
        @(negedge clk);start=1;
        @(negedge clk);start=0;
        if(!busy)$fatal(1,"busy not asserted after start");
        wait(received==4*N);
        @(negedge clk);
        if(!done||busy||sent!=N)$fatal(1,"completion mismatch sent=%0d busy=%b done=%b",sent,busy,done);
        $display("ACX750_MEMBER_B_NETWORK_CORE_BIT_EXACT_PASS size=%0dx%0d output_bytes=%0d",W,H,4*N);
        $finish;
    end
    fsrcnn_network_core #(.IMG_W(W),.IMG_H(H),.STRIPE_ROWS(64)) dut (
        .clk_200(clk),.rst_n(rst_n),.start(start),.busy(busy),.done(done),
        .in_valid(sent<N),.in_ready(in_ready),.in_data(input_mem[sent]),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),
        .stripe_last(stripe_last),.frame_last(frame_last),
        .w1(w1[0]),.w2(w2[0]),.w3(w3[0]),.w4(w4[0]),.w5(w5[0]),
        .b1(b1[0]),.b2(b2[0]),.b3(b3[0]),.b4(b4[0]),.b5(b5[0]),
        .p1(p1[0]),.p2(p2[0]),.p3(p3[0]),.p4(p4[0]),
        .q1(q1[0]),.q2(q2[0]),.q3(q3[0]),.q4(q4[0]),.q5(q5[0])
    );
    always @(negedge clk)if(rst_n)begin
        cycle=cycle+1;
        out_ready=((cycle%19)!=4)&&((cycle%19)!=5)&&((cycle%19)!=6);
        if(cycle==25)start=1;
        if(cycle==26)start=0;
    end
    always @(posedge clk)if(rst_n)begin
        if(in_ready&&sent<N)sent=sent+1;
        if(held&&(!out_valid||out_data!==held_data||stripe_last!==held_stripe||frame_last!==held_frame))
            $fatal(1,"top output changed under stall");
        held=out_valid&&!out_ready;
        if(held)begin held_data=out_data;held_stripe=stripe_last;held_frame=frame_last;end
        if(out_valid&&out_ready)begin
            if(out_data!==output_mem[received])$fatal(1,"output byte=%0d got=%0d expected=%0d",received,out_data,output_mem[received]);
            if(frame_last!==(received==4*N-1))$fatal(1,"frame_last index=%0d",received);
            if(stripe_last!==(((received%(2*W))==2*W-1)&&
                ((((received/(2*W)+1)%64)==0)||(received==4*N-1))))
                $fatal(1,"stripe_last index=%0d",received);
            received=received+1;
        end
        if(cycle>24*N+2000)$fatal(1,"top timeout sent=%0d received=%0d",sent,received);
    end
endmodule
