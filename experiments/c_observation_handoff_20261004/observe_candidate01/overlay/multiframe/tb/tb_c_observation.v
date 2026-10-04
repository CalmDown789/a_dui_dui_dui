`timescale 1ns / 1ps
module tb_c_observation;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n;
    reg frame_start;
    reg session_done;
    reg [31:0] expected_frame_id;
    reg [31:0] uart_bytes;
    reg core_busy;
    reg core_done;
    reg uart_final_idle;
    reg core_proto_error;
    reg core_overflow_error;
    reg loader_protocol_error;
    reg [31:0] loader_frame_error_count;
    reg [31:0] uart_framing_error_count;
    reg c2b_valid;
    reg c2b_ready;
    reg [7:0] c2b_data;
    reg b_out_valid;
    reg [7:0] b_out_data;
    reg b_out_ready;
    reg b_stripe_last;
    reg b_frame_last;
    reg pause_active;
    reg pause_forced_block;
    reg [3:0] snapshot_select;
    wire [933:0] snapshot_selected_data;
    wire snapshot_selected_valid;
    wire [4:0] snapshot_count;
    wire snapshot_overflow;

    c_observation #(
        .EXPECTED_INPUTS(3),
        .EXPECTED_OUTPUTS(3),
        .SNAPSHOT_COUNT(2)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .frame_start(frame_start), .session_done(session_done),
        .expected_frame_id(expected_frame_id), .uart_bytes(uart_bytes),
        .core_busy(core_busy), .core_done(core_done),
        .uart_final_idle(uart_final_idle),
        .core_proto_error(core_proto_error),
        .core_overflow_error(core_overflow_error),
        .loader_protocol_error(loader_protocol_error),
        .loader_frame_error_count(loader_frame_error_count),
        .uart_framing_error_count(uart_framing_error_count),
        .c2b_valid(c2b_valid), .c2b_ready(c2b_ready), .c2b_data(c2b_data),
        .b_out_valid(b_out_valid), .b_out_data(b_out_data),
        .b_out_ready(b_out_ready), .b_stripe_last(b_stripe_last),
        .b_frame_last(b_frame_last), .pause_active(pause_active),
        .pause_forced_block(pause_forced_block),
        .snapshot_select(snapshot_select),
        .snapshot_selected_data(snapshot_selected_data),
        .snapshot_selected_valid(snapshot_selected_valid),
        .snapshot_count(snapshot_count), .snapshot_overflow(snapshot_overflow)
    );

    task defaults;
    begin
        frame_start = 0; session_done = 0; expected_frame_id = 0; uart_bytes = 0;
        core_busy = 0; core_done = 0; uart_final_idle = 0;
        core_proto_error = 0; core_overflow_error = 0; loader_protocol_error = 0;
        loader_frame_error_count = 0; uart_framing_error_count = 0;
        c2b_valid = 0; c2b_ready = 0; c2b_data = 0;
        b_out_valid = 0; b_out_data = 0; b_out_ready = 0;
        b_stripe_last = 0; b_frame_last = 0;
        pause_active = 0; pause_forced_block = 0; snapshot_select = 0;
    end
    endtask

    task start_empty_frame;
        input [31:0] fid;
    begin
        @(negedge clk);
        frame_start = 1; expected_frame_id = fid; core_busy = 1;
        @(posedge clk); #1;
        @(negedge clk);
        frame_start = 0; core_busy = 0; core_done = 1;
        session_done = 1; uart_final_idle = 1;
        @(posedge clk); #1;
        @(negedge clk);
        session_done = 0; core_done = 0; uart_final_idle = 0;
    end
    endtask

    initial begin
        rst_n = 0;
        defaults();
        repeat (2) @(posedge clk);
        @(negedge clk); rst_n = 1;

        // Frame start itself carries the first accepted input and output.
        @(negedge clk);
        frame_start = 1; expected_frame_id = 32'h1234abcd; uart_bytes = 10;
        core_busy = 1; c2b_valid = 1; c2b_ready = 1; c2b_data = 8'h10;
        b_out_valid = 1; b_out_ready = 1; b_out_data = 8'h20;
        b_stripe_last = 1; b_frame_last = 0;
        @(posedge clk); #1;

        // Two stalled cycles, with an intentional payload and sideband change.
        @(negedge clk);
        frame_start = 0; c2b_ready = 0; c2b_data = 8'h30;
        b_out_ready = 0; b_out_data = 8'h40; b_stripe_last = 1; b_frame_last = 0;
        @(posedge clk); #1;
        @(negedge clk);
        c2b_data = 8'h31; b_out_data = 8'h41;
        b_stripe_last = 0; b_frame_last = 1;
        @(posedge clk); #1;

        // Stable release and second handshake on both stream boundaries.
        @(negedge clk);
        c2b_ready = 1; b_out_ready = 1;
        @(posedge clk); #1;

        // One cycle where C has no new input while B is blocked: a joint stall.
        @(negedge clk);
        c2b_valid = 0; c2b_ready = 0; core_busy = 1;
        b_out_data = 8'h55; b_stripe_last = 1; b_frame_last = 0;
        b_frame_last = 1; b_out_ready = 0; pause_active = 1; pause_forced_block = 1;
        @(posedge clk); #1;

        // Final input/output handshakes and core_done are counted on this edge.
        @(negedge clk);
        c2b_valid = 1; c2b_ready = 1; c2b_data = 8'h60;
        b_out_ready = 1; b_stripe_last = 1; b_frame_last = 1;
        core_done = 1; pause_active = 0; pause_forced_block = 0;
        uart_bytes = 12;
        @(posedge clk); #1;

        // Snapshot only after the UART has gone idle; cumulative errors are sampled.
        @(negedge clk);
        c2b_valid = 0; c2b_ready = 0; b_out_valid = 0;
        core_busy = 0; core_done = 0; session_done = 1; uart_final_idle = 1;
        uart_bytes = 20; core_proto_error = 1; core_overflow_error = 0;
        loader_protocol_error = 1; loader_frame_error_count = 2;
        uart_framing_error_count = 7;
        @(posedge clk); #1;

        if (snapshot_count !== 5'd1) $fatal(1, "snapshot count after frame 1");
        if (snapshot_overflow !== 1'b0) $fatal(1, "overflow before capacity");
        if (snapshot_selected_valid !== 1'b1) $fatal(1, "slot 0 valid");
        if (snapshot_selected_data[0] !== 1'b1) $fatal(1, "snapshot valid bit");
        if (snapshot_selected_data[4:1] !== 4'd0) $fatal(1, "slot index");
        if (snapshot_selected_data[36:5] !== 32'h1234abcd) $fatal(1, "latched frame id");
        if (snapshot_selected_data[37] !== 1'b1) $fatal(1, "frame start seen");
        if (snapshot_selected_data[38] !== 1'b0) $fatal(1, "core busy at session done");
        if (snapshot_selected_data[39] !== 1'b1) $fatal(1, "core done seen");
        if (snapshot_selected_data[40] !== 1'b1) $fatal(1, "session done");
        if (snapshot_selected_data[41] !== 1'b1) $fatal(1, "UART idle");
        if (snapshot_selected_data[73:42] !== 32'd3) $fatal(1, "final input handshake count");
        if (snapshot_selected_data[105:74] !== 32'd3) $fatal(1, "final output handshake count");
        if (snapshot_selected_data[121:106] !== 16'd2) $fatal(1, "accepted stripe-last count");
        if (snapshot_selected_data[129:122] !== 8'd2) $fatal(1, "accepted frame-last count");
        if (snapshot_selected_data[161:130] !== 32'd10) $fatal(1, "UART byte delta");
        if (snapshot_selected_data[162] !== 1'b1 ||
            snapshot_selected_data[163] !== 1'b0 ||
            snapshot_selected_data[164] !== 1'b1) $fatal(1, "sticky core/loader errors");
        if (snapshot_selected_data[196:165] !== 32'd2) $fatal(1, "loader frame errors");
        if (snapshot_selected_data[228:197] !== 32'd7) $fatal(1, "UART framing errors");
        if (snapshot_selected_data[292:229] !== 64'd6) $fatal(1, "core span cycles");
        if (snapshot_selected_data[356:293] !== 64'd6) $fatal(1, "last input cycle");
        if (snapshot_selected_data[420:357] !== 64'd6) $fatal(1, "last output cycle");
        if (snapshot_selected_data[484:421] !== 64'd7) $fatal(1, "session-done cycle");
        if (snapshot_selected_data[548:485] !== 64'd3) $fatal(1, "output blocked cycles");
        if (snapshot_selected_data[612:549] !== 64'd1) $fatal(1, "B input wait cycles");
        if (snapshot_selected_data[676:613] !== 64'd2) $fatal(1, "C-to-B stalled cycles");
        if (snapshot_selected_data[740:677] !== 64'd1) $fatal(1, "joint stall cycles");
        if (snapshot_selected_data[772:741] !== 32'd1) $fatal(1, "C-to-B hold violation count");
        if (snapshot_selected_data[804:773] !== 32'd1) $fatal(1, "B output hold violation count");
        if (snapshot_selected_data[868:805] !== 64'd1) $fatal(1, "pause request cycles");
        if (snapshot_selected_data[932:869] !== 64'd1) $fatal(1, "pause forced block cycles");
        if (snapshot_selected_data[933] !== 1'b0) $fatal(1, "pause active at completion");

        // Two-slot capacity test: preserve slot 0, fill slot 1, then report overflow.
        start_empty_frame(32'h00000002);
        if (snapshot_count !== 5'd2 || snapshot_overflow !== 1'b0)
            $fatal(1, "slot 1 capture / capacity");
        snapshot_select = 1;
        #1;
        if (snapshot_selected_valid !== 1'b1 ||
            snapshot_selected_data[36:5] !== 32'h00000002)
            $fatal(1, "slot 1 contents");
        start_empty_frame(32'h00000003);
        if (snapshot_count !== 5'd2 || snapshot_overflow !== 1'b1)
            $fatal(1, "overflow must latch after capacity");
        snapshot_select = 0; #1;
        if (snapshot_selected_data[36:5] !== 32'h1234abcd)
            $fatal(1, "slot 0 retention");
        snapshot_select = 1; #1;
        if (snapshot_selected_data[36:5] !== 32'h00000002)
            $fatal(1, "slot 1 retention");
        $display("RESULT: PASS observation counts, stalls, sidebands, errors, pause, and retention");
        $finish;
    end
endmodule