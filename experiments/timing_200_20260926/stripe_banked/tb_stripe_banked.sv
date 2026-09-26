`timescale 1ns / 1ps
`default_nettype none

// Direct memory test: candidate vs. unpartitioned two-stage reference, plus
// an independent memory/response model. The pingpong reset contract is tested
// separately by reusing tb_stripe_pipe with this candidate memory module.
module stripe_banked_case #(
    parameter integer ID = 0,
    parameter integer DEPTH = 122880
)(input wire clk, output reg done = 0);
    localparam integer ADDR_W = (DEPTH+1 <= 1) ? 1 : $clog2(DEPTH+1);
    localparam integer BANKS = (DEPTH+4095)/4096;
    localparam integer MAX_CYCLES = 300000;
    reg wr_en = 0, rd_en = 0;
    reg [ADDR_W-1:0] wr_addr = 0, rd_addr = 0;
    reg [7:0] wr_data = 0;
    wire [7:0] rd_data, reference_data;
    stripe_buffer #(.WIDTH(DEPTH), .ROWS(1), .DATA_W(8), .ADDR_W(ADDR_W)) dut (
        .clk(clk), .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
        .rd_en(rd_en), .rd_addr(rd_addr), .rd_data(rd_data)
    );
    stripe_buffer_reference #(.WIDTH(DEPTH), .ROWS(1), .DATA_W(8), .ADDR_W(ADDR_W)) original (
        .clk(clk), .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
        .rd_en(rd_en), .rd_addr(rd_addr), .rd_data(reference_data)
    );

    reg [7:0] expected_memory [0:DEPTH-1];
    reg [7:0] expected_q0 = 0, expected_q1 = 0;
    reg known_q0 = 0, known_q1 = 0;
    integer cycles = 0, writes = 0, reads = 0, compared = 0;
    integer invalid_reads = 0, invalid_writes = 0;
    integer same_address_rw = 0, different_address_rw = 0;
    integer last_address_reads = 0, cross_forward = 0, cross_reverse = 0;
    integer different_bank_adjacent = 0;
    reg previous_read = 0;
    integer previous_address = 0;
    reg seen_bank [0:BANKS-1];
    reg initialized = 0;
    integer monitor_bank;

    // Process read before write to model read-first behavior independently.
    // expected_q1 gets the old q0 every edge, including disabled/invalid reads.
    // Once initialized/read, every following cycle must match, so invalid read
    // enables and bank-selector hold behavior are checked, not just valid data.
    always @(posedge clk) begin
        cycles = cycles + 1;
        if (cycles > MAX_CYCLES) $fatal(1, "STRIPE_BANKED_TIMEOUT id=%0d", ID);
        expected_q1 = expected_q0;
        known_q1 = known_q0;
        if (rd_en && rd_addr < DEPTH) begin
            if (!initialized) $fatal(1, "Test read before full initialization id=%0d", ID);
            expected_q0 = expected_memory[rd_addr];
            known_q0 = 1;
            reads = reads + 1;
            monitor_bank = rd_addr / 4096;
            seen_bank[monitor_bank] = 1;
            if (rd_addr == DEPTH-1) last_address_reads = last_address_reads + 1;
            if (previous_read && previous_address/4096 != monitor_bank)
                different_bank_adjacent = different_bank_adjacent + 1;
            if (previous_read && previous_address == 4095 && rd_addr == 4096)
                cross_forward = cross_forward + 1;
            if (previous_read && previous_address == 4096 && rd_addr == 4095)
                cross_reverse = cross_reverse + 1;
            previous_read = 1;
            previous_address = rd_addr;
        end else begin
            previous_read = 0;
            if (rd_en) invalid_reads = invalid_reads + 1;
        end
        if (wr_en && wr_addr < DEPTH) begin
            if (rd_en && rd_addr < DEPTH) begin
                if (wr_addr == rd_addr) same_address_rw = same_address_rw + 1;
                else different_address_rw = different_address_rw + 1;
            end
            expected_memory[wr_addr] = wr_data;
            writes = writes + 1;
        end else if (wr_en) invalid_writes = invalid_writes + 1;
        #1;
        if (known_q1) begin
            if (rd_data !== expected_q1 || reference_data !== expected_q1)
                $fatal(1, "STRIPE_BANKED_MISMATCH id=%0d cycle=%0d got=%02x original=%02x expected=%02x",
                       ID, cycles, rd_data, reference_data, expected_q1);
            compared = compared + 1;
        end
    end

    function automatic [7:0] pattern(input integer address_value, input integer version);
        integer value;
        begin
            // Include high address bits so 4096-spaced locations differ.
            value = address_value*29 + (address_value >> 8)*17 +
                    (address_value >> 12)*53 + version*67;
            pattern = value[7:0];
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
    task automatic step(
        input bit write_enable, input integer write_address, input [7:0] data_value,
        input bit read_enable, input integer read_address
    );
        begin
            @(negedge clk);
            wr_en = write_enable;
            wr_addr = write_address;
            wr_data = data_value;
            rd_en = read_enable;
            rd_addr = read_address;
            @(posedge clk);
            #2;
        end
    endtask

    integer address_value, k, bank_number, write_address, read_address;
    reg [31:0] random_state;
    initial begin
        for (bank_number=0; bank_number<BANKS; bank_number=bank_number+1)
            seen_bank[bank_number] = 0;
        // Initialize every byte, then continuously read every address. The
        // production case crosses all 29 internal bank boundaries.
        for (address_value=0; address_value<DEPTH; address_value=address_value+1)
            step(1, address_value, pattern(address_value, 0), 0, 0);
        initialized = 1;
        for (address_value=0; address_value<DEPTH; address_value=address_value+1)
            step(0, 0, 0, 1, address_value);
        step(0, 0, 0, 0, 0);
        step(0, 0, 0, 0, 0);

        if (DEPTH > 4096) begin
            step(0, 0, 0, 1, 4095);
            step(0, 0, 0, 1, 4096);
            step(0, 0, 0, 1, 4095);
            for (k=0; k<8; k=k+1) begin
                step(0, 0, 0, 1, 0);
                step(0, 0, 0, 1, DEPTH-1);
                step(0, 0, 0, 1, 4096);
            end
        end

        // Read-first collision must return the old byte, then the new byte on
        // the next request. Addresses cover first and last words of the memory.
        step(1, 0, pattern(0, 1), 1, 0);
        step(0, 0, 0, 1, 0);
        step(1, DEPTH-1, pattern(DEPTH-1, 2), 1, DEPTH-1);
        step(0, 0, 0, 1, DEPTH-1);
        if (DEPTH > 1) begin
            step(1, 0, pattern(0, 3), 1, DEPTH-1);
            step(1, DEPTH-1, pattern(DEPTH-1, 3), 1, 0);
        end

        // Invalid writes must not wrap to address zero. Invalid reads must
        // preserve the prior response even when memory[0] changes meanwhile.
        step(0, 0, 0, 1, 0);
        step(0, 0, 0, 0, 0);
        step(1, DEPTH, 8'ha5, 0, 0);
        step(0, 0, 0, 1, 0);
        step(0, 0, 0, 0, 0);
        step(1, 0, pattern(0, 4), 0, 0);
        step(0, 0, 0, 1, DEPTH);
        step(0, 0, 0, 0, DEPTH);
        step(0, 0, 0, 1, 0);
        step(0, 0, 0, 0, 0);

        random_state = 32'h32a1674f ^ ID;
        for (k=0; k<2000; k=k+1) begin
            random_state = next_random(random_state);
            write_address = (random_state & 32'h7fffffff) % DEPTH;
            random_state = next_random(random_state);
            read_address = (random_state & 32'h7fffffff) % DEPTH;
            if (k % 31 == 0) write_address = DEPTH;
            if (k % 29 == 0) read_address = DEPTH;
            if (k % 11 == 0 && write_address < DEPTH) read_address = write_address;
            step(random_state[0], write_address, pattern(write_address, k+5),
                 random_state[1] | random_state[2], read_address);
        end
        step(0, 0, 0, 1, DEPTH-1);
        repeat (8) step(0, 0, 0, 0, 0);
        for (bank_number=0; bank_number<BANKS; bank_number=bank_number+1)
            if (!seen_bank[bank_number])
                $fatal(1, "Bank was never read id=%0d bank=%0d", ID, bank_number);
        if (last_address_reads == 0 || invalid_reads == 0 || invalid_writes == 0 ||
            same_address_rw == 0 || compared < DEPTH ||
            (DEPTH > 1 && different_address_rw == 0) ||
            (BANKS > 1 && (cross_forward == 0 || cross_reverse == 0 || different_bank_adjacent == 0)))
            $fatal(1, "Missing boundary/enable/collision coverage id=%0d", ID);
        $display("STRIPE_BANKED_CONFIG_PASS id=%0d depth=%0d banks=%0d addr_w=%0d writes=%0d reads=%0d compared=%0d same_rw=%0d different_rw=%0d invalid_r=%0d invalid_w=%0d forward=%0d reverse=%0d bank_switch=%0d",
                 ID, DEPTH, BANKS, ADDR_W, writes, reads, compared, same_address_rw,
                 different_address_rw, invalid_reads, invalid_writes, cross_forward,
                 cross_reverse, different_bank_adjacent);
        done = 1;
    end
endmodule

module tb_stripe_banked;
    reg clk = 0;
    always #5 clk = ~clk;
    wire [4:0] done;
    stripe_banked_case #(.ID(0), .DEPTH(122880)) full (.clk(clk), .done(done[0]));
    stripe_banked_case #(.ID(1), .DEPTH(8197)) tail5 (.clk(clk), .done(done[1]));
    stripe_banked_case #(.ID(2), .DEPTH(4096)) exact1 (.clk(clk), .done(done[2]));
    stripe_banked_case #(.ID(3), .DEPTH(32)) small_case (.clk(clk), .done(done[3]));
    stripe_banked_case #(.ID(4), .DEPTH(1)) single (.clk(clk), .done(done[4]));
    initial begin
        wait (done === 5'b11111);
        repeat (4) @(posedge clk);
        $display("STRIPE_BANKED_ALL_CONFIGS_PASS configs=5");
        $finish;
    end
    initial begin
        #3000001;
        $fatal(1, "STRIPE_BANKED_WALL_CLOCK_TIMEOUT");
    end
endmodule

`default_nettype wire
