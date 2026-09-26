`timescale 1ns / 1ps
`default_nettype none

// Standalone contract test for the stripe_pipe overlay.
// E0: rd_req && rd_busy is accepted at the rising edge.
// E1: rd_valid/data/start/last become visible after the next rising edge.
// E2: a synchronous consumer samples that response.
//
// The reference FIFO is populated ONLY from accepted external writes. Expected
// responses are popped ONLY by accepted external read requests. No DUT internal
// state or DUT output data is used to construct the expected data/markers.
// Inputs have one owner and change on falling edges. The checker samples the
// request at a rising edge, then checks post-NBA outputs at #1. The driver reads
// checker results at #2, so its bookkeeping cannot race the checker.
module tb_stripe_pipe;
    localparam integer WIDTH = 8;
    localparam integer ROWS = 4;
    localparam integer DEPTH = WIDTH * ROWS;
    localparam integer DATA_W = 8;
    localparam integer ADDR_W = $clog2(DEPTH + 1);
    localparam integer MAX_STRIPES = 1024;
    localparam integer MAX_CYCLES = 100000;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg wr_push = 1'b0;
    reg [DATA_W-1:0] wr_data = 0;
    reg [ADDR_W-1:0] wr_stripe_len = 1;
    reg rd_req = 1'b0;
    // Test-driver intent, distinct from wr_push, which is the accepted transfer.
    reg write_offer = 1'b0;

    wire wr_ready, wr_ready_nxt;
    wire rd_avail, rd_valid, rd_start, rd_last, rd_busy;
    wire [DATA_W-1:0] rd_data;
    wire [ADDR_W-1:0] rd_len;
    wire [1:0] buf_state;
    wire overflow_err;

    pingpong_buffer #(
        .WIDTH(WIDTH), .ROWS(ROWS), .DATA_W(DATA_W), .ADDR_W(ADDR_W)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .wr_push(wr_push), .wr_data(wr_data), .wr_stripe_len(wr_stripe_len),
        .wr_ready(wr_ready), .wr_ready_nxt(wr_ready_nxt),
        .rd_req(rd_req), .rd_avail(rd_avail), .rd_valid(rd_valid),
        .rd_data(rd_data), .rd_start(rd_start), .rd_last(rd_last),
        .rd_len(rd_len), .rd_busy(rd_busy),
        .buf_state(buf_state), .overflow_err(overflow_err)
    );

    // A completed stripe enters the reference FIFO only on its final write.
    reg [7:0] expected_bytes [0:MAX_STRIPES*DEPTH-1];
    integer expected_lengths [0:MAX_STRIPES-1];
    integer written_stripes = 0;
    integer write_pos = 0;
    integer requested_stripes = 0;
    integer request_pos = 0;

    // pipe_* is the request sampled at the previous rising edge. Thus checking
    // its value after this edge enforces precisely the extra response cycle.
    reg pipe_valid = 1'b0;
    reg [7:0] pipe_data = 0;
    reg pipe_first = 1'b0;
    reg pipe_last = 1'b0;
    integer pipe_length = 0;
    reg check_valid;
    reg [7:0] check_data;
    reg check_first, check_last;
    integer check_length;
    reg accept_read, accept_write;
    reg previous_accept_read = 1'b0;

    integer cycle_count = 0;
    integer latest_last_request_cycle = -100;
    integer last_request_cycle = -100;
    reg last_write_accepted = 1'b0;
    reg last_read_accepted = 1'b0;
    integer total_writes = 0;
    integer total_requests = 0;
    integer total_responses = 0;
    integer epoch_writes = 0;
    integer epoch_requests = 0;
    integer epoch_responses = 0;
    integer coverage_single = 0;
    integer coverage_short = 0;
    integer coverage_full = 0;
    integer coverage_consecutive_reads = 0;
    integer coverage_simultaneous_rw = 0;
    integer coverage_blocked_write = 0;
    integer coverage_earliest_reuse = 0;
    integer coverage_reset_stage1 = 0;
    integer coverage_reset_stage2 = 0;
    integer coverage_random_seeds = 0;

    always @(posedge clk) begin
        cycle_count = cycle_count + 1;
        if (cycle_count > MAX_CYCLES)
            $fatal(1, "TIMEOUT cycle=%0d written=%0d requested=%0d pos=%0d",
                   cycle_count, written_stripes, requested_stripes, request_pos);

        if (!rst_n) begin
            written_stripes = 0;
            write_pos = 0;
            requested_stripes = 0;
            request_pos = 0;
            pipe_valid = 1'b0;
            pipe_data = 0;
            pipe_first = 1'b0;
            pipe_last = 1'b0;
            pipe_length = 0;
            previous_accept_read = 1'b0;
            last_write_accepted = 1'b0;
            last_read_accepted = 1'b0;
            latest_last_request_cycle = -100;
            last_request_cycle = -100;
            epoch_writes = 0;
            epoch_requests = 0;
            epoch_responses = 0;
            #1;
            if (rd_valid !== 1'b0 || rd_start !== 1'b0 || rd_last !== 1'b0)
                $fatal(1, "Reset did not clear response qualifiers, cycle=%0d", cycle_count);
        end else begin
            if ($isunknown({wr_ready, rd_busy, rd_avail, overflow_err}))
                $fatal(1, "Unknown control output at cycle=%0d", cycle_count);
            if (overflow_err !== 1'b0)
                $fatal(1, "Unexpected overflow at cycle=%0d", cycle_count);
            if (wr_push && !wr_ready)
                $fatal(1, "Test driver violated write handshake at cycle=%0d", cycle_count);

            accept_read = rd_req && rd_busy;
            accept_write = wr_push && wr_ready;
            last_read_accepted = accept_read;
            last_write_accepted = accept_write;
            if (write_offer && !wr_ready)
                coverage_blocked_write = coverage_blocked_write + 1;
            if (accept_read && previous_accept_read)
                coverage_consecutive_reads = coverage_consecutive_reads + 1;
            if (accept_read && accept_write)
                coverage_simultaneous_rw = coverage_simultaneous_rw + 1;
            previous_accept_read = accept_read;

            // Save the OLD pipeline entry before inserting this edge's request.
            check_valid = pipe_valid;
            check_data = pipe_data;
            check_first = pipe_first;
            check_last = pipe_last;
            check_length = pipe_length;
            pipe_valid = 1'b0;
            pipe_first = 1'b0;
            pipe_last = 1'b0;

            // Consume from already-complete stripes before adding this edge's
            // write. A stripe finishing now cannot already be the active read.
            if (accept_read) begin
                if (requested_stripes >= written_stripes)
                    $fatal(1, "Read without a completed reference stripe, cycle=%0d", cycle_count);
                if (rd_len !== expected_lengths[requested_stripes])
                    $fatal(1, "rd_len mismatch at request: got=%0d expected=%0d cycle=%0d",
                           rd_len, expected_lengths[requested_stripes], cycle_count);
                pipe_valid = 1'b1;
                pipe_data = expected_bytes[requested_stripes*DEPTH + request_pos];
                pipe_first = (request_pos == 0);
                pipe_length = expected_lengths[requested_stripes];
                pipe_last = (request_pos == pipe_length-1);
                last_request_cycle = cycle_count;
                total_requests = total_requests + 1;
                epoch_requests = epoch_requests + 1;
                if (pipe_last) begin
                    latest_last_request_cycle = cycle_count;
                    request_pos = 0;
                    requested_stripes = requested_stripes + 1;
                end else begin
                    request_pos = request_pos + 1;
                end
            end

            if (accept_write) begin
                if (written_stripes >= MAX_STRIPES)
                    $fatal(1, "Reference FIFO capacity exceeded");
                if ($isunknown({wr_stripe_len, wr_data}) ||
                    wr_stripe_len < 1 || wr_stripe_len > DEPTH)
                    $fatal(1, "Invalid write value/length at cycle=%0d", cycle_count);
                if (write_pos == 0)
                    expected_lengths[written_stripes] = wr_stripe_len;
                else if (wr_stripe_len !== expected_lengths[written_stripes])
                    $fatal(1, "Driver changed stripe length mid-stripe");
                expected_bytes[written_stripes*DEPTH + write_pos] = wr_data;
                total_writes = total_writes + 1;
                epoch_writes = epoch_writes + 1;
                if (write_pos == expected_lengths[written_stripes]-1) begin
                    write_pos = 0;
                    written_stripes = written_stripes + 1;
                end else begin
                    write_pos = write_pos + 1;
                end
            end

            #1;
            if (rd_valid !== check_valid)
                $fatal(1, "Response latency/valid mismatch: got=%b expected=%b cycle=%0d",
                       rd_valid, check_valid, cycle_count);
            // Require zero markers on invalid cycles too. This detects stale
            // first/last pulses as well as spurious markers in a stripe body.
            if (rd_start !== check_first || rd_last !== check_last)
                $fatal(1, "Marker mismatch: first=%b/%b last=%b/%b cycle=%0d",
                       rd_start, check_first, rd_last, check_last, cycle_count);
            if (check_valid) begin
                if (rd_data !== check_data)
                    $fatal(1, "FIFO data mismatch: got=%02x expected=%02x cycle=%0d",
                           rd_data, check_data, cycle_count);
                total_responses = total_responses + 1;
                epoch_responses = epoch_responses + 1;
                if (check_last) begin
                    if (check_length == 1)
                        coverage_single = coverage_single + 1;
                    else if (check_length == DEPTH)
                        coverage_full = coverage_full + 1;
                    else
                        coverage_short = coverage_short + 1;
                end
            end
        end
    end

    function automatic [7:0] payload(input integer stripe_id, input integer index);
        reg [31:0] value;
        begin
            value = stripe_id*67 + index*29 + (index >> 2)*17;
            payload = value[7:0] ^ {index[3:0], stripe_id[3:0]};
        end
    endfunction

    function automatic [31:0] next_random(input [31:0] old_state);
        reg [31:0] value;
        begin
            value = old_state ^ (old_state << 13);
            value = value ^ (value >> 17);
            next_random = value ^ (value << 5);
        end
    endfunction

    task automatic tick(
        input bit offer_write,
        input [7:0] data_value,
        input integer stripe_length,
        input bit request_read
    );
        begin
            @(negedge clk);
            write_offer = offer_write;
            wr_data = data_value;
            wr_stripe_len = stripe_length;
            wr_push = offer_write && wr_ready;
            rd_req = request_read;
            @(posedge clk);
            #2;
        end
    endtask

    task automatic reset_dut;
        begin
            @(negedge clk);
            rst_n = 1'b0;
            write_offer = 1'b0;
            wr_push = 1'b0;
            rd_req = 1'b0;
            wr_data = 0;
            wr_stripe_len = 1;
            // The reset is asynchronous: assert between request/capture edges
            // and verify qualifiers clear without waiting for another posedge.
            #1;
            if (rd_valid !== 1'b0 || rd_start !== 1'b0 || rd_last !== 1'b0)
                $fatal(1, "Asynchronous reset left a stale response visible");
            repeat (3) begin
                @(posedge clk);
                #2;
            end
            @(negedge clk);
            rst_n = 1'b1;
        end
    endtask

    task automatic idle_cycles(input integer count, input bit request_read);
        integer k;
        begin
            for (k=0; k<count; k=k+1)
                tick(0, 0, 1, request_read);
        end
    endtask

    task automatic write_stripe(input integer stripe_id, input integer length);
        integer index;
        begin
            index = 0;
            while (index < length) begin
                tick(1, payload(stripe_id, index), length, 0);
                if (last_write_accepted)
                    index = index + 1;
            end
        end
    endtask

    task automatic wait_read_active;
        begin
            while (!rd_busy)
                tick(0, 0, 1, 0);
        end
    endtask

    task automatic drain_all;
        begin
            if (write_pos != 0)
                $fatal(1, "drain_all called with a partial reference stripe");
            while (requested_stripes != written_stripes || pipe_valid ||
                   rd_valid || rd_busy || rd_avail)
                tick(0, 0, 1, 1);
            // Leave read requests high while empty to check they create no
            // phantom responses, then allow all visible outputs to settle.
            idle_cycles(5, 1);
            idle_cycles(3, 0);
            if (epoch_writes != epoch_requests || epoch_requests != epoch_responses)
                $fatal(1, "Drain count mismatch: writes=%0d requests=%0d responses=%0d",
                       epoch_writes, epoch_requests, epoch_responses);
        end
    endtask

    task automatic check_empty_after_reset;
        begin
            idle_cycles(6, 1);
            if (rd_avail !== 1'b0 || rd_busy !== 1'b0 || rd_valid !== 1'b0 ||
                epoch_requests != 0 || epoch_responses != 0)
                $fatal(1, "Old stripe/response survived reset");
            idle_cycles(2, 0);
        end
    endtask

    task automatic random_run(input [31:0] seed, input integer id_base);
        reg [31:0] random_state;
        integer stripe_index, index, length, step;
        bit want_write, want_read;
        begin
            $display("Random seed=%08x", seed);
            reset_dut();
            check_empty_after_reset();
            random_state = seed;
            stripe_index = 0;
            index = 0;
            length = 1;
            step = 0;
            while (stripe_index < 64) begin
                random_state = next_random(random_state);
                want_write = (random_state[3:0] != 0);
                // Initial hold fills both banks. Periodic long stalls plus
                // random gaps exercise full backpressure and partial drains.
                want_read = (step >= 120) && ((step % 83) >= 25) &&
                            (random_state[7:4] >= 3);
                tick(want_write, payload(id_base+stripe_index, index), length, want_read);
                if (last_write_accepted) begin
                    if (index == length-1) begin
                        index = 0;
                        stripe_index = stripe_index + 1;
                        case (stripe_index % 4)
                            0: length = 1;
                            1: length = 5;
                            2: length = DEPTH;
                            default: length = 2 + (random_state[15:8] % (DEPTH-2));
                        endcase
                    end else begin
                        index = index + 1;
                    end
                end
                step = step + 1;
            end
            drain_all();
            coverage_random_seeds = coverage_random_seeds + 1;
        end
    endtask

    integer index, k;
    integer blocked_before;
    initial begin
        $display("stripe_pipe: independent FIFO scoreboard, depth=%0d", DEPTH);
        reset_dut();
        check_empty_after_reset();

        $display("Directed: one-byte stripe (first and last on the same response)");
        write_stripe(1, 1);
        drain_all();

        $display("Directed: short stripe with read-request gaps");
        write_stripe(2, 7);
        wait_read_active();
        for (k=0; k<7; k=k+1) begin
            tick(0, 0, 1, 1);
            if (!last_read_accepted)
                $fatal(1, "Expected directed short-stripe request to be accepted");
            idle_cycles(k % 3 + 1, 0);
        end
        drain_all();

        $display("Directed: two full banks, backpressure, earliest reuse, simultaneous R/W");
        write_stripe(3, DEPTH);
        write_stripe(4, DEPTH);
        blocked_before = coverage_blocked_write;
        for (k=0; k<12; k=k+1) begin
            tick(1, payload(5, 0), DEPTH, 0);
            if (last_write_accepted || wr_ready !== 1'b0)
                $fatal(1, "Both full banks failed to apply write backpressure");
        end
        if (coverage_blocked_write - blocked_before != 12)
            $fatal(1, "Directed full-bank stall was not exercised");
        index = 0;
        while (index < DEPTH) begin
            tick(1, payload(5, index), DEPTH, 1);
            if (last_write_accepted) begin
                if (index == 0) begin
                    // E0 last read; E1 clear full; E2 writer switches bank;
                    // E3 is the earliest legal new write in the original
                    // release protocol. This checks externally visible reuse.
                    if (cycle_count != latest_last_request_cycle + 3)
                        $fatal(1, "Reuse was not earliest legal cycle: write=%0d last_req=%0d",
                               cycle_count, latest_last_request_cycle);
                    coverage_earliest_reuse = coverage_earliest_reuse + 1;
                end
                index = index + 1;
            end
        end
        drain_all();

        random_run(32'h12ab34cd, 100);
        random_run(32'h6d2b79f5, 300);
        random_run(32'hf00d1234, 500);

        $display("Reset: request stage occupied, output stage empty");
        reset_dut();
        write_stripe(701, 7);
        wait_read_active();
        tick(0, 0, 1, 1); // E0: only the first pipeline stage is occupied.
        if (!last_read_accepted || !pipe_valid || rd_valid !== 1'b0)
            $fatal(1, "Failed to establish request-stage reset case");
        coverage_reset_stage1 = coverage_reset_stage1 + 1;
        reset_dut();       // Assert on E0's following negedge, before E1.
        check_empty_after_reset();
        write_stripe(702, 1);
        write_stripe(703, DEPTH);
        drain_all();

        $display("Reset: output stage occupied before downstream capture");
        reset_dut();
        write_stripe(801, 7);
        wait_read_active();
        tick(0, 0, 1, 1); // E0: request first byte.
        tick(0, 0, 1, 0); // E1: only the output stage remains occupied.
        if (last_read_accepted || pipe_valid || rd_valid !== 1'b1 || rd_start !== 1'b1)
            $fatal(1, "Failed to establish output-stage reset case");
        coverage_reset_stage2 = coverage_reset_stage2 + 1;
        reset_dut();       // Assert between E1 and E2, before consumer capture.
        check_empty_after_reset();
        write_stripe(802, 1);
        write_stripe(803, 17);
        drain_all();

        if (coverage_single == 0 || coverage_short == 0 || coverage_full == 0 ||
            coverage_consecutive_reads == 0 || coverage_simultaneous_rw == 0 ||
            coverage_blocked_write == 0 || coverage_earliest_reuse != 1 ||
            coverage_reset_stage1 != 1 || coverage_reset_stage2 != 1 ||
            coverage_random_seeds != 3)
            $fatal(1, "Required coverage was not completed");

        $display("Coverage single=%0d short=%0d full=%0d consecutive=%0d simultaneous_rw=%0d blocked=%0d reuse=%0d reset1=%0d reset2=%0d seeds=%0d",
                 coverage_single, coverage_short, coverage_full,
                 coverage_consecutive_reads, coverage_simultaneous_rw,
                 coverage_blocked_write, coverage_earliest_reuse,
                 coverage_reset_stage1, coverage_reset_stage2, coverage_random_seeds);
        // Totals include intentionally abandoned data around reset; equality is
        // instead checked per drained epoch by drain_all().
        $display("Totals writes=%0d requests=%0d visible_responses=%0d cycles=%0d",
                 total_writes, total_requests, total_responses, cycle_count);
        $display("STRIPE_PIPE_UNIT_TEST_PASS");
        $finish;
    end

    // Independent wall-clock guard, including accidental clock/driver deadlock.
    initial begin
        #(MAX_CYCLES * 10 + 100);
        $fatal(1, "WALL_CLOCK_TIMEOUT");
    end
endmodule

`default_nettype wire
