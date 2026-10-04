`timescale 1ns / 1ps
`default_nettype none

module tb_c_controlled_pause;
    localparam integer CLK_HZ = 100000000;
    localparam integer UART_BAUD = 25000000;
    localparam integer UART_DIV = CLK_HZ / UART_BAUD;
    localparam integer IMG_W = 96;
    localparam integer IMG_H = 54;
    localparam integer OUT_W = 192;
    localparam integer OUT_H = 108;
    localparam integer IN_BYTES = IMG_W * IMG_H;
    localparam integer OUT_BYTES = OUT_W * OUT_H;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg uart_rx = 1'b1;
    wire uart_tx;
    wire [7:0] led;
    wire dbg_frame_start, dbg_frame_done, dbg_frame_active;
    wire [31:0] dbg_expected_frame_id, dbg_frame_error_count;
    wire [31:0] dbg_uart_bytes;
    wire dbg_core_busy, dbg_core_done;
    reg [4:0] obs_control = 5'd0;
    wire [933:0] obs_snapshot_data;
    wire obs_snapshot_valid;
    wire [4:0] obs_snapshot_count;
    wire obs_snapshot_overflow;
    wire obs_pause_effective;
    wire obs_pause_forced_block;
    wire obs_clk;
    integer forced_block_cycles = 0;
    integer pause_injections = 0;
    integer pause_countdown = 0;
    reg pause_injected_this_frame = 1'b0;
    wire [7:0] tx_monitor_data;
    wire tx_monitor_valid, tx_monitor_framing_error;

    c_multiframe_top #(
        .IMG_W(IMG_W), .IMG_H(IMG_H), .OUT_W(OUT_W), .OUT_H(OUT_H),
        .STRIPE_H(64), .ROM_ADDR_W(19), .ROM_DEPTH(524288),
        .USE_MMCM(0), .CLK_HZ(CLK_HZ), .UART_BAUD(UART_BAUD),
        .OBS_TEST_PAUSE_ENABLE(1)
    ) dut (
        .sys_clk(clk), .rst_n(rst_n), .uart_rx(uart_rx), .led(led), .uart_tx(uart_tx),
        .dbg_frame_start(dbg_frame_start), .dbg_frame_done(dbg_frame_done),
        .dbg_frame_active(dbg_frame_active), .dbg_expected_frame_id(dbg_expected_frame_id),
        .dbg_frame_error_count(dbg_frame_error_count), .dbg_uart_bytes(dbg_uart_bytes),
        .dbg_core_busy(dbg_core_busy), .dbg_core_done(dbg_core_done),
        .dbg_obs_control(obs_control),
        .dbg_obs_snapshot_data(obs_snapshot_data),
        .dbg_obs_snapshot_valid(obs_snapshot_valid),
        .dbg_obs_snapshot_count(obs_snapshot_count),
        .dbg_obs_snapshot_overflow(obs_snapshot_overflow),
        .dbg_obs_pause_effective(obs_pause_effective),
        .dbg_obs_pause_forced_block(obs_pause_forced_block), .dbg_obs_clk(obs_clk)
    );

    // Decode the physical TX pin with an independent 8N1 receiver instead of
    // inferring UART start edges from arbitrary data-bit transitions.
    uart_rx #(.BAUD_DIV(UART_DIV), .DATA_W(8)) u_tx_monitor (
        .clk(clk), .rst_n(rst_n), .rx_serial(uart_tx),
        .rx_data(tx_monitor_data), .rx_valid(tx_monitor_valid),
        .rx_framing_error(tx_monitor_framing_error)
    );

    reg [7:0] impulse_in [0:IN_BYTES-1];
    reg [7:0] ramp_in [0:IN_BYTES-1];
    reg [7:0] impulse_expected [0:OUT_BYTES-1];
    reg [7:0] ramp_expected [0:OUT_BYTES-1];
    reg [7:0] captured [0:2*OUT_BYTES-1];
    integer frame_done_count = 0;
    integer received_frames = 0;
    integer uart_monitor_count = 0;
    integer uart_monitor_framing_errors = 0;
    integer errors = 0;
    integer i;
    integer fd;
    reg [7:0] rx_byte;
    reg [31:0] payload_crc;
    reg [31:0] header_crc;
    reg [31:0] crc_work;
    reg [7:0] header_bytes [0:11];

    always @(posedge clk) begin
        if (!rst_n) begin
            frame_done_count <= 0;
        end else if (dbg_frame_done) begin
            frame_done_count <= frame_done_count + 1;
            $display("FRAME_DONE count=%0d expected_id=%0d uart_bytes=%0d errors=%0d",
                     frame_done_count + 1, dbg_expected_frame_id, dbg_uart_bytes,
                     dbg_frame_error_count);
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            uart_monitor_count = 0;
            uart_monitor_framing_errors = 0;
        end else begin
            if (tx_monitor_valid) begin
                if (uart_monitor_count < 2*OUT_BYTES)
                    captured[uart_monitor_count] = tx_monitor_data;
                uart_monitor_count = uart_monitor_count + 1;
            end
            if (tx_monitor_framing_error)
                uart_monitor_framing_errors = uart_monitor_framing_errors + 1;
        end
    end

    always @(posedge clk) begin
        if (rst_n && obs_pause_forced_block)
            forced_block_cycles = forced_block_cycles + 1;
    end

    // Inject one short pause per frame only when B presents a beat that C
    // could otherwise accept. This makes the forced block causally observable.
    always @(negedge clk) begin
        if (!rst_n) begin
            obs_control = 5'd0;
            pause_countdown = 0;
            pause_injected_this_frame = 1'b0;
        end else begin
            if (dbg_frame_start)
                pause_injected_this_frame = 1'b0;
            if (obs_control[4]) begin
                if (pause_countdown > 0)
                    pause_countdown = pause_countdown - 1;
                if (pause_countdown == 0)
                    obs_control[4] = 1'b0;
            end
            if (dbg_frame_active && !pause_injected_this_frame &&
                dut.obs_b_out_valid && dut.u_core.out_ready_base && !obs_control[4]) begin
                obs_control[4] = 1'b1;
                pause_countdown = 16;
                pause_injected_this_frame = 1'b1;
                pause_injections = pause_injections + 1;
                $display("CONTROLLED_PAUSE_START frame=%0d", dbg_expected_frame_id);
            end
        end
    end

    task check_observation;
        input [3:0] slot;
        input [31:0] expected_id;
        begin
            obs_control[3:0] = slot;
            #1;
            if (obs_snapshot_valid !== 1'b1) begin
                $display("[FAIL] observation slot %0d invalid", slot);
                errors = errors + 1;
            end
            if (obs_snapshot_data[4:1] !== slot || obs_snapshot_data[36:5] !== expected_id) begin
                $display("[FAIL] observation slot/id got=%0d/%08x expected=%0d/%08x",
                         obs_snapshot_data[4:1], obs_snapshot_data[36:5], slot, expected_id);
                errors = errors + 1;
            end
            if (obs_snapshot_data[37] !== 1'b1 || obs_snapshot_data[38] !== 1'b0 ||
                obs_snapshot_data[39] !== 1'b1 || obs_snapshot_data[40] !== 1'b1 ||
                obs_snapshot_data[41] !== 1'b1 || obs_snapshot_data[933] !== 1'b0) begin
                $display("[FAIL] observation completion flags slot=%0d", slot);
                errors = errors + 1;
            end
            if (obs_snapshot_data[73:42] !== IN_BYTES ||
                obs_snapshot_data[105:74] !== OUT_BYTES ||
                obs_snapshot_data[121:106] !== 16'd2 ||
                obs_snapshot_data[129:122] !== 8'd1 ||
                obs_snapshot_data[161:130] !== OUT_BYTES) begin
                $display("[FAIL] observation stream counts slot=%0d in=%0d out=%0d stripe=%0d frame=%0d uart=%0d",
                         slot, obs_snapshot_data[73:42], obs_snapshot_data[105:74],
                         obs_snapshot_data[121:106], obs_snapshot_data[129:122],
                         obs_snapshot_data[161:130]);
                errors = errors + 1;
            end
            if (obs_snapshot_data[162] || obs_snapshot_data[163] || obs_snapshot_data[164] ||
                obs_snapshot_data[196:165] !== 32'd0 || obs_snapshot_data[228:197] !== 32'd0) begin
                $display("[FAIL] observation errors slot=%0d", slot);
                errors = errors + 1;
            end
            if (obs_snapshot_data[772:741] !== 32'd0 || obs_snapshot_data[804:773] !== 32'd0) begin
                $display("[FAIL] hold violation in slot=%0d c2b=%0d bout=%0d",
                         slot, obs_snapshot_data[772:741], obs_snapshot_data[804:773]);
                errors = errors + 1;
            end
            if (obs_snapshot_data[868:805] == 64'd0 || obs_snapshot_data[932:869] == 64'd0) begin
                $display("[FAIL] pause evidence missing in slot=%0d request=%0d forced=%0d",
                         slot, obs_snapshot_data[868:805], obs_snapshot_data[932:869]);
                errors = errors + 1;
            end
            $display("OBSERVATION_FRAME slot=%0d frame_id=%0d input=%0d output=%0d pause=%0d forced=%0d hold=%0d/%0d",
                     slot, obs_snapshot_data[36:5], obs_snapshot_data[73:42],
                     obs_snapshot_data[105:74], obs_snapshot_data[868:805],
                     obs_snapshot_data[932:869], obs_snapshot_data[772:741],
                     obs_snapshot_data[804:773]);
        end
    endtask

    function [31:0] crc32_byte;
        input [31:0] crc_in;
        input [7:0] data_in;
        reg [31:0] crc;
        integer k;
        begin
            crc = crc_in ^ {24'd0, data_in};
            for (k = 0; k < 8; k = k + 1) begin
                if (crc[0]) crc = (crc >> 1) ^ 32'hEDB88320;
                else        crc = crc >> 1;
            end
            crc32_byte = crc;
        end
    endfunction

    function [31:0] vector_payload_crc;
        input integer vector_id;
        integer k;
        reg [31:0] crc;
        begin
            crc = 32'hFFFFFFFF;
            for (k = 0; k < IN_BYTES; k = k + 1) begin
                if (vector_id == 0) crc = crc32_byte(crc, impulse_in[k]);
                else                crc = crc32_byte(crc, ramp_in[k]);
            end
            vector_payload_crc = ~crc;
        end
    endfunction

    function [31:0] header_payload_crc;
        input [95:0] bytes_0_to_11;
        integer k;
        reg [31:0] crc;
        begin
            crc = 32'hFFFFFFFF;
            for (k = 0; k < 12; k = k + 1)
                crc = crc32_byte(crc, bytes_0_to_11[k*8 +: 8]);
            header_payload_crc = ~crc;
        end
    endfunction

    task send_uart_bit;
        input value;
        integer n;
        begin
            uart_rx = value;
            for (n = 0; n < UART_DIV; n = n + 1) @(negedge clk);
        end
    endtask

    task send_uart_byte;
        input [7:0] value;
        integer bit_no;
        begin
            send_uart_bit(1'b0);
            for (bit_no = 0; bit_no < 8; bit_no = bit_no + 1)
                send_uart_bit(value[bit_no]);
            send_uart_bit(1'b1);
        end
    endtask

    task send_u32_le;
        input [31:0] value;
        begin
            send_uart_byte(value[7:0]);
            send_uart_byte(value[15:8]);
            send_uart_byte(value[23:16]);
            send_uart_byte(value[31:24]);
        end
    endtask

    task send_frame;
        input integer vector_id;
        input [31:0] frame_id;
        integer k;
        reg [31:0] pcrc;
        reg [31:0] hcrc;
        reg [95:0] hbytes;
        begin
            pcrc = vector_payload_crc(vector_id);
            hbytes = 96'd0;
            hbytes[31:0] = frame_id;
            hbytes[63:32] = IN_BYTES;
            hbytes[95:64] = pcrc;
            hcrc = header_payload_crc(hbytes);

            $display("HOST_SEND frame_id=%0d payload=%0d payload_crc=%08x header_crc=%08x",
                     frame_id, IN_BYTES, pcrc, hcrc);
            send_uart_byte(8'h53); // S
            send_uart_byte(8'h52); // R
            send_uart_byte(8'h54); // T
            send_uart_byte(8'h50); // P
            for (k = 0; k < 12; k = k + 1)
                header_bytes[k] = hbytes[k*8 +: 8];
            for (k = 0; k < 12; k = k + 1) send_uart_byte(header_bytes[k]);
            send_u32_le(hcrc);
            for (k = 0; k < IN_BYTES; k = k + 1) begin
                if (vector_id == 0) send_uart_byte(impulse_in[k]);
                else                send_uart_byte(ramp_in[k]);
            end
            uart_rx = 1'b1;
        end
    endtask

    task capture_frame;
        input integer frame_id;
        integer target;
        begin
            target = (frame_id + 1) * OUT_BYTES;
            while (uart_monitor_count < target) @(negedge clk);
            received_frames = frame_id + 1;
            $display("UART_CAPTURE frame=%0d bytes=%0d", frame_id, OUT_BYTES);
        end
    endtask

    task compare_frame;
        input integer vector_id;
        input integer frame_id;
        integer k;
        integer mismatch_count;
        integer out_fd;
        reg [7:0] expected_byte;
        begin
            mismatch_count = 0;
            if (frame_id == 0) out_fd = $fopen("actual_frame0.mem", "w");
            else               out_fd = $fopen("actual_frame1.mem", "w");
            for (k = 0; k < OUT_BYTES; k = k + 1) begin
                if (vector_id == 0) expected_byte = impulse_expected[k];
                else                expected_byte = ramp_expected[k];
                if (captured[frame_id*OUT_BYTES + k] !== expected_byte) begin
                    if (mismatch_count < 8)
                        $display("[FAIL] frame=%0d byte=%0d got=%02x expected=%02x",
                                 frame_id, k, captured[frame_id*OUT_BYTES + k], expected_byte);
                    mismatch_count = mismatch_count + 1;
                end
                if (out_fd != 0) $fdisplay(out_fd, "%02x", captured[frame_id*OUT_BYTES + k]);
            end
            if (out_fd != 0) $fclose(out_fd);
            if (mismatch_count != 0) begin
                $display("[FAIL] frame=%0d mismatches=%0d", frame_id, mismatch_count);
                errors = errors + mismatch_count;
            end else begin
                $display("FRAME_BIT_EXACT frame=%0d bytes=%0d mismatches=0", frame_id, OUT_BYTES);
            end
        end
    endtask

    initial begin
        $readmemh("tv_impulse_in.mem", impulse_in);
        $readmemh("tv_ramp_in.mem", ramp_in);
        $readmemh("tv_impulse_out.mem", impulse_expected);
        $readmemh("tv_ramp_out.mem", ramp_expected);

        repeat (8) @(posedge clk);
        rst_n = 1'b1;
        repeat (8) @(posedge clk);

        fork
            capture_frame(0);
            send_frame(0, 32'd0);
        join
        wait (frame_done_count == 1);
        compare_frame(0, 0);
        if (dbg_expected_frame_id != 1 || dbg_frame_error_count != 0 ||
            dbg_uart_bytes != OUT_BYTES || dbg_core_busy || dbg_frame_active) begin
            $display("[FAIL] after frame0 id=%0d err=%0d uart=%0d busy=%0d active=%0d",
                     dbg_expected_frame_id, dbg_frame_error_count, dbg_uart_bytes,
                     dbg_core_busy, dbg_frame_active);
            errors = errors + 1;
        end

        // Deliberately keep rst_n high: this verifies consecutive requests.
        fork
            capture_frame(1);
            send_frame(1, 32'd1);
        join
        wait (frame_done_count == 2);
        compare_frame(1, 1);
        if (dbg_expected_frame_id != 2 || dbg_frame_error_count != 0 ||
            dbg_uart_bytes != 2*OUT_BYTES || dbg_core_busy || dbg_frame_active ||
            received_frames != 2 || uart_monitor_count != 2*OUT_BYTES ||
            uart_monitor_framing_errors != 0) begin
            $display("[FAIL] after frame1 id=%0d err=%0d uart=%0d busy=%0d active=%0d rxframes=%0d monitor_bytes=%0d framing=%0d",
                     dbg_expected_frame_id, dbg_frame_error_count, dbg_uart_bytes,
                     dbg_core_busy, dbg_frame_active, received_frames,
                     uart_monitor_count, uart_monitor_framing_errors);
            errors = errors + 1;
        end

        if (pause_injections != 2 || forced_block_cycles < 2 ||
            obs_snapshot_count != 5'd2 || obs_snapshot_overflow !== 1'b0) begin
            $display("[FAIL] controlled pause summary injections=%0d forced_cycles=%0d snapshots=%0d overflow=%0d",
                     pause_injections, forced_block_cycles, obs_snapshot_count, obs_snapshot_overflow);
            errors = errors + 1;
        end
        check_observation(4'd0, 32'd0);
        check_observation(4'd1, 32'd1);

        if (errors == 0) begin
            $display("RESULT: PASS controlled pause with two consecutive byte-exact UART frames; forced_block_cycles=%0d",
                     forced_block_cycles);
            $finish;
        end else begin
            $display("RESULT: FAIL errors=%0d", errors);
            $fatal(1, "multi-frame UART regression failed");
        end
    end

    integer progress_cycles = 0;
    integer accepted_inputs = 0;
    always @(posedge clk) begin
        progress_cycles = progress_cycles + 1;
        if (rst_n && dut.u_core.in_valid && dut.u_core.in_ready)
            accepted_inputs = accepted_inputs + 1;
        if ((progress_cycles % 100000) == 0)
            $display("PROGRESS t=%0t cycles=%0d accepted_inputs=%0d frame_done=%0d uart_bytes=%0d active=%0d busy=%0d",
                     $time, progress_cycles, accepted_inputs, frame_done_count,
                     uart_monitor_count, dbg_frame_active, dbg_core_busy);
    end

    initial begin
        repeat (25000000) @(posedge clk);
        $display("[FAIL] global timeout frame_done=%0d uart_bytes=%0d core_busy=%0d active=%0d errors=%0d",
                 frame_done_count, dbg_uart_bytes, dbg_core_busy, dbg_frame_active,
                 dbg_frame_error_count);
        $fatal(1, "global timeout");
    end
endmodule

`default_nettype wire
