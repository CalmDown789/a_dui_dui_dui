`timescale 1ns/1ps
module rom_pipeline_case #(
    parameter integer W=7,H=5,AW=6,DEPTH=64,REAL_IMAGE=0,ID=0
)(output reg complete=0);
    localparam integer N=W*H;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,start_load=0,ready=0;
    wire valid,en,active,done;
    wire [7:0] data,rom_data;
    wire [AW-1:0] addr;
    wire [15:0] x,y;
    reg [7:0] golden[0:DEPTH-1];
    integer seen=0,requests=0,cycles=0,stalls=0,frames=0,resets=0,i;
    reg checking=0,held=0;
    reg [7:0] held_data;
    reg [15:0] held_x,held_y;
    reg [31:0] rng=32'h812fe43a+ID;
    integer ready_mode=0;
    input_stream #(.IMG_W(W),.IMG_H(H),.PIXEL_W(8),.ADDR_W(AW),.TOT_PIX(N)) stream(
        .clk(clk),.rst_n(rst_n),.start_load(start_load),.in_valid(valid),
        .in_data(data),.in_ready(ready),.rom_en(en),.rom_addr(addr),.rom_dout(rom_data),
        .input_active(active),.input_done(done),.dbg_x(x),.dbg_y(y));
    input_rom #(.ADDR_W(AW),.DATA_W(8),.MEM_DEPTH(DEPTH),
                .INIT_MODE(REAL_IMAGE?0:1),.INIT_EN(REAL_IMAGE)) rom(
        .clk(clk),.en(en),.addr(addr),.dout(rom_data));
    always @(negedge clk) begin
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
        case(ready_mode)
            0: ready=0;
            1: ready=1;
            default: ready=(rng[3:0]!=0) && ((cycles%997)<913);
        endcase
    end
    always @(posedge clk) begin
        cycles=cycles+1;
        if (!rst_n || start_load || !checking) held=0;
        else begin
            if (held && (!valid || data!==held_data || x!==held_x || y!==held_y))
                $fatal(1,"ROM_PIPE hold id=%0d seen=%0d",ID,seen);
            if (en) begin
                if (requests>=N || addr!==AW'(requests))
                    $fatal(1,"ROM_PIPE request order id=%0d req=%0d addr=%0d",ID,requests,addr);
                requests=requests+1;
            end
            if (valid && ready) begin
                if (seen>=N || data!==golden[seen] || x!==16'(seen%W) || y!==16'(seen/W))
                    $fatal(1,"ROM_PIPE data/coord id=%0d seen=%0d got=%02x exp=%02x x/y=%0d/%0d",ID,seen,data,golden[seen],x,y);
                seen=seen+1;
            end
            held=valid && !ready;
            if (held) begin
                held_data=data; held_x=x; held_y=y; stalls=stalls+1;
            end
        end
    end
    task automatic reset_path;
        begin
            @(negedge clk); checking=0; rst_n=0; start_load=0; ready_mode=0;
            repeat(4) @(negedge clk);
            rst_n=1; resets=resets+1;
            repeat(3) @(negedge clk);
        end
    endtask
    task automatic launch(input integer mode);
        begin
            @(negedge clk); seen=0; requests=0; held=0; checking=1;
            ready_mode=mode; start_load=1;
            @(negedge clk); start_load=0;
        end
    endtask
    task automatic full_frame(input integer mode);
        begin
            launch(mode);
            wait(done===1'b1);
            @(negedge clk);
            if (seen!=N || requests!=N || active || valid)
                $fatal(1,"ROM_PIPE completion id=%0d seen=%0d req=%0d",ID,seen,requests);
            repeat(7) begin
                @(negedge clk);
                if (!done || en || valid) $fatal(1,"ROM_PIPE done not sticky id=%0d",ID);
            end
            checking=0; frames=frames+1;
        end
    endtask
    initial begin
        if (REAL_IMAGE) $readmemh("input_rom_2p19_u8.mem",golden);
        else for(i=0;i<DEPTH;i=i+1) golden[i]=((i*7)+(i>>8)+13)&255;
        reset_path();
        // Abort while requests are in flight, before any output handshake.
        launch(0); repeat(2) @(negedge clk); reset_path();
        // Abort with a nonempty response queue under a long output stall.
        launch(0); repeat(20) @(negedge clk); reset_path();
        full_frame(1);
        full_frame(2);
        full_frame(2);
        if (frames!=3 || resets!=3 || stalls<10)
            $fatal(1,"ROM_PIPE missing coverage id=%0d",ID);
        $display("ROM_PIPELINE_CASE_PASS id=%0d W=%0d H=%0d frames=%0d pixels_each=%0d cycles=%0d stalls=%0d resets=%0d",ID,W,H,frames,N,cycles,stalls,resets);
        complete=1;
    end
    initial begin #100000000; $fatal(1,"ROM_PIPE timeout id=%0d",ID); end
endmodule
module tb_rom_pipeline;
    wire [3:0] complete;
    rom_pipeline_case #(.W(1),.H(1),.AW(1),.DEPTH(2),.ID(0)) c0(complete[0]);
    rom_pipeline_case #(.W(7),.H(5),.AW(6),.DEPTH(64),.ID(1)) c1(complete[1]);
    rom_pipeline_case #(.W(9),.H(7),.AW(6),.DEPTH(64),.ID(2)) c2(complete[2]);
    rom_pipeline_case #(.W(960),.H(540),.AW(19),.DEPTH(524288),.REAL_IMAGE(1),.ID(3)) c3(complete[3]);
    initial begin wait(&complete); $display("ROM_PIPELINE_UNIT_PASS cases=4 frames_each=3 latency_edges=3"); $finish; end
endmodule
