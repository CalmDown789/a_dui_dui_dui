`timescale 1ns / 1ps

// Independent front-to-back queue model, plus the unchanged original FIFO.
// The model removes its first element on pop and appends at its tail on push;
// it copies neither the DUT's newest-first SRL nor circular address pointers.
module fifo_srl_checker #(
    parameter integer ID=1,
    parameter integer DATA_W=6400,
    parameter integer DEPTH=4
)(input wire clk, output reg done=0);
    localparam integer COUNT_W=$clog2(DEPTH+1);
    reg rst=1, in_valid=0, out_ready=0;
    reg [DATA_W-1:0] in_data=0;
    wire in_ready, out_valid, ref_in_ready, ref_out_valid;
    wire [DATA_W-1:0] out_data, ref_out_data;
    wire [COUNT_W-1:0] occupancy, ref_occupancy;
    elastic_fifo #(.DATA_W(DATA_W),.DEPTH(DEPTH)) dut (
        .clk(clk),.rst(rst),.in_valid(in_valid),.in_ready(in_ready),.in_data(in_data),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),.occupancy(occupancy));
    elastic_fifo_reference #(.DATA_W(DATA_W),.DEPTH(DEPTH)) original (
        .clk(clk),.rst(rst),.in_valid(in_valid),.in_ready(ref_in_ready),.in_data(in_data),
        .out_valid(ref_out_valid),.out_ready(out_ready),.out_data(ref_out_data),.occupancy(ref_occupancy));

    reg [DATA_W-1:0] expected[0:DEPTH-1];
    integer size=0, next_token=1, cycles=0, pushes=0, pops=0, discarded=0;
    integer full_exchange=0, full_run=0, max_full_run=0;
    integer simultaneous=0, steady_run=0, max_steady_run=0;
    integer append_stalled=0, full_stalls=0, hold_checks=0, input_bubbles=0;
    integer empty_to_one=0, became_full=0, drained_full=0;
    integer reset_nonempty=0, reset_full=0, reset_partial=0;
    integer reset_pending_source=0, reset_input_asserted=0, pending_hold_checks=0;
    integer random_cycles=0;
    reg source_pending=0, output_hold=0;
    reg [DATA_W-1:0] source_word, held_word;
    reg [31:0] random_state;
    integer j, iteration;

    function automatic [31:0] next_random(input [31:0] value);
        reg [31:0] x;
        begin
            x=value^(value<<13);
            x=x^(x>>17);
            next_random=x^(x<<5);
        end
    endfunction

    function automatic [DATA_W-1:0] make_word(input integer token);
        integer bit_index;
        reg [31:0] x;
        begin
            make_word=0;
            x=32'hb079264a^token^(ID*32'h9e3779b9);
            // Every bit is initialized, including non-32-bit final slices.
            for(bit_index=0;bit_index<DATA_W;bit_index=bit_index+1)begin
                if((bit_index%32)==0)x=next_random(x);
                make_word[bit_index]=x[bit_index%32];
                if(bit_index<32)make_word[bit_index]=token[bit_index];
            end
        end
    endfunction

    task automatic check_outputs;
        reg expected_ready;
        begin
            expected_ready=(size<DEPTH)||((size!=0)&&out_ready);
            if(occupancy!==size[COUNT_W-1:0])
                $fatal(1,"FIFO id=%0d occupancy cycle=%0d expected=%0d actual=%0d",ID,cycles,size,occupancy);
            if(in_ready!==expected_ready || out_valid!==(size!=0))
                $fatal(1,"FIFO id=%0d ready/valid cycle=%0d size=%0d",ID,cycles,size);
            if(in_ready!==ref_in_ready || out_valid!==ref_out_valid || occupancy!==ref_occupancy)
                $fatal(1,"FIFO id=%0d reference handshake/occupancy mismatch cycle=%0d",ID,cycles);
            if(size!=0)begin
                if(out_data!==expected[0])
                    $fatal(1,"FIFO id=%0d full-width queue data/X mismatch cycle=%0d",ID,cycles);
                if(out_data!==ref_out_data)
                    $fatal(1,"FIFO id=%0d original data mismatch cycle=%0d",ID,cycles);
            end
            // Empty storage is intentionally unreset; invalid data is ignored.
        end
    endtask

    task automatic drive_cycle(input reg reset_now,
                               input reg want_input,
                               input reg ready_now);
        reg take_in,take_out,was_pending;
        integer old_size, q;
        begin
            @(negedge clk);
            rst=reset_now;
            out_ready=ready_now;
            was_pending=source_pending;
            if(reset_now)begin
                // Some directed resets deliberately leave valid asserted.
                // Reset cancels a pending producer transaction, never accepts it.
                in_valid=want_input;
                in_data=make_word(next_token);
            end else if(source_pending)begin
                in_valid=1;
                in_data=source_word;
                pending_hold_checks=pending_hold_checks+1;
            end else begin
                in_valid=want_input;
                in_data=make_word(next_token);
            end
            #1;
            if(!reset_now)begin
                check_outputs();
                if(output_hold)begin
                    if(!out_valid || out_data!==held_word)
                        $fatal(1,"FIFO id=%0d output changed during stall cycle=%0d",ID,cycles);
                    hold_checks=hold_checks+1;
                end
                if(!in_valid)input_bubbles=input_bubbles+1;
                if(size==DEPTH && in_valid && !out_ready)full_stalls=full_stalls+1;
                if(size==DEPTH && in_valid && out_ready && !in_ready)
                    $fatal(1,"FIFO id=%0d full pop/push inserted a bubble",ID);
            end
            old_size=size;
            take_in=!reset_now&&in_valid&&in_ready;
            take_out=!reset_now&&out_valid&&out_ready;
            output_hold=!reset_now&&out_valid&&!out_ready;
            if(output_hold)held_word=out_data;

            @(posedge clk);
            cycles=cycles+1;
            if(reset_now)begin
                if(size!=0)reset_nonempty=reset_nonempty+1;
                if(size==DEPTH)reset_full=reset_full+1;
                if(size>0&&size<DEPTH)reset_partial=reset_partial+1;
                if(was_pending)reset_pending_source=reset_pending_source+1;
                if(in_valid)reset_input_asserted=reset_input_asserted+1;
                discarded=discarded+size;
                size=0;
                source_pending=0;
                output_hold=0;
                full_run=0;
                steady_run=0;
                next_token=next_token+1;
            end else begin
                if(take_in&&take_out)begin
                    simultaneous=simultaneous+1;
                    steady_run=steady_run+1;
                    if(steady_run>max_steady_run)max_steady_run=steady_run;
                end else steady_run=0;
                if(old_size==DEPTH&&take_in&&take_out)begin
                    full_exchange=full_exchange+1;
                    full_run=full_run+1;
                    if(full_run>max_full_run)max_full_run=full_run;
                end else full_run=0;
                if(old_size!=0&&!out_ready&&take_in)append_stalled=append_stalled+1;
                if(take_out)begin
                    if(size<=0)$fatal(1,"queue model underflow");
                    for(q=0;q<DEPTH-1;q=q+1)expected[q]=expected[q+1];
                    size=size-1;
                    pops=pops+1;
                end
                if(take_in)begin
                    if(size>=DEPTH)$fatal(1,"queue model overflow");
                    expected[size]=in_data;
                    size=size+1;
                    pushes=pushes+1;
                    next_token=next_token+1;
                    source_pending=0;
                end else if(in_valid)begin
                    source_pending=1;
                    source_word=in_data;
                end
                if(old_size==0&&size==1)empty_to_one=empty_to_one+1;
                if(old_size<DEPTH&&size==DEPTH)became_full=became_full+1;
                if(old_size==DEPTH&&size<DEPTH)drained_full=drained_full+1;
            end
            #1;
            check_outputs();
        end
    endtask

    initial begin
        random_state=32'h601ad97b^ID;
        repeat(2)drive_cycle(1,0,0);
        repeat(4)drive_cycle(0,0,1);
        repeat(DEPTH)drive_cycle(0,1,0);
        repeat(8)drive_cycle(0,0,0);
        // Full occupancy must sustain forty consecutive replacements.
        repeat(40)drive_cycle(0,1,1);
        repeat(DEPTH+3)drive_cycle(0,0,1);
        // One-entry occupancy must also sustain one word each clock.
        drive_cycle(0,1,0);
        repeat(40)drive_cycle(0,1,1);
        repeat(DEPTH+3)drive_cycle(0,0,1);
        // Append while keeping the original head stalled and stable.
        drive_cycle(0,1,0);
        repeat(4)drive_cycle(0,0,0);
        repeat(DEPTH-1)drive_cycle(0,1,0);
        repeat(8)drive_cycle(0,1,0);
        repeat(DEPTH+4)drive_cycle(0,0,1);
        // Flush a full queue with a waiting producer and asserted input valid.
        repeat(DEPTH)drive_cycle(0,1,0);
        repeat(2)drive_cycle(0,1,0);
        drive_cycle(1,1,1);
        repeat(4)drive_cycle(0,0,1);
        if(DEPTH>1)begin
            repeat(DEPTH/2)drive_cycle(0,1,0);
            drive_cycle(1,0,0);
            repeat(4)drive_cycle(0,0,1);
        end
        // Force repeated complete fills and drains, including non-power-of-two
        // ring-pointer wrap in the unchanged fallback/reference branches.
        for(iteration=0;iteration<20;iteration=iteration+1)begin
            repeat(DEPTH)drive_cycle(0,1,0);
            repeat(DEPTH)drive_cycle(0,0,1);
        end
        for(j=0;j<2000;j=j+1)begin
            random_cycles=random_cycles+1;
            random_state=next_random(random_state);
            if((j%317)==316)drive_cycle(1,random_state[3],random_state[4]);
            else drive_cycle(0,random_state[0]|random_state[1],
                             ((j%211)<51)?1'b0:random_state[2]);
        end
        repeat(DEPTH+8)drive_cycle(0,0,1);
        if(size!=0||out_valid||source_pending)
            $fatal(1,"FIFO id=%0d final drain incomplete",ID);
        if(pushes!=pops+discarded)
            $fatal(1,"FIFO id=%0d lost/extra model transaction accounting",ID);
        if(pushes<100||pops<100||full_exchange<40||max_full_run<40||
           simultaneous<40||max_steady_run<40||full_stalls<8||hold_checks<20||
           empty_to_one<20||became_full<20||drained_full<20||
           reset_nonempty==0||reset_full==0||reset_pending_source==0||
           reset_input_asserted==0||pending_hold_checks<8||input_bubbles<8||
           random_cycles!=2000)
            $fatal(1,"FIFO id=%0d required coverage missing",ID);
        if(DEPTH>1&&(append_stalled<DEPTH-1||reset_partial==0))
            $fatal(1,"FIFO id=%0d missing partial-fill/append/reset coverage",ID);
        $display("FIFO_SRL_CONFIG_PASS id=%0d width=%0d depth=%0d cycles=%0d pushes=%0d pops=%0d discarded=%0d full_exchange=%0d full_run=%0d simultaneous=%0d steady_run=%0d append_stalled=%0d full_stalls=%0d holds=%0d empty_to_one=%0d became_full=%0d drained_full=%0d reset_full=%0d reset_partial=%0d reset_pending=%0d reset_valid=%0d random_cycles=%0d",
                 ID,DATA_W,DEPTH,cycles,pushes,pops,discarded,full_exchange,
                 max_full_run,simultaneous,max_steady_run,append_stalled,
                 full_stalls,hold_checks,empty_to_one,became_full,drained_full,
                 reset_full,reset_partial,reset_pending_source,reset_input_asserted,random_cycles);
        done=1;
    end
endmodule

module tb_elastic_fifo_srl;
    reg clk=0;
    always #5 clk=~clk;
    wire [6:0] done;
    fifo_srl_checker #(.ID(1),.DATA_W(6400),.DEPTH(4)) l5_srl(clk,done[0]);
    fifo_srl_checker #(.ID(2),.DATA_W(256),.DEPTH(32)) narrow_network(clk,done[1]);
    fifo_srl_checker #(.ID(3),.DATA_W(200),.DEPTH(4)) narrow_window(clk,done[2]);
    fifo_srl_checker #(.ID(4),.DATA_W(1152),.DEPTH(4)) other_wide_window(clk,done[3]);
    fifo_srl_checker #(.ID(5),.DATA_W(1025),.DEPTH(3)) wide_tail_nonpow2(clk,done[4]);
    fifo_srl_checker #(.ID(6),.DATA_W(6400),.DEPTH(3)) same_width_other_depth(clk,done[5]);
    fifo_srl_checker #(.ID(7),.DATA_W(37),.DEPTH(1)) single_entry(clk,done[6]);
    initial begin
        wait(&done);
        $display("FIFO_SRL_ALL_SEVEN_CONFIGS_PASS");
        $finish;
    end
    initial begin
        #200000;
        $fatal(1,"FIFO SRL test timeout");
    end
endmodule
