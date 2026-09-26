`timescale 1ns / 1ps

// Independent queue scoreboard: on pop, remove the front word by shifting
// the expected queue. This model does not copy the DUT's circular pointers.
module tb_mac_partial_fifo2;
    localparam integer DATA_W=131;
    reg clk=0;
    always #5 clk=~clk;
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
    integer size=0, next_token=1, cycles=0, pushes=0, pops=0;
    integer full_pop_blocks_input=0, simultaneous=0, max_steady_run=0;
    integer steady_run=0, full_stalls=0, held_checks=0, reset_nonempty=0;
    integer append_stalled=0, empty_push=0;
    reg source_pending=0, output_hold=0;
    reg [DATA_W-1:0] source_word,held_word;
    reg [31:0] random_state=32'h579bef13;
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
            x=32'h92f037ac^token;
            for(lane=0;lane<4;lane=lane+1)begin
                x=xorshift(x);
                make_word[lane*32+:32]=x;
            end
            make_word[31:0]=token;
            make_word[130:128]=token[2:0];
        end
    endfunction

    task automatic check_outputs;
        begin
            if(occupancy!==size[1:0])
                $fatal(1,"occupancy cycle=%0d expected=%0d got=%0d",cycles,size,occupancy);
            if(in_ready!==(size<2))
                $fatal(1,"in_ready must depend only on registered count cycle=%0d size=%0d out_ready=%b",cycles,size,out_ready);
            if(out_valid!==(size!=0))
                $fatal(1,"out_valid cycle=%0d expected size=%0d",cycles,size);
            if((size!=0)&&(out_data!==expected[0]))
                $fatal(1,"data/phase/X cycle=%0d expected=%h got=%h",cycles,expected[0],out_data);
        end
    endtask

    task automatic drive_cycle(input reg reset_now,
                               input reg want_input,
                               input reg ready_now);
        reg take_in,take_out;
        integer old_size;
        begin
            @(negedge clk);
            rst=reset_now;
            out_ready=ready_now;
            if(reset_now)begin
                in_valid=0;
                source_pending=0;
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
                if(output_hold)begin
                    if(!out_valid||(out_data!==held_word))
                        $fatal(1,"output not held cycle=%0d",cycles);
                    held_checks=held_checks+1;
                end
            end
            old_size=size;
            take_in=!reset_now&&in_valid&&in_ready;
            take_out=!reset_now&&out_valid&&out_ready;
            if(!reset_now&&(size==2)&&in_valid&&!out_ready)
                full_stalls=full_stalls+1;
            if(!reset_now&&(size==2)&&in_valid&&out_ready)begin
                // A look-ahead FIFO with '|| pop' would fail this check.
                if(in_ready)$fatal(1,"full pop incorrectly enables input combinationally");
                full_pop_blocks_input=full_pop_blocks_input+1;
            end
            output_hold=!reset_now&&out_valid&&!out_ready;
            if(output_hold)held_word=out_data;

            @(posedge clk);
            cycles=cycles+1;
            if(reset_now)begin
                if(size!=0)reset_nonempty=reset_nonempty+1;
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
                    if(size>=2)$fatal(1,"scoreboard overflow");
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
        repeat(2)drive_cycle(0,1,0);
        repeat(5)drive_cycle(0,1,0);
        // Full recovery forbids push in the first pop cycle. Thereafter
        // occupancy one sustains a simultaneous push/pop on every cycle.
        repeat(24)drive_cycle(0,1,1);
        repeat(40)drive_cycle(0,1,0);
        repeat(8)drive_cycle(0,0,1);
        repeat(2)drive_cycle(0,1,0);
        drive_cycle(1,0,0);
        repeat(6)drive_cycle(0,0,1);
        // Repeated fills/drains exercise both circular addresses many times.
        repeat(20)begin
            repeat(2)drive_cycle(0,1,0);
            repeat(2)drive_cycle(0,0,1);
        end
        for(j=0;j<1600;j=j+1)begin
            random_state=xorshift(random_state);
            if((j%293)==292)drive_cycle(1,0,0);
            else drive_cycle(0,random_state[0]|random_state[1],
                             ((j%131)<23)?1'b0:random_state[2]);
        end
        repeat(12)drive_cycle(0,0,1);
        if(size!=0||out_valid||source_pending)$fatal(1,"final drain incomplete");
        if(pushes<100||pops<100||full_pop_blocks_input==0||simultaneous<20||
           max_steady_run<20||full_stalls<5||held_checks<40||
           reset_nonempty==0||append_stalled==0||empty_push<20)
            $fatal(1,"required coverage missing");
        $display("MAC_PARTIAL_FIFO2_COVERAGE cycles=%0d pushes=%0d pops=%0d full_pop_blocked=%0d simultaneous=%0d max_steady_run=%0d full_stalls=%0d holds=%0d reset_nonempty=%0d append_stalled=%0d empty_push=%0d",
                 cycles,pushes,pops,full_pop_blocks_input,simultaneous,
                 max_steady_run,full_stalls,held_checks,reset_nonempty,
                 append_stalled,empty_push);
        $display("MAC_PARTIAL_FIFO2_131BIT_TEST_PASS");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"mac partial FIFO timeout");
    end
endmodule
