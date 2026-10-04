`timescale 1ns/1ps
`default_nettype none
module tb_c_input_bank16;
    localparam integer TOTAL=960*540;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0, start_load=0, stream_mode=0;
    reg manual_en=0, wr_en=0;
    reg [18:0] manual_addr=0, wr_addr=0;
    reg [7:0] wr_data=0;
    wire stream_en; wire [18:0] stream_addr;
    wire [7:0] dout, data; wire valid, active, done;
    wire [15:0] x,y;
    reg ready=0;
    integer cycles=0, accepted=0, seed=0, tail_stalls=0;
    integer a,b,f;
    reg held=0; reg [7:0] held_data; reg [15:0] held_x,held_y;
    wire read_en=stream_mode?stream_en:manual_en;
    wire [18:0] read_addr=stream_mode?stream_addr:manual_addr;

    function [7:0] pattern;
        input integer addr; input integer frame;
        begin pattern=((addr*7)+(addr>>8)+13+frame*37)&255; end
    endfunction
    input_rom #(.ADDR_W(19),.DATA_W(8),.MEM_DEPTH(524288),.INIT_MODE(0),.INIT_EN(0)) rom
        (.clk(clk),.en(read_en),.addr(read_addr),.wr_en(wr_en),.wr_addr(wr_addr),.wr_data(wr_data),.dout(dout));
    input_stream #(.IMG_W(960),.IMG_H(540),.PIXEL_W(8),.ADDR_W(19),.TOT_PIX(TOTAL)) stream
        (.clk(clk),.rst_n(rst_n),.start_load(start_load),.in_valid(valid),.in_data(data),.in_ready(ready),
         .rom_en(stream_en),.rom_addr(stream_addr),.rom_dout(dout),.input_active(active),.input_done(done),.dbg_x(x),.dbg_y(y));
    always @(negedge clk) begin
        if(stream_mode && accepted==TOTAL-1 && tail_stalls>0) begin
            ready=0;tail_stalls=tail_stalls-1;
        end else ready=(cycles%7>=3);
    end
    always @(posedge clk) begin
        cycles=cycles+1;
        if(stream_mode && rst_n) begin
            if(wr_en) $fatal(1,"write during stream");
            if(stream_en && stream_addr>=TOTAL) $fatal(1,"read beyond final pixel");
            if(held && (!valid || data!==held_data || x!==held_x || y!==held_y))
                $fatal(1,"data/coordinates changed under backpressure");
            held=valid&&!ready; held_data=data;held_x=x;held_y=y;
            if(valid&&ready) begin
                if(accepted>=TOTAL || data!==pattern(accepted,seed) || x!==accepted%960 || y!==accepted/960)
                    $fatal(1,"stream mismatch seed=%0d index=%0d got=%02x x=%0d y=%0d",seed,accepted,data,x,y);
                accepted=accepted+1;
            end
        end else held=0;
        if(cycles%500000==0) $display("PROGRESS cycles=%0d seed=%0d accepted=%0d active=%0d done=%0d",cycles,seed,accepted,active,done);
        if(cycles>=5000000) $fatal(1,"unit simulation timeout seed=%0d accepted=%0d",seed,accepted);
    end
    task check_address;
        input integer addr;
        reg [7:0] before;
        begin
            @(negedge clk);manual_addr=addr;manual_en=1;
            @(negedge clk);
            if(dout!==pattern(addr,seed)) $fatal(1,"bank/address mismatch seed=%0d address=%0d got=%02x",seed,addr,dout);
            manual_en=0;before=dout;
            repeat(3) begin
                @(negedge clk);manual_addr=(manual_addr+32768)&524287;
                if(dout!==before) $fatal(1,"ROM changed with read enable low");
            end
        end
    endtask
    initial begin
        repeat(5) @(negedge clk);rst_n=1;
        for(f=0;f<2;f=f+1) begin
            seed=f;stream_mode=0;accepted=0;
            for(a=0;a<524288;a=a+1) begin
                @(negedge clk);wr_en=1;wr_addr=a;wr_data=pattern(a,seed);
            end
            @(negedge clk);wr_en=0;
            for(b=0;b<16;b=b+1) begin
                check_address(b*32768);check_address(b*32768+1);
                check_address(b*32768+32766);check_address(b*32768+32767);
            end
            check_address(518399);
            $display("BANK_BOUNDARIES_PASS seed=%0d banks=16 boundaries=65",seed);
            @(negedge clk);stream_mode=1;start_load=1;tail_stalls=5;
            @(negedge clk);start_load=0;
            wait(done);@(negedge clk);
            if(accepted!=TOTAL || active || valid) $fatal(1,"frame completion mismatch accepted=%0d",accepted);
            stream_mode=0;
            $display("INPUT_FRAME_PASS seed=%0d accepted=%0d no_reset=1",seed,accepted);
        end
        $display("RESULT: PASS bank16 writes, boundaries, full-size reads, backpressure, two frames without reset");
        $finish;
    end
endmodule
`default_nettype wire
