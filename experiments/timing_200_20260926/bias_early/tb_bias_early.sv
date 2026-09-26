`timescale 1ns / 1ps

// Member B, 2026-09-26. Five concurrent parameter configurations compare:
//   (1) candidate versus the unchanged original 36-bit module, cycle by cycle;
//   (2) valid outputs versus an independent signed-64 mathematical scoreboard.
// Bias is initialized once and remains constant, matching the frozen ROM.
module bias_early_checker #(
    parameter integer ID=1,
    parameter integer CIN=1,
    parameter integer COUT=16,
    parameter integer IN_PAR=1,
    parameter integer OUT_PAR=2
)(input wire clk, output reg done=0);
    localparam integer IN_GROUPS=CIN/IN_PAR;
    localparam integer QUEUE_DEPTH=256;
    reg rst=1, phase_valid=0, out_ready=0;
    reg [2:0] phase=0;
    reg [OUT_PAR*32-1:0] partial_sums=0;
    reg [COUT*32-1:0] bias_flat=0;
    reg [COUT*32-1:0] frozen_bias;
    wire phase_ready, out_valid, ref_phase_ready, ref_out_valid;
    wire [COUT*32-1:0] out_data, ref_out_data;

    phase_accumulator #(.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),
        .OUT_PAR(OUT_PAR)) dut (
        .clk(clk),.rst(rst),.phase_valid(phase_valid),.phase_ready(phase_ready),
        .phase(phase),.partial_sums(partial_sums),.bias_flat(bias_flat),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data)
    );
    phase_accumulator_reference36 #(.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),
        .OUT_PAR(OUT_PAR)) reference (
        .clk(clk),.rst(rst),.phase_valid(phase_valid),.phase_ready(ref_phase_ready),
        .phase(phase),.partial_sums(partial_sums),.bias_flat(bias_flat),
        .out_valid(ref_out_valid),.out_ready(out_ready),.out_data(ref_out_data)
    );

    reg signed [63:0] math_sum[0:COUT-1];
    reg [COUT*32-1:0] expected[0:QUEUE_DEPTH-1];
    integer head=0, tail=0, queued=0;
    integer next_phase=0, next_window=0, cycles=0;
    integer accepted_phases=0, completed_windows=0, consumed_windows=0;
    integer positive_clip=0, negative_clip=0, exact_max=0, exact_min=0;
    integer in_stalls=0, out_stalls=0, held_checks=0;
    integer reset_nonempty=0, reset_midphase=0, consecutive_outputs=0;
    integer recovered_after_wide_sum=0;
    reg intermediate_outside_i32[0:COUT-1];
    reg source_pending=0, output_hold=0, previous_consumed=0;
    reg [2:0] held_phase;
    reg [OUT_PAR*32-1:0] held_partials;
    reg [COUT*32-1:0] held_output;
    reg [31:0] random_state;
    integer c_init, j;

    function automatic [31:0] xorshift(input [31:0] value);
        reg [31:0] x;
        begin
            x=value^(value<<13);
            x=x^(x>>17);
            xorshift=x^(x<<5);
        end
    endfunction

    function automatic [31:0] channel_bias(input integer channel);
        begin
            case(channel%8)
                0: channel_bias=32'h7fffffff;
                1: channel_bias=32'h80000000;
                2: channel_bias=32'h00000000;
                3: channel_bias=32'h00000001;
                4: channel_bias=32'hffffffff;
                5: channel_bias=32'd123456789;
                6: channel_bias=-32'sd123456789;
                default: channel_bias=32'd2000000000;
            endcase
        end
    endfunction

    function automatic [31:0] make_partial(input integer window_id,
                                          input integer phase_id,
                                          input integer lane);
        reg [31:0] seed;
        integer input_group;
        begin
            input_group=phase_id%IN_GROUPS;
            seed=32'hac753219 ^ (window_id*32'h9e3779b9) ^
                 (phase_id*32'h85ebca6b) ^ (lane*32'hc2b2ae35) ^ ID;
            case(window_id%16)
                0: make_partial=32'h7fffffff;
                1: make_partial=32'h80000000;
                2: make_partial=32'h00000000;
                // For IN_GROUPS=8, wide intermediate sums return to bias.
                3: make_partial=(input_group%2==0)?32'h7fffffff:32'h80000001;
                4: make_partial=(input_group==0)?32'h7fffffff:32'h00000000;
                5: make_partial=(input_group==0)?32'h80000000:32'h00000000;
                6: make_partial=(input_group%2==0)?32'h80000000:32'h7fffffff;
                7: make_partial=(input_group%2==0)?32'h00000001:32'hffffffff;
                8: make_partial=32'h00000001;
                9: make_partial=32'hffffffff;
                default: make_partial=xorshift(xorshift(seed));
            endcase
        end
    endfunction

    function automatic signed [63:0] signed64(input [31:0] value);
        begin
            signed64=$signed({{32{value[31]}},value});
        end
    endfunction

    function automatic [31:0] mathematical_clip(input signed [63:0] value);
        begin
            if(value>64'sd2147483647)mathematical_clip=32'h7fffffff;
            else if(value< -64'sd2147483648)mathematical_clip=32'h80000000;
            else mathematical_clip=value[31:0];
        end
    endfunction

    task automatic check_outputs;
        integer c;
        begin
            if(bias_flat!==frozen_bias)
                $fatal(1,"checker %0d bias changed",ID);
            if(phase_ready!==ref_phase_ready)
                $fatal(1,"checker %0d ready differs cycle=%0d",ID,cycles);
            if(out_valid!==ref_out_valid)
                $fatal(1,"checker %0d output latency/valid differs cycle=%0d",ID,cycles);
            if((out_valid!==1'b0)&&(out_valid!==1'b1))
                $fatal(1,"checker %0d unknown out_valid",ID);
            if(out_valid)begin
                if(out_data!==ref_out_data)
                    $fatal(1,"checker %0d reference data mismatch cycle=%0d",ID,cycles);
                if(queued==0)
                    $fatal(1,"checker %0d unexpected output cycle=%0d",ID,cycles);
                for(c=0;c<COUT;c=c+1)
                    if(out_data[c*32+:32]!==expected[head][c*32+:32])
                        $fatal(1,"checker %0d mathematical mismatch cycle=%0d channel=%0d expected=%h got=%h",
                               ID,cycles,c,expected[head][c*32+:32],out_data[c*32+:32]);
            end
        end
    endtask

    task automatic drive_cycle(input reg reset_now,
                               input reg want_phase,
                               input reg ready_now);
        reg take_phase, take_output;
        integer lane, c, output_group;
        reg [COUT*32-1:0] result_word;
        begin
            @(negedge clk);
            rst=reset_now;
            out_ready=ready_now;
            if(reset_now)begin
                phase_valid=0;
                source_pending=0;
            end else begin
                phase_valid=want_phase||source_pending;
                phase=next_phase[2:0];
                for(lane=0;lane<OUT_PAR;lane=lane+1)
                    partial_sums[lane*32+:32]=make_partial(next_window,next_phase,lane);
                if(source_pending && ((phase!==held_phase)||(partial_sums!==held_partials)))
                    $fatal(1,"checker %0d producer changed a stalled phase",ID);
            end
            #1;
            if(!reset_now)begin
                check_outputs();
                if(output_hold)begin
                    if(!out_valid||(out_data!==held_output))
                        $fatal(1,"checker %0d output hold violation",ID);
                    held_checks=held_checks+1;
                end
            end
            take_phase=!reset_now&&phase_valid&&phase_ready;
            take_output=!reset_now&&out_valid&&out_ready;
            output_hold=!reset_now&&out_valid&&!out_ready;
            if(output_hold)begin
                held_output=out_data;
                out_stalls=out_stalls+1;
            end
            if(!reset_now&&phase_valid&&!phase_ready)in_stalls=in_stalls+1;

            @(posedge clk);
            cycles=cycles+1;
            if(reset_now)begin
                if(queued!=0)reset_nonempty=reset_nonempty+1;
                if(next_phase!=0)reset_midphase=reset_midphase+1;
                head=0;tail=0;queued=0;
                next_phase=0;
                next_window=next_window+1;
                source_pending=0;output_hold=0;previous_consumed=0;
                for(c=0;c<COUT;c=c+1)begin
                    math_sum[c]=0;
                    intermediate_outside_i32[c]=0;
                end
            end else begin
                if(take_output)begin
                    if(previous_consumed)consecutive_outputs=consecutive_outputs+1;
                    head=(head==QUEUE_DEPTH-1)?0:head+1;
                    queued=queued-1;
                    consumed_windows=consumed_windows+1;
                end
                previous_consumed=take_output;
                if(take_phase)begin
                    accepted_phases=accepted_phases+1;
                    source_pending=0;
                    output_group=next_phase/IN_GROUPS;
                    if(next_phase==0)
                        for(c=0;c<COUT;c=c+1)begin
                            math_sum[c]=signed64(channel_bias(c));
                            intermediate_outside_i32[c]=0;
                        end
                    // Independent mathematics: only the scheduled output
                    // group receives this phase's signed-32 partial terms.
                    for(lane=0;lane<OUT_PAR;lane=lane+1)begin
                        c=output_group*OUT_PAR+lane;
                        math_sum[c]=math_sum[c]+signed64(partial_sums[lane*32+:32]);
                        if((math_sum[c]>64'sd34359738367)||
                           (math_sum[c]< -64'sd34359738368))
                            $fatal(1,"checker %0d stimulus exceeded signed36",ID);
                        if((next_phase!=7)&&((math_sum[c]>64'sd2147483647)||
                                               (math_sum[c]< -64'sd2147483648)))
                            intermediate_outside_i32[c]=1;
                    end
                    if(next_phase==7)begin
                        result_word=0;
                        for(c=0;c<COUT;c=c+1)begin
                            result_word[c*32+:32]=mathematical_clip(math_sum[c]);
                            if(math_sum[c]>64'sd2147483647)positive_clip=positive_clip+1;
                            else if(math_sum[c]< -64'sd2147483648)negative_clip=negative_clip+1;
                            else if(intermediate_outside_i32[c])
                                recovered_after_wide_sum=recovered_after_wide_sum+1;
                            if(math_sum[c]==64'sd2147483647)exact_max=exact_max+1;
                            if(math_sum[c]== -64'sd2147483648)exact_min=exact_min+1;
                        end
                        if(queued>=QUEUE_DEPTH)$fatal(1,"scoreboard overflow");
                        expected[tail]=result_word;
                        tail=(tail==QUEUE_DEPTH-1)?0:tail+1;
                        queued=queued+1;
                        completed_windows=completed_windows+1;
                        next_phase=0;
                        next_window=next_window+1;
                    end else next_phase=next_phase+1;
                end else if(phase_valid)begin
                    source_pending=1;
                    held_phase=phase;
                    held_partials=partial_sums;
                end
            end
            #1;
            check_outputs();
        end
    endtask

    initial begin
        random_state=32'h1209ce75^ID;
        for(c_init=0;c_init<COUT;c_init=c_init+1)begin
            bias_flat[c_init*32+:32]=channel_bias(c_init);
            math_sum[c_init]=0;
            intermediate_outside_i32[c_init]=0;
        end
        frozen_bias=bias_flat;
        repeat(2)drive_cycle(1,0,0);
        // Cover every directed arithmetic mode without output stalls.
        repeat(160)drive_cycle(0,1,1);
        // Fill both output stages, then release consecutive pending outputs.
        repeat(40)drive_cycle(0,1,0);
        repeat(12)drive_cycle(0,0,1);
        // Reset while valid outputs are pending and while a phase group is partial.
        repeat(40)drive_cycle(0,1,0);
        drive_cycle(1,0,0);
        repeat(3)drive_cycle(0,1,1);
        drive_cycle(1,0,0);
        for(j=0;j<1800;j=j+1)begin
            random_state=xorshift(random_state);
            if((j%389)==388)drive_cycle(1,0,0);
            else drive_cycle(0,random_state[0]|random_state[1],
                             ((j%173)<37)?1'b0:random_state[2]);
        end
        // Finish any partially accepted group before checking the final drain.
        while((next_phase!=0)||source_pending)drive_cycle(0,1,1);
        repeat(24)drive_cycle(0,0,1);
        if(queued!=0||out_valid||source_pending||(next_phase!=0))
            $fatal(1,"checker %0d final drain failed",ID);
        if(completed_windows<40||consumed_windows<30||positive_clip==0||
           negative_clip==0||exact_max==0||exact_min==0||in_stalls==0||
           out_stalls==0||held_checks==0||reset_nonempty==0||
           reset_midphase==0||consecutive_outputs==0)
            $fatal(1,"checker %0d required coverage missing",ID);
        if(IN_GROUPS>1&&recovered_after_wide_sum==0)
            $fatal(1,"checker %0d missing wide intermediate recovery",ID);
        $display("BIAS_EARLY_CONFIG_PASS id=%0d CIN=%0d COUT=%0d IN_PAR=%0d OUT_PAR=%0d cycles=%0d phases=%0d complete=%0d consumed=%0d clip_hi=%0d clip_lo=%0d exact_hi=%0d exact_lo=%0d in_stalls=%0d out_stalls=%0d holds=%0d reset_nonempty=%0d reset_midphase=%0d consecutive=%0d recovered=%0d",
                 ID,CIN,COUT,IN_PAR,OUT_PAR,cycles,accepted_phases,
                 completed_windows,consumed_windows,positive_clip,negative_clip,
                 exact_max,exact_min,in_stalls,out_stalls,held_checks,
                 reset_nonempty,reset_midphase,consecutive_outputs,recovered_after_wide_sum);
        done=1;
    end
endmodule

module tb_bias_early;
    reg clk=0;
    always #5 clk=~clk;
    wire [4:0] done;
    bias_early_checker #(.ID(1),.CIN(1), .COUT(16),.IN_PAR(1),.OUT_PAR(2))
        l1(.clk(clk),.done(done[0]));
    bias_early_checker #(.ID(2),.CIN(16),.COUT(8), .IN_PAR(2),.OUT_PAR(8))
        l2(.clk(clk),.done(done[1]));
    bias_early_checker #(.ID(3),.CIN(8), .COUT(8), .IN_PAR(1),.OUT_PAR(8))
        l3(.clk(clk),.done(done[2]));
    bias_early_checker #(.ID(4),.CIN(8), .COUT(16),.IN_PAR(1),.OUT_PAR(16))
        l4(.clk(clk),.done(done[3]));
    bias_early_checker #(.ID(5),.CIN(16),.COUT(4), .IN_PAR(2),.OUT_PAR(4))
        l5(.clk(clk),.done(done[4]));
    initial begin
        wait(&done);
        $display("BIAS_EARLY_ALL_FIVE_CONFIGS_PASS");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"bias-early test timeout");
    end
endmodule
