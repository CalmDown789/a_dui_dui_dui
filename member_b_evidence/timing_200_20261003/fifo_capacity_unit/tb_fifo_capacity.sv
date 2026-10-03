`timescale 1ns/1ps
// Member B: independent accepted-transfer scoreboard for the actual 6400-bit
// L5 window FIFO. Covers full+pop rejection, simultaneous transfer, long
// stalls, all data bits, pointer wrapping, and reset while nonempty.
module tb_fifo_capacity;
    localparam W=6400;
    reg clk=0;
    always #2.5 clk=~clk;
    reg rst=1, in_valid=0, out_ready=0;
    reg [W-1:0] in_data=0;
    wire in_ready, out_valid;
    wire [W-1:0] out_data;
    wire [2:0] occupancy;
    elastic_fifo #(.DATA_W(W),.DEPTH(4)) dut(.*);
    reg [W-1:0] expected[0:4095];
    integer head=0, tail=0, seq=0, pushes=0, pops=0;
    integer full_pop=0, concurrent=0, reset_nonempty=0, stalled=0;
    reg hold_input=0, held_output=0;
    reg [W-1:0] held_data;
    reg [31:0] rng=32'hbd412719;
    integer cycle, lane;
    reg [W-1:0] word;
    function automatic [W-1:0] make_word(input integer tag);
        integer k;
        begin
            for(k=0;k<W/64;k=k+1)
                make_word[k*64+:64]={32'hb37a9081^(tag*32'h45789abc)^k,
                                    32'hccda1547^(tag*32'hca301197)^(k*32'h1234567)};
        end
    endfunction
    always @(posedge clk) begin
        if(rst) begin
            if(tail>head)reset_nonempty=reset_nonempty+1;
            head=0;tail=0;hold_input=0;held_output=0;
        end else begin
            if(out_valid !== (tail>head))$fatal(1,"output-valid disagrees with queue");
            if(in_ready !== (tail-head<4))$fatal(1,"capacity-only input ready violated");
            if(held_output && (!out_valid || out_data !== held_data))
                $fatal(1,"output changed under backpressure");
            if(out_valid && out_ready)begin
                if(out_data !== expected[head])$fatal(1,"6400-bit FIFO data/order mismatch at pop %0d",pops);
                head=head+1;pops=pops+1;
            end
            if(in_valid && in_ready)begin
                expected[tail]=in_data;tail=tail+1;
                if(tail>=4096)$fatal(1,"scoreboard storage exhausted");
                seq=seq+1;pushes=pushes+1;
            end
            if(occupancy==4 && out_ready && in_valid)full_pop=full_pop+1;
            if(in_valid && in_ready && out_valid && out_ready)concurrent=concurrent+1;
            if(out_valid && !out_ready)stalled=stalled+1;
            hold_input=in_valid&&!in_ready;
            held_output=out_valid&&!out_ready;held_data=out_data;
        end
        #0.5;
        if(occupancy !== tail-head)$fatal(1,"occupancy differs from accepted transfers");
    end
    initial begin
        repeat(4)@(negedge clk);
        rst=0;
        for(cycle=0;cycle<2000;cycle=cycle+1)begin
            @(negedge clk);
            rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
            // Reset during the forced output stall, so both resets are
            // guaranteed to cancel a nonempty queue rather than rely on RNG.
            rst=(cycle==225 || cycle==725);
            if(rst)begin in_valid=0;out_ready=0;end
            else begin
                if(!hold_input)in_valid=(cycle<32 || cycle%100<35 || rng[0]);
                out_ready=(cycle<12)?0:(cycle<32)?1:(cycle%100<35)?0:(cycle%100<65)?1:rng[4];
                in_data=make_word(seq);
            end
        end
        @(negedge clk);out_ready=1;
        // Complete a held source offer before ending the input stream.
        if(hold_input)begin
            in_valid=1;in_data=make_word(seq);
            @(negedge clk);
        end
        in_valid=0;
        repeat(10)@(negedge clk);
        if(tail!=head || occupancy!=0)$fatal(1,"queue did not drain");
        if(pushes<300 || pops<300 || full_pop<10 || concurrent<100 || reset_nonempty<2 || stalled<100)
            $fatal(1,"insufficient coverage p=%0d o=%0d fp=%0d c=%0d r=%0d s=%0d",
                   pushes,pops,full_pop,concurrent,reset_nonempty,stalled);
        $display("L5_FIFO_CAPACITY_6400BIT_PASS pushes=%0d pops=%0d full_pop=%0d concurrent=%0d resets=%0d stalls=%0d",
                 pushes,pops,full_pop,concurrent,reset_nonempty,stalled);
        $finish;
    end
    initial begin #100000;$fatal(1,"unit timeout");end
endmodule
