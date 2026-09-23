`timescale 1ns / 1ps

// 成员B工作 / Team member B: real five-layer B core inside C's c_core.
// C modules are loaded from an isolated copy of the supplied ZIP.
module member_b_c_core_real_integration_tb;
    localparam integer W=6,H=5,N=W*H,OUT_N=4*N,STRIPE_H=4;
    reg clk=0,rst_n=0,start=0,rb_enable=0;
    always #5 clk=~clk;
    reg [7:0] golden[0:OUT_N-1];
    wire busy,done,uart_tx,proto_err,overflow_err,in_done,b_busy,b_done_seen;
    wire [1:0] buf_state;
    wire [15:0] stripe_cnt,stripes_sent,in_x,in_y,out_x,out_y;
    wire [31:0] uart_bytes;
    integer input_count=0,output_count=0,cycles=0,stall_cycles=0;
    integer frame,frame_byte;
    integer consecutive_stall=0,max_consecutive_stall=0;
    reg held=0;
    reg [7:0] held_data;
    reg held_stripe,held_frame;

    c_core #(
        .IMG_W(W),.IMG_H(H),.OUT_W(2*W),.OUT_H(2*H),
        .STRIPE_H(STRIPE_H),.PIXEL_W(8),
        .ROM_ADDR_W(5),.ROM_DEPTH(32),
        .ROM_INIT_MODE(0),.ROM_INIT_EN(1),
        .ROM_INIT_FILE("input_u8.mem"),
        .CLK_HZ(1_000_000),.UART_BAUD(100_000)
    ) dut (
        .clk(clk),.rst_n(rst_n),.start(start),.busy(busy),.done(done),
        .rb_enable(rb_enable),.uart_tx(uart_tx),
        .dbg_buf_state(buf_state),.dbg_stripe_cnt(stripe_cnt),
        .dbg_uart_bytes(uart_bytes),.dbg_stripes_sent(stripes_sent),
        .dbg_proto_err(proto_err),.dbg_overflow_err(overflow_err),
        .dbg_in_done(in_done),.dbg_b_busy(b_busy),
        .dbg_b_done_seen(b_done_seen),
        .dbg_in_x(in_x),.dbg_in_y(in_y),.dbg_out_x(out_x),.dbg_out_y(out_y)
    );

    initial begin
        $readmemh("output_u8.mem",golden);
        repeat(4)@(negedge clk);rst_n=1;
        for(frame=0;frame<2;frame=frame+1)begin
            @(negedge clk);start=1;
            @(negedge clk);start=0;
            wait(done);
            @(negedge clk);
            if(input_count!=(frame+1)*N||output_count!=(frame+1)*OUT_N)
                $fatal(1,"frame=%0d transfer totals input=%0d output=%0d",frame,input_count,output_count);
            if(proto_err||overflow_err)
                $fatal(1,"C errors protocol=%b overflow=%b",proto_err,overflow_err);
            if(stripe_cnt!=3)
                $fatal(1,"C stripe count=%0d",stripe_cnt);
            wait(uart_bytes==(frame+1)*OUT_N);
            repeat(3)@(negedge clk);
            if(stripes_sent!=(frame+1)*3)
                $fatal(1,"C UART stripe count=%0d",stripes_sent);
        end
        if(max_consecutive_stall<5000)
            $fatal(1,"long C output stall not exercised: %0d",max_consecutive_stall);
        $display("ACX750_MEMBER_B_C_CORE_REAL_PASS size=%0dx%0d frames=2 bytes=%0d max_stall=%0d",W,H,2*OUT_N,max_consecutive_stall);
        $finish;
    end

    // Fill both C banks, then delay UART draining to force sustained
    // backpressure through PixelShuffle and all five B layers.
    always @(negedge clk)if(rst_n&&cycles==12000)rb_enable=1;

    always @(posedge clk)if(rst_n)begin
        cycles=cycles+1;
        if(cycles>100000)$fatal(1,"C+B integration timeout in=%0d out=%0d uart=%0d",input_count,output_count,uart_bytes);
        if(dut.in_valid&&dut.in_ready)input_count=input_count+1;
        if(held&&(!dut.b_out_valid||dut.b_out_data!==held_data||
                 dut.b_stripe_last!==held_stripe||dut.b_frame_last!==held_frame))
            $fatal(1,"B output changed during C backpressure");
        held=dut.b_out_valid&&!dut.out_ready;
        if(held)begin
            stall_cycles=stall_cycles+1;
            consecutive_stall=consecutive_stall+1;
            if(consecutive_stall>max_consecutive_stall)
                max_consecutive_stall=consecutive_stall;
            held_data=dut.b_out_data;
            held_stripe=dut.b_stripe_last;
            held_frame=dut.b_frame_last;
        end else consecutive_stall=0;
        if(dut.b_out_valid&&dut.out_ready)begin
            frame_byte=output_count%OUT_N;
            if(dut.b_out_data!==golden[frame_byte])
                $fatal(1,"C+B output mismatch at %0d got=%h expected=%h",output_count,dut.b_out_data,golden[frame_byte]);
            if(dut.b_frame_last!==(frame_byte==OUT_N-1))
                $fatal(1,"frame marker at %0d",output_count);
            if(dut.b_stripe_last!==((((frame_byte/(2*W)+1)%STRIPE_H)==0&&
                frame_byte%(2*W)==2*W-1)||(frame_byte==OUT_N-1)))
                $fatal(1,"stripe marker at %0d",output_count);
            output_count=output_count+1;
        end
    end
endmodule
