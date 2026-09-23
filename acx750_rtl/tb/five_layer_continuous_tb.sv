`timescale 1ns / 1ps
`ifndef TB_W
`define TB_W 6
`endif
`ifndef TB_H
`define TB_H 5
`endif

// 成员B工作 / Team member B: five concurrently running RTL layers with
// four 32-token FIFOs; compare every layer token to independent A-based data.
module five_layer_continuous_tb #(
    parameter integer W=`TB_W,
    parameter integer H=`TB_H
);
    localparam integer N=W*H;
    reg clk=0,rst=1,start=0,out_ready=0;
    always #5 clk=~clk;
    reg [7:0] input_mem[0:N-1];
    reg [15:0] feature_mem[0:N*16-1],shrink_mem[0:N*8-1];
    reg [15:0] mapping_mem[0:N*8-1],expand_mem[0:N*16-1];
    reg [7:0] subpixel_mem[0:N*4-1];
    reg [7:0] output_mem[0:N*4-1];
    reg [16*1*25*8-1:0] w1[0:0];
    reg [8*16*1*8-1:0] w2[0:0];
    reg [8*8*9*8-1:0] w3[0:0];
    reg [16*8*1*8-1:0] w4[0:0];
    reg [4*16*25*8-1:0] w5[0:0];
    reg [16*32-1:0] b1[0:0],b4[0:0],q1[0:0],q4[0:0];
    reg [8*32-1:0] b2[0:0],b3[0:0],q2[0:0],q3[0:0];
    reg [4*32-1:0] b5[0:0],q5[0:0];
    reg [16*16-1:0] p1[0:0],p4[0:0];
    reg [8*16-1:0] p2[0:0],p3[0:0];
    integer sent=0,n1=0,n2=0,n3=0,n4=0,n5=0,nout=0,cycle=0,c;
    wire v1,r1,v12,r12,v2,r2,v23,r23,v3,r3,v34,r34,v4,r4,v45,r45,v5,r5;
    wire r0;
    wire [255:0] d1,d12,d4,d45;
    wire [127:0] d2,d23,d3,d34;
    wire [31:0] d5;
    wire vout,stripe_last,frame_last,shuffle_busy,shuffle_done;
    wire [7:0] dout;
    reg held=0;
    reg [7:0] held_data;
    reg held_stripe,held_frame;
    initial begin
        $readmemh("input_u8.mem",input_mem);
        $readmemh("feature_out.mem",feature_mem);
        $readmemh("shrink_out.mem",shrink_mem);
        $readmemh("mapping0_out.mem",mapping_mem);
        $readmemh("expand_out.mem",expand_mem);
        $readmemh("subpixel_out.mem",subpixel_mem);
        $readmemh("output_u8.mem",output_mem);
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
        repeat(3)@(negedge clk);rst=0;
        @(negedge clk);start=1;
        @(negedge clk);start=0;
        wait(nout==4*N);
        @(negedge clk);
        if(sent!=N||n1!=N||n2!=N||n3!=N||n4!=N||n5!=N||!shuffle_done)
            $fatal(1,"token counts or done incomplete");
        $display("ACX750_MEMBER_B_FULL_STREAM_BIT_EXACT_PASS size=%0dx%0d layer_values=%0d output_bytes=%0d",W,H,N*52,4*N);
        $finish;
    end
    fsrcnn_stream_layer #(.IMG_W(W),.IMG_H(H),.K(5),.CIN(1),.COUT(16),
        .IN_PAR(1),.OUT_PAR(2),.ACT_W(8),.ACT_UNSIGNED(1),.OUT_W(16)) l1 (
        .clk(clk),.rst(rst),.start(start),.in_valid(sent<N),.in_ready(r0),.in_pixel(input_mem[sent]),
        .weight_flat(w1[0]),.bias_flat(b1[0]),.prelu_flat(p1[0]),.q31_flat(q1[0]),
        .out_valid(v1),.out_ready(r1),.out_pixel(d1)
    );
    elastic_fifo #(.DATA_W(256),.DEPTH(32)) f12 (
        .clk(clk),.rst(rst),.in_valid(v1),.in_ready(r1),.in_data(d1),
        .out_valid(v12),.out_ready(r12),.out_data(d12),.occupancy()
    );
    fsrcnn_stream_layer #(.IMG_W(W),.IMG_H(H),.K(1),.CIN(16),.COUT(8),
        .IN_PAR(2),.OUT_PAR(8),.ACT_W(16),.ACT_UNSIGNED(0),.OUT_W(16)) l2 (
        .clk(clk),.rst(rst),.start(start),.in_valid(v12),.in_ready(r12),.in_pixel(d12),
        .weight_flat(w2[0]),.bias_flat(b2[0]),.prelu_flat(p2[0]),.q31_flat(q2[0]),
        .out_valid(v2),.out_ready(r2),.out_pixel(d2)
    );
    elastic_fifo #(.DATA_W(128),.DEPTH(32)) f23 (
        .clk(clk),.rst(rst),.in_valid(v2),.in_ready(r2),.in_data(d2),
        .out_valid(v23),.out_ready(r23),.out_data(d23),.occupancy()
    );
    fsrcnn_stream_layer #(.IMG_W(W),.IMG_H(H),.K(3),.CIN(8),.COUT(8),
        .IN_PAR(1),.OUT_PAR(8),.ACT_W(16),.ACT_UNSIGNED(0),.OUT_W(16)) l3 (
        .clk(clk),.rst(rst),.start(start),.in_valid(v23),.in_ready(r23),.in_pixel(d23),
        .weight_flat(w3[0]),.bias_flat(b3[0]),.prelu_flat(p3[0]),.q31_flat(q3[0]),
        .out_valid(v3),.out_ready(r3),.out_pixel(d3)
    );
    elastic_fifo #(.DATA_W(128),.DEPTH(32)) f34 (
        .clk(clk),.rst(rst),.in_valid(v3),.in_ready(r3),.in_data(d3),
        .out_valid(v34),.out_ready(r34),.out_data(d34),.occupancy()
    );
    fsrcnn_stream_layer #(.IMG_W(W),.IMG_H(H),.K(1),.CIN(8),.COUT(16),
        .IN_PAR(1),.OUT_PAR(16),.ACT_W(16),.ACT_UNSIGNED(0),.OUT_W(16)) l4 (
        .clk(clk),.rst(rst),.start(start),.in_valid(v34),.in_ready(r34),.in_pixel(d34),
        .weight_flat(w4[0]),.bias_flat(b4[0]),.prelu_flat(p4[0]),.q31_flat(q4[0]),
        .out_valid(v4),.out_ready(r4),.out_pixel(d4)
    );
    elastic_fifo #(.DATA_W(256),.DEPTH(32)) f45 (
        .clk(clk),.rst(rst),.in_valid(v4),.in_ready(r4),.in_data(d4),
        .out_valid(v45),.out_ready(r45),.out_data(d45),.occupancy()
    );
    fsrcnn_stream_layer #(.IMG_W(W),.IMG_H(H),.K(5),.CIN(16),.COUT(4),
        .IN_PAR(2),.OUT_PAR(4),.ACT_W(16),.ACT_UNSIGNED(0),.OUT_W(8),.APPLY_PRELU(0)) l5 (
        .clk(clk),.rst(rst),.start(start),.in_valid(v45),.in_ready(r45),.in_pixel(d45),
        .weight_flat(w5[0]),.bias_flat(b5[0]),.prelu_flat(64'b0),.q31_flat(q5[0]),
        .out_valid(v5),.out_ready(r5),.out_pixel(d5)
    );
    pixel_shuffle2x_row_banks #(.IMG_W(W),.IMG_H(H),.STRIPE_ROWS(64)) shuffle (
        .clk(clk),.rst(rst),.start(start),.busy(shuffle_busy),.done(shuffle_done),
        .in_valid(v5),.in_ready(r5),.in_phases(d5),
        .out_valid(vout),.out_ready(out_ready),.out_data(dout),
        .stripe_last(stripe_last),.frame_last(frame_last)
    );
    always @(negedge clk)if(!rst)begin
        cycle=cycle+1;
        out_ready=((cycle%19)!=4)&&((cycle%19)!=5)&&((cycle%19)!=6)&&((cycle%19)!=7);
    end
    always @(posedge clk)if(!rst)begin
        if(sent<N&&r0)sent=sent+1;
        if(v1&&r1)begin
            for(c=0;c<16;c=c+1)if(d1[c*16+:16]!==feature_mem[n1*16+c])$fatal(1,"L1 pixel=%0d ch=%0d",n1,c);
            n1=n1+1;
        end
        if(v2&&r2)begin
            for(c=0;c<8;c=c+1)if(d2[c*16+:16]!==shrink_mem[n2*8+c])$fatal(1,"L2 pixel=%0d ch=%0d",n2,c);
            n2=n2+1;
        end
        if(v3&&r3)begin
            for(c=0;c<8;c=c+1)if(d3[c*16+:16]!==mapping_mem[n3*8+c])$fatal(1,"L3 pixel=%0d ch=%0d",n3,c);
            n3=n3+1;
        end
        if(v4&&r4)begin
            for(c=0;c<16;c=c+1)if(d4[c*16+:16]!==expand_mem[n4*16+c])$fatal(1,"L4 pixel=%0d ch=%0d",n4,c);
            n4=n4+1;
        end
        if(v5&&r5)begin
            for(c=0;c<4;c=c+1)if(d5[c*8+:8]!==subpixel_mem[n5*4+c])$fatal(1,"L5 pixel=%0d phase=%0d",n5,c);
            n5=n5+1;
        end
        if(held&&(!vout||dout!==held_data||stripe_last!==held_stripe||frame_last!==held_frame))
            $fatal(1,"shuffle output changed under stall");
        held=vout&&!out_ready;
        if(held)begin held_data=dout;held_stripe=stripe_last;held_frame=frame_last;end
        if(vout&&out_ready)begin
            if(dout!==output_mem[nout])$fatal(1,"output byte=%0d got=%0d expected=%0d",nout,dout,output_mem[nout]);
            if(frame_last!==(nout==4*N-1))$fatal(1,"frame_last byte=%0d",nout);
            if(stripe_last!==(((nout%(2*W))==2*W-1)&&
                ((((nout/(2*W)+1)%64)==0)||(nout==4*N-1))))
                $fatal(1,"stripe_last byte=%0d",nout);
            nout=nout+1;
        end
        if(cycle>24*N+2000)$fatal(1,"network timeout n1=%0d n2=%0d n3=%0d n4=%0d n5=%0d out=%0d",n1,n2,n3,n4,n5,nout);
    end
endmodule
