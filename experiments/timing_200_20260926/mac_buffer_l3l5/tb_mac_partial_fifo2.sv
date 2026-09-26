`timescale 1ns / 1ps
`default_nettype none

// Independent front-pop/append-tail model. It does not reproduce the DUT's
// circular address pointers. Each case checks all phase and partial bits.
module mac_partial_fifo2_case #(
    parameter integer ID=3,
    parameter integer OUT_PAR=8
)(input wire clk, output reg done=1'b0);
    localparam integer DATA_W=3+OUT_PAR*32;
    reg rst=1, in_valid=0, out_ready=0;
    reg [DATA_W-1:0] in_data=0;
    wire in_ready,out_valid;
    wire [DATA_W-1:0] out_data;
    wire [1:0] occupancy;
    mac_partial_fifo2 #(.DATA_W(DATA_W)) dut (
        .clk(clk),.rst(rst),.in_valid(in_valid),.in_ready(in_ready),
        .in_data(in_data),.out_valid(out_valid),.out_ready(out_ready),
        .out_data(out_data),.occupancy(occupancy)
    );

    reg [DATA_W-1:0] expected[0:1];
    integer size=0, next_token=1, cycles=0, pushes=0, pops=0, discarded=0;
    integer full_pop_blocks_input=0, simultaneous=0, max_steady_run=0;
    integer steady_run=0, full_stalls=0, held_checks=0, input_hold_checks=0;
    integer reset_full=0, reset_partial=0, reset_pending=0, reset_valid=0;
    integer append_stalled=0, empty_push=0, random_cycles=0;
    reg source_pending=0, output_hold=0;
    reg [DATA_W-1:0] source_word,held_word;
    reg [31:0] random_state=32'h579bef13^ID;
    integer j;

    function automatic [31:0] xorshift(input [31:0] value);
        reg [31:0] x;
        begin
            x=value^(value<<13);
            x=x^(x>>17);
            xorshift=x^(x<<5);
        end
    endfunction

    function automatic [DATA_W-1:0] make_word(input integer token);
        reg [31:0] x;
        integer lane;
        begin
            x=32'h92f037ac^token^ID;
            for(lane=0;lane<OUT_PAR;lane=lane+1)begin
                x=xorshift(x);
                make_word[lane*32+:32]=x;
            end
            make_word[31:0]=token;
            make_word[OUT_PAR*32+:3]=token[2:0];
        end
    endfunction

    task automatic check_outputs;
        begin
            if(occupancy!==size[1:0])
                $fatal(1,"occupancy id=%0d cycle=%0d expected=%0d got=%0d",ID,cycles,size,occupancy);
            if(in_ready!==(size<2))
                $fatal(1,"ready must depend only on registered count id=%0d cycle=%0d size=%0d out_ready=%b",ID,cycles,size,out_ready);
            if(out_valid!==(size!=0))
                $fatal(1,"out_valid id=%0d cycle=%0d expected size=%0d",ID,cycles,size);
            if((size!=0)&&(out_data!==expected[0]))
                $fatal(1,"data/phase/X id=%0d cycle=%0d expected=%h got=%h",ID,cycles,expected[0],out_data);
        end
    endtask

    task automatic drive_cycle(input reg reset_now,
                               input reg want_input,
                               input reg ready_now);
        reg take_in,take_out,pending_before;
        integer old_size;
        begin
            @(negedge clk);
            pending_before=source_pending;
            rst=reset_now;
            out_ready=ready_now;
            if(reset_now)begin
                // Reset is also tested while the source presents valid data.
                in_valid=want_input;
                in_data=source_pending?source_word:make_word(next_token);
            end else if(source_pending)begin
                in_valid=1;
                in_data=source_word;
            end else begin
                in_valid=want_input;
                in_data=make_word(next_token);
            end
            #1;
            if(!reset_now)begin
                check_outputs();
                if(pending_before)begin
                    if(!in_valid||(in_data!==source_word))
                        $fatal(1,"test source violated input hold id=%0d cycle=%0d",ID,cycles);
                    input_hold_checks=input_hold_checks+1;
                end
                if(output_hold)begin
                    if(!out_valid||(out_data!==held_word))
                        $fatal(1,"output not held id=%0d cycle=%0d",ID,cycles);
                    held_checks=held_checks+1;
                end
            end
            old_size=size;
            take_in=!reset_now&&in_valid&&in_ready;
            take_out=!reset_now&&out_valid&&out_ready;
            if(!reset_now&&(size==2)&&in_valid&&!out_ready)
                full_stalls=full_stalls+1;
            if(!reset_now&&(size==2)&&in_valid&&out_ready)begin
                if(in_ready)$fatal(1,"full pop incorrectly enables input id=%0d",ID);
                full_pop_blocks_input=full_pop_blocks_input+1;
            end
            output_hold=!reset_now&&out_valid&&!out_ready;
            if(output_hold)held_word=out_data;

            @(posedge clk);
            cycles=cycles+1;
            if(reset_now)begin
                if(size==2)reset_full=reset_full+1;
                if(size==1)reset_partial=reset_partial+1;
                if(pending_before)reset_pending=reset_pending+1;
                if(in_valid)reset_valid=reset_valid+1;
                discarded=discarded+size;
                size=0;
                source_pending=0;
                output_hold=0;
                steady_run=0;
                next_token=next_token+1;
            end else begin
                if(take_in&&take_out)begin
                    simultaneous=simultaneous+1;
                    steady_run=steady_run+1;
                    if(steady_run>max_steady_run)max_steady_run=steady_run;
                end else steady_run=0;
                if((old_size==0)&&take_in)empty_push=empty_push+1;
                if((old_size!=0)&&!out_ready&&take_in)append_stalled=append_stalled+1;
                if(take_out)begin
                    expected[0]=expected[1];
                    size=size-1;
                    pops=pops+1;
                end
                if(take_in)begin
                    if(size>=2)$fatal(1,"scoreboard overflow id=%0d",ID);
                    expected[size]=in_data;
                    size=size+1;
                    pushes=pushes+1;
                    next_token=next_token+1;
                    source_pending=0;
                end else if(in_valid)begin
                    source_pending=1;
                    source_word=in_data;
                end
            end
            #1;
            check_outputs();
        end
    endtask

    initial begin
        repeat(2)drive_cycle(1,0,0);
        repeat(4)drive_cycle(0,0,1);
        // Explicit partially occupied reset, with valid high at reset.
        drive_cycle(0,1,0);
        drive_cycle(1,1,0);
        repeat(3)drive_cycle(0,0,1);
        repeat(2)drive_cycle(0,1,0);
        repeat(5)drive_cycle(0,1,0);
        // Full + pop must reject input once; occupancy one then runs each cycle.
        repeat(24)drive_cycle(0,1,1);
        repeat(40)drive_cycle(0,1,0);
        repeat(8)drive_cycle(0,0,1);
        repeat(2)drive_cycle(0,1,0);
        drive_cycle(0,1,0); // Establish blocked source while FIFO is full.
        drive_cycle(1,1,0);
        repeat(6)drive_cycle(0,0,1);
        repeat(20)begin
            repeat(2)drive_cycle(0,1,0);
            repeat(2)drive_cycle(0,0,1);
        end
        for(j=0;j<1600;j=j+1)begin
            random_state=xorshift(random_state);
            if((j%293)==292)drive_cycle(1,random_state[0],0);
            else begin
                random_cycles=random_cycles+1;
                drive_cycle(0,random_state[0]|random_state[1],
                             ((j%131)<23)?1'b0:random_state[2]);
            end
        end
        repeat(12)drive_cycle(0,0,1);
        if(size!=0||out_valid||source_pending)$fatal(1,"final drain incomplete id=%0d",ID);
        if(pushes!=pops+discarded)$fatal(1,"token conservation failed id=%0d",ID);
        if(pushes<100||pops<100||full_pop_blocks_input==0||simultaneous<20||
           max_steady_run<20||full_stalls<5||held_checks<40||input_hold_checks<40||
           reset_full==0||reset_partial==0||reset_pending==0||reset_valid<2||
           append_stalled==0||empty_push<20||random_cycles<1500)
            $fatal(1,"required coverage missing id=%0d",ID);
        $display("MAC_L3L5_CONFIG_PASS id=%0d width=%0d cycles=%0d pushes=%0d pops=%0d discarded=%0d full_pop_blocked=%0d simultaneous=%0d max_steady_run=%0d full_stalls=%0d out_holds=%0d in_holds=%0d reset_full=%0d reset_partial=%0d reset_pending=%0d reset_valid=%0d append_stalled=%0d empty_push=%0d random_cycles=%0d",
                 ID,DATA_W,cycles,pushes,pops,discarded,full_pop_blocks_input,
                 simultaneous,max_steady_run,full_stalls,held_checks,input_hold_checks,
                 reset_full,reset_partial,reset_pending,reset_valid,append_stalled,
                 empty_push,random_cycles);
        done=1;
    end
endmodule

module tb_mac_partial_fifo2;
    reg clk=0;
    always #5 clk=~clk;
    wire [1:0] done;
    mac_partial_fifo2_case #(.ID(3),.OUT_PAR(8)) l3 (.clk(clk),.done(done[0]));
    mac_partial_fifo2_case #(.ID(5),.OUT_PAR(4)) l5 (.clk(clk),.done(done[1]));
    initial begin
        wait(done===2'b11);
        repeat(3)@(posedge clk);
        $display("MAC_L3L5_ALL_CONFIGS_PASS configs=2");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"MAC L3/L5 FIFO timeout");
    end
endmodule

`default_nettype wire
