`timescale 1ns / 1ps
`default_nettype none

// Shifted-slot candidate vs. original indexed-slot reference, plus an
// independent arithmetic / external ready-valid scoreboard. Static parameters
// are required because each group reads PReLU/Q31 at dispatch time.
module post_shift_case #(
    parameter integer ID = 0,
    parameter integer CHANNELS = 16,
    parameter integer LANES = 2,
    parameter integer OUT_W = 16,
    parameter integer OUT_SIGNED = 1,
    parameter integer APPLY_PRELU = 1
)(input wire clk, output reg done = 1'b0);
    localparam integer QUEUE_SIZE = 512;
    localparam integer MAX_CYCLES = 50000;
    localparam integer GROUPS = CHANNELS/LANES;
    reg rst = 1'b1;
    reg in_valid = 1'b0;
    wire in_ready;
    reg [CHANNELS*32-1:0] accum_flat = 0;
    reg [CHANNELS*16-1:0] prelu_flat = 0;
    reg [CHANNELS*32-1:0] q31_flat = 0;
    wire out_valid;
    reg out_ready = 1'b0;
    wire [CHANNELS*OUT_W-1:0] out_flat;
    wire reference_in_ready, reference_out_valid;
    wire [CHANNELS*OUT_W-1:0] reference_out_flat;
    reg [CHANNELS*16-1:0] frozen_prelu;
    reg [CHANNELS*32-1:0] frozen_q31;

    vector_postprocess_shared #(
        .CHANNELS(CHANNELS), .LANES(LANES), .OUT_W(OUT_W),
        .OUT_SIGNED(OUT_SIGNED), .APPLY_PRELU(APPLY_PRELU)
    ) dut (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_ready(in_ready),
        .accum_flat(accum_flat), .prelu_flat(prelu_flat), .q31_flat(q31_flat),
        .out_valid(out_valid), .out_ready(out_ready), .out_flat(out_flat)
    );
    vector_postprocess_shared_reference #(
        .CHANNELS(CHANNELS), .LANES(LANES), .OUT_W(OUT_W),
        .OUT_SIGNED(OUT_SIGNED), .APPLY_PRELU(APPLY_PRELU)
    ) reference_dut (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_ready(reference_in_ready),
        .accum_flat(accum_flat), .prelu_flat(prelu_flat), .q31_flat(q31_flat),
        .out_valid(reference_out_valid), .out_ready(out_ready),
        .out_flat(reference_out_flat)
    );

    // Compare after NBA too, including reset and invalid-output cycles. Output
    // slots are reset and assembled in the same order in both implementations,
    // so this candidate is expected to preserve their entire cycle trace.
    always @(posedge clk) begin
        #1;
        if (in_ready !== reference_in_ready || out_valid !== reference_out_valid ||
            out_flat !== reference_out_flat)
            $fatal(1, "Post-shift cycle equivalence mismatch id=%0d in_ready=%b/%b out_valid=%b/%b out=%h/%h time=%0t",
                   ID, in_ready, reference_in_ready, out_valid, reference_out_valid,
                   out_flat, reference_out_flat, $time);
        // Check the unsaturated arithmetic inputs even in issue bubbles, when
        // the dispatch register must hold its last word in both versions.
        if (dut.dispatch_valid !== reference_dut.dispatch_valid ||
            dut.dispatch_accum !== reference_dut.dispatch_accum ||
            dut.dispatch_prelu !== reference_dut.dispatch_prelu ||
            dut.dispatch_q31 !== reference_dut.dispatch_q31)
            $fatal(1, "Post-shift dispatch/hold mismatch id=%0d time=%0t", ID, $time);
    end

    // Signed 64-bit mathematical reference: division of a nonnegative
    // magnitude implements nearest rounding, with exact ties away from zero.
    // All products here are bounded by 2^62, so abs/add-half fit signed64.
    // This deliberately does not reproduce the DUT's bit slicing/carry logic.
    function automatic signed [63:0] rounded_division(
        input signed [63:0] value, input integer fraction_bits
    );
        reg signed [63:0] denominator, magnitude, result_value;
        begin
            denominator = 64'sd1 <<< fraction_bits;
            magnitude = (value < 0) ? -value : value;
            result_value = (magnitude + denominator/2) / denominator;
            rounded_division = (value < 0) ? -result_value : result_value;
        end
    endfunction

    function automatic [OUT_W-1:0] reference_channel(
        input signed [31:0] accumulator,
        input signed [15:0] alpha,
        input signed [31:0] multiplier
    );
        reg signed [63:0] value, wide_alpha, wide_multiplier, product_value;
        reg signed [63:0] maximum, minimum;
        begin
            value = accumulator;
            wide_alpha = alpha;
            wide_multiplier = multiplier;
            if (APPLY_PRELU != 0 && value < 0) begin
                product_value = value * wide_alpha;
                value = rounded_division(product_value, 15);
                if (value > 64'sd2147483647) value = 64'sd2147483647;
                if (value < -64'sd2147483648) value = -64'sd2147483648;
            end
            product_value = value * wide_multiplier;
            value = rounded_division(product_value, 31);
            if (OUT_SIGNED != 0) begin
                maximum = (64'sd1 <<< (OUT_W-1)) - 1;
                minimum = -(64'sd1 <<< (OUT_W-1));
            end else begin
                maximum = (64'sd1 <<< OUT_W) - 1;
                minimum = 0;
            end
            if (value > maximum) value = maximum;
            if (value < minimum) value = minimum;
            reference_channel = value[OUT_W-1:0];
        end
    endfunction

    function automatic [CHANNELS*OUT_W-1:0] reference_vector(
        input [CHANNELS*32-1:0] vector_value
    );
        integer ch;
        begin
            for (ch=0; ch<CHANNELS; ch=ch+1)
                reference_vector[ch*OUT_W+:OUT_W] = reference_channel(
                    $signed(vector_value[ch*32+:32]),
                    $signed(frozen_prelu[ch*16+:16]),
                    $signed(frozen_q31[ch*32+:32]));
        end
    endfunction

    function automatic [31:0] next_random(input [31:0] state);
        reg [31:0] value;
        begin
            value = state ^ (state << 13);
            value = value ^ (value >> 17);
            next_random = value ^ (value << 5);
        end
    endfunction

    function automatic [31:0] accumulator_sample(
        input integer vector_id, input integer channel_id
    );
        reg [31:0] hash_value;
        begin
            hash_value = next_random(32'h6d2b79f5 ^ (vector_id*32'h9e3779b9)
                                     ^ (channel_id*32'h45d9f3b));
            // A dedicated phase stays small enough to avoid signed16 clipping.
            // For unsigned8 its positive lanes remain inside [1,100]. This
            // exposes group/channel swaps that extreme saturated vectors hide.
            if (vector_id >= 1000 && vector_id < 1064)
                accumulator_sample = ((vector_id-1000)*7 + channel_id*11) % 201 - 100;
            else case ((vector_id + channel_id*5) % 24)
                 0: accumulator_sample = 32'h80000000;
                 1: accumulator_sample = 32'h7fffffff;
                 2: accumulator_sample = -32'sd1;
                 3: accumulator_sample = 32'sd1;
                 4: accumulator_sample = -32'sd3;
                 5: accumulator_sample = 32'sd3;
                 6: accumulator_sample = -32'sd32768;
                 7: accumulator_sample = 32'sd32767;
                 8: accumulator_sample = -32'sd65536;
                 9: accumulator_sample = 32'sd65535;
                10: accumulator_sample = -32'sd1073741824;
                11: accumulator_sample = 32'sd1073741824;
                12: accumulator_sample = 32'd0;
                13: accumulator_sample = 32'h80000001;
                14: accumulator_sample = -32'sd16385;
                15: accumulator_sample = -32'sd16384;
                16: accumulator_sample = -32'sd16383;
                17: accumulator_sample = 32'sd511;
                18: accumulator_sample = 32'sd509;
                19: accumulator_sample = -32'sd257;
                default: accumulator_sample = hash_value;
            endcase
        end
    endfunction

    function automatic [CHANNELS*32-1:0] make_vector(input integer vector_id);
        integer ch;
        begin
            for (ch=0; ch<CHANNELS; ch=ch+1)
                make_vector[ch*32+:32] = accumulator_sample(vector_id, ch);
        end
    endfunction

    reg [CHANNELS*OUT_W-1:0] expected [0:QUEUE_SIZE-1];
    integer head = 0, tail = 0;
    integer cycles = 0;
    integer total_inputs = 0, total_outputs = 0;
    integer input_stalls = 0, output_stalls = 0, simultaneous_io = 0;
    integer input_gaps = 0;
    integer reset_compute = 0, reset_held_output = 0;
    integer max_pending = 0;
    integer simultaneous_capture_issue = 0;
    integer slot_accepts [0:1];
    integer issue_hits [0:1][0:GROUPS-1];
    integer next_issue_group [0:1];
    reg [CHANNELS*32-1:0] captured_slot [0:1];
    reg last_input_fire = 1'b0, last_output_fire = 1'b0;
    reg input_was_stalled = 1'b0, output_was_stalled = 1'b0;
    reg [CHANNELS*32-1:0] held_input;
    reg [CHANNELS*OUT_W-1:0] held_output;
    integer ch_check;

    // Handshakes are sampled before NBA updates, as a synchronous peer sees
    // them. The driver changes signals at negedge and reads these counters #2
    // after posedge. No hierarchy or lane-valid signal drives the reference.
    always @(posedge clk) begin
        cycles = cycles + 1;
        if (cycles > MAX_CYCLES)
            $fatal(1, "SHARED_TIMEOUT id=%0d head=%0d tail=%0d", ID, head, tail);
        if (rst) begin
            head = 0;
            tail = 0;
            last_input_fire = 0;
            last_output_fire = 0;
            input_was_stalled = 0;
            output_was_stalled = 0;
            next_issue_group[0] = 0;
            next_issue_group[1] = 0;
            captured_slot[0] = 0;
            captured_slot[1] = 0;
            #1;
            if (out_valid !== 1'b0 || in_ready !== 1'b1)
                $fatal(1, "Reset failed to empty shared slots id=%0d", ID);
        end else begin
            if ($isunknown({in_ready, out_valid}))
                $fatal(1, "Unknown handshake output id=%0d cycle=%0d", ID, cycles);
            if (prelu_flat !== frozen_prelu || q31_flat !== frozen_q31)
                $fatal(1, "Shared parameters changed while running id=%0d", ID);
            if (input_was_stalled &&
                (in_valid !== 1'b1 || accum_flat !== held_input))
                $fatal(1, "Source failed to hold stalled vector id=%0d", ID);
            if (output_was_stalled &&
                (out_valid !== 1'b1 || out_flat !== held_output))
                $fatal(1, "DUT changed/dropped stalled output vector id=%0d", ID);

            last_input_fire = in_valid && in_ready;
            last_output_fire = out_valid && out_ready;
            input_was_stalled = in_valid && !in_ready;
            output_was_stalled = out_valid && !out_ready;
            held_input = accum_flat;
            held_output = out_flat;
            if (input_was_stalled) input_stalls = input_stalls + 1;
            if (output_was_stalled) output_stalls = output_stalls + 1;
            if (!in_valid && in_ready) input_gaps = input_gaps + 1;
            if (last_input_fire && last_output_fire)
                simultaneous_io = simultaneous_io + 1;

            // Observe scheduler state only to check the proposed shift and its
            // coverage. Expected math/order below still uses external transfers.
            // captured_slot stores the full original vector; it is never shifted.
            if (dut.issue_valid) begin
                if ($isunknown({dut.issue_slot, dut.issue_group}) ||
                    dut.issue_group >= GROUPS)
                    $fatal(1, "Invalid issue selector id=%0d", ID);
                if (dut.issue_group !== next_issue_group[dut.issue_slot])
                    $fatal(1, "Issue group order mismatch id=%0d slot=%0d got=%0d expected=%0d",
                           ID, dut.issue_slot, dut.issue_group, next_issue_group[dut.issue_slot]);
                if (dut.input_slot[dut.issue_slot][0+:LANES*32] !==
                    captured_slot[dut.issue_slot][next_issue_group[dut.issue_slot]*LANES*32+:LANES*32])
                    $fatal(1, "Shifted low channels mismatch id=%0d slot=%0d group=%0d",
                           ID, dut.issue_slot, next_issue_group[dut.issue_slot]);
                issue_hits[dut.issue_slot][next_issue_group[dut.issue_slot]] =
                    issue_hits[dut.issue_slot][next_issue_group[dut.issue_slot]] + 1;
                next_issue_group[dut.issue_slot] = next_issue_group[dut.issue_slot] + 1;
            end
            if (last_input_fire) begin
                if (dut.issue_valid && dut.issue_slot == dut.write_slot)
                    $fatal(1, "Capture and shift targeted the same occupied slot id=%0d", ID);
                if (dut.issue_valid)
                    simultaneous_capture_issue = simultaneous_capture_issue + 1;
                captured_slot[dut.write_slot] = accum_flat;
                next_issue_group[dut.write_slot] = 0;
                slot_accepts[dut.write_slot] = slot_accepts[dut.write_slot] + 1;
            end

            // Validate every visible result, including long blocked periods.
            // Pop before push: output is never allowed to bypass a fresh input.
            if (out_valid) begin
                if (head >= tail)
                    $fatal(1, "Unexpected/duplicate output id=%0d cycle=%0d", ID, cycles);
                for (ch_check=0; ch_check<CHANNELS; ch_check=ch_check+1)
                    if (out_flat[ch_check*OUT_W+:OUT_W] !==
                        expected[head][ch_check*OUT_W+:OUT_W])
                        $fatal(1, "Shared math/order mismatch id=%0d vec=%0d ch=%0d got=%h expected=%h cycle=%0d",
                               ID, head, ch_check, out_flat[ch_check*OUT_W+:OUT_W],
                               expected[head][ch_check*OUT_W+:OUT_W], cycles);
            end
            if (last_output_fire) begin
                head = head + 1;
                total_outputs = total_outputs + 1;
            end
            if (last_input_fire) begin
                if (tail >= QUEUE_SIZE) $fatal(1, "Reference capacity exceeded id=%0d", ID);
                expected[tail] = reference_vector(accum_flat);
                tail = tail + 1;
                total_inputs = total_inputs + 1;
            end
            if (tail-head > 2)
                $fatal(1, "Accepted beyond two occupied slots id=%0d pending=%0d", ID, tail-head);
            if (tail-head > max_pending) max_pending = tail-head;
        end
    end

    task automatic drive_cycle(input bit offer, input integer vector_id, input bit sink_ready);
        begin
            @(negedge clk);
            // Keep a previously offered vector until a real handshake. After
            // acceptance, changing all accumulator channels stresses capture.
            if (!in_valid || last_input_fire) begin
                in_valid = offer;
                accum_flat = make_vector(vector_id);
            end
            out_ready = sink_ready;
            @(posedge clk);
            #2;
        end
    endtask

    task automatic reset_case;
        begin
            @(negedge clk);
            rst = 1;
            in_valid = 0;
            out_ready = 0;
            accum_flat = 0;
            repeat (3) begin @(posedge clk); #2; end
            @(negedge clk);
            rst = 0;
        end
    endtask

    task automatic check_empty;
        integer k;
        begin
            for (k=0; k<40; k=k+1) begin
                drive_cycle(0, 900+k, 1);
                if (out_valid !== 1'b0 || head != 0 || tail != 0)
                    $fatal(1, "Stale output survived reset id=%0d", ID);
            end
        end
    endtask

    task automatic send_vectors(
        input integer count, input integer base_id, input integer mode,
        input [31:0] seed
    );
        integer sent, step;
        reg [31:0] random_state;
        bit offer, ready_value;
        begin
            sent = 0;
            step = 0;
            random_state = seed;
            while (sent < count) begin
                random_state = next_random(random_state);
                offer = (mode != 2) || (random_state[3:0] > 3);
                if (mode == 0) ready_value = 0;
                else if (mode == 1) ready_value = 1;
                else ready_value = (random_state[7:4] > 4) && ((step % 137) > 47);
                drive_cycle(offer, base_id+sent, ready_value);
                if (last_input_fire) sent = sent + 1;
                step = step + 1;
            end
            // Remove the final accepted offer before returning to the caller.
            drive_cycle(0, base_id+count, mode != 0);
        end
    endtask

    task automatic drain;
        integer k;
        begin
            while (head != tail || out_valid || in_valid)
                drive_cycle(0, 1234, 1);
            for (k=0; k<24; k=k+1) drive_cycle(0, 1300+k, 1);
            if (head != tail || out_valid)
                $fatal(1, "Drain left a response id=%0d", ID);
        end
    endtask

    integer ch, k, slot_id, group_id;
    integer blocked_before, held_before;
    initial begin
        for (slot_id=0; slot_id<2; slot_id=slot_id+1) begin
            slot_accepts[slot_id] = 0;
            for (group_id=0; group_id<GROUPS; group_id=group_id+1)
                issue_hits[slot_id][group_id] = 0;
        end
        // Each channel has a fixed, deliberately nonuniform parameter pair.
        // CHANNELS=4 still contains +/- half, Q31 maximum and Q31 minimum.
        for (ch=0; ch<CHANNELS; ch=ch+1) begin
            case (ch % 8)
                0: begin prelu_flat[ch*16+:16]=16'h8000; q31_flat[ch*32+:32]=32'h40000000; end
                1: begin prelu_flat[ch*16+:16]=16'h7fff; q31_flat[ch*32+:32]=32'hc0000000; end
                2: begin prelu_flat[ch*16+:16]=16'h4000; q31_flat[ch*32+:32]=32'h7fffffff; end
                3: begin prelu_flat[ch*16+:16]=16'hc000; q31_flat[ch*32+:32]=32'h80000000; end
                4: begin prelu_flat[ch*16+:16]=16'h0000; q31_flat[ch*32+:32]=32'h00000000; end
                // MIN_INT32 * (-1 Q15) must clip to MAX_INT32 before Q31.
                // Multiplier=1 makes the correct small output +1 observable.
                5: begin prelu_flat[ch*16+:16]=16'h8000; q31_flat[ch*32+:32]=32'h00000001; end
                // Two distinct rounds: (-1 * 0.5 Q15) then 0.5 Q31 is -1.
                6: begin prelu_flat[ch*16+:16]=16'h4000; q31_flat[ch*32+:32]=32'h40000000; end
                7: begin prelu_flat[ch*16+:16]=16'd12345; q31_flat[ch*32+:32]=32'h01000000; end
            endcase
        end
        frozen_prelu = prelu_flat;
        frozen_q31 = q31_flat;
        reset_case();
        check_empty();

        // Fill both slots, hold a third input stable, and keep the first output
        // blocked long enough for both vectors to finish in either group count.
        send_vectors(2, 0, 0, 32'h12345678);
        blocked_before = input_stalls;
        held_before = output_stalls;
        for (k=0; k<96; k=k+1) begin
            drive_cycle(1, 2, 0);
            if (in_ready !== 1'b0 || last_input_fire || tail-head != 2)
                $fatal(1, "Two full slots did not block the third vector id=%0d", ID);
        end
        if (input_stalls-blocked_before != 96 || output_stalls-held_before < 64)
            $fatal(1, "Long backpressure case did not reach required coverage id=%0d", ID);
        // First output frees slot 0. Next edge can both accept the held third
        // vector and consume slot 1; this exercises simultaneous push/pop.
        send_vectors(1, 2, 1, 32'h456789ab);
        send_vectors(45, 3, 1, 32'h98765432);
        drain();

        send_vectors(64, 1000, 1, 32'h10293847);
        drain();

        send_vectors(128, 100, 2, 32'h31415926 ^ ID);
        drain();
        send_vectors(128, 300, 2, 32'h89abcdef ^ ID);
        drain();

        // Reset while groups are still traversing the scalar arithmetic pipe.
        reset_case();
        send_vectors(2, 600, 0, 32'h10203040);
        drive_cycle(0, 602, 0);
        if (tail-head != 2 || out_valid !== 1'b0)
            $fatal(1, "Compute-in-flight reset case not established id=%0d", ID);
        reset_compute = reset_compute + 1;
        reset_case();
        check_empty();
        send_vectors(17, 620, 1, 32'h01020304);
        drain();

        // Reset with a visible blocked output and a third blocked input.
        send_vectors(2, 700, 0, 32'h66778899);
        for (k=0; k<64; k=k+1) drive_cycle(1, 702, 0);
        if (!out_valid || in_ready || !in_valid || tail-head != 2)
            $fatal(1, "Held-output reset case not established id=%0d", ID);
        reset_held_output = reset_held_output + 1;
        reset_case();
        check_empty();
        send_vectors(33, 800, 2, 32'h76543210 ^ ID);
        drain();

        for (slot_id=0; slot_id<2; slot_id=slot_id+1) begin
            if (slot_accepts[slot_id] < 3)
                $fatal(1, "Slot reuse coverage missing id=%0d slot=%0d", ID, slot_id);
            for (group_id=0; group_id<GROUPS; group_id=group_id+1)
                if (issue_hits[slot_id][group_id] == 0)
                    $fatal(1, "Shift group coverage missing id=%0d slot=%0d group=%0d",
                           ID, slot_id, group_id);
        end
        if (max_pending != 2 || input_stalls < 96 || output_stalls < 64 ||
            simultaneous_io == 0 || input_gaps == 0 || total_outputs < 300 ||
            simultaneous_capture_issue == 0 || reset_compute != 1 || reset_held_output != 1)
            $fatal(1, "Missing shared coverage id=%0d", ID);
        $display("POST_SHIFT_CONFIG_PASS id=%0d channels=%0d lanes=%0d signed=%0d prelu=%0d inputs=%0d outputs=%0d in_stall=%0d out_stall=%0d simultaneous_io=%0d capture_issue=%0d slot0=%0d slot1=%0d groups=%0d gaps=%0d cycles=%0d",
                 ID, CHANNELS, LANES, OUT_SIGNED, APPLY_PRELU, total_inputs,
                 total_outputs, input_stalls, output_stalls, simultaneous_io,
                 simultaneous_capture_issue, slot_accepts[0], slot_accepts[1], GROUPS, input_gaps, cycles);
        done = 1;
    end
endmodule

module tb_post_shift;
    reg clk = 0;
    always #5 clk = ~clk;
    wire [4:0] done;
    // Three network configurations plus one- and two-group boundaries.
    post_shift_case #(.ID(0), .CHANNELS(16), .LANES(2), .OUT_W(16),
        .OUT_SIGNED(1), .APPLY_PRELU(1)) c0 (.clk(clk), .done(done[0]));
    post_shift_case #(.ID(1), .CHANNELS(8), .LANES(1), .OUT_W(16),
        .OUT_SIGNED(1), .APPLY_PRELU(1)) c1 (.clk(clk), .done(done[1]));
    post_shift_case #(.ID(2), .CHANNELS(4), .LANES(1), .OUT_W(8),
        .OUT_SIGNED(0), .APPLY_PRELU(0)) c2 (.clk(clk), .done(done[2]));
    post_shift_case #(.ID(3), .CHANNELS(1), .LANES(1), .OUT_W(16),
        .OUT_SIGNED(1), .APPLY_PRELU(1)) c3 (.clk(clk), .done(done[3]));
    post_shift_case #(.ID(4), .CHANNELS(4), .LANES(2), .OUT_W(16),
        .OUT_SIGNED(1), .APPLY_PRELU(1)) c4 (.clk(clk), .done(done[4]));
    initial begin
        wait (done === 5'b11111);
        repeat (4) @(posedge clk);
        $display("POST_SHIFT_ALL_CONFIGS_PASS configs=5");
        $finish;
    end
    initial begin
        #500001;
        $fatal(1, "POST_SHIFT_WALL_CLOCK_TIMEOUT");
    end
endmodule

`default_nettype wire
