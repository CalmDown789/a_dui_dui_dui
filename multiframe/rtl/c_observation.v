`timescale 1ns / 1ps
`default_nettype none

// Read-only C/B boundary recorder. It observes handshakes and stores a
// stop-and-wait session's completed-frame records; it never drives the stream.
module c_observation #(
    parameter integer EXPECTED_INPUTS = 518400,
    parameter integer EXPECTED_OUTPUTS = 2073600,
    parameter integer SNAPSHOT_COUNT = 16
) (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         frame_start,
    input  wire         session_done,
    input  wire [31:0]  expected_frame_id,
    input  wire [31:0]  uart_bytes,
    input  wire         core_busy,
    input  wire         core_done,
    input  wire         uart_final_idle,
    input  wire         core_proto_error,
    input  wire         core_overflow_error,
    input  wire         loader_protocol_error,
    input  wire [31:0]  loader_frame_error_count,
    input  wire [31:0]  uart_framing_error_count,
    input  wire         c2b_valid,
    input  wire         c2b_ready,
    input  wire [7:0]   c2b_data,
    input  wire         b_out_valid,
    input  wire [7:0]   b_out_data,
    input  wire         b_out_ready,
    input  wire         b_stripe_last,
    input  wire         b_frame_last,
    input  wire         pause_active,
    input  wire         pause_forced_block,
    input  wire [3:0]   snapshot_select,
    output wire [933:0] snapshot_selected_data,
    output wire         snapshot_selected_valid,
    output reg  [4:0]   snapshot_count,
    output reg          snapshot_overflow
);
    // Exact modulo-2^64 increment, with four independent 16-bit sums.
    // Carry predicates use the OLD value; no cycle latency or range change.
    function [63:0] inc64;
        input [63:0] value;
        begin
            inc64[15:0]  = value[15:0]  + 16'd1;
            inc64[31:16] = value[31:16] + (&value[15:0]);
            inc64[47:32] = value[47:32] + (&value[31:0]);
            inc64[63:48] = value[63:48] + (&value[47:0]);
        end
    endfunction

    localparam [31:0] EXPECTED_INPUTS_U32 = EXPECTED_INPUTS;
    localparam [31:0] EXPECTED_OUTPUTS_U32 = EXPECTED_OUTPUTS;

    reg frame_active_q;
    reg [31:0] frame_id_q;
    reg [31:0] uart_bytes_start_q;
    reg core_done_seen_q;
    reg [63:0] elapsed_cycles_q;

    reg [31:0] input_accept_count_q;
    reg [31:0] output_accept_count_q;
    reg [15:0] stripe_last_accept_count_q;
    reg [7:0] frame_last_accept_count_q;
    reg [63:0] core_span_cycles_q;
    reg [63:0] last_input_cycle_q;
    reg [63:0] last_output_cycle_q;
    reg [63:0] output_blocked_cycles_q;
    reg [63:0] b_input_wait_cycles_q;
    reg [63:0] c2b_stall_cycles_q;
    reg [63:0] joint_stall_cycles_q;
    reg [31:0] c2b_hold_violation_count_q;
    reg [31:0] b_output_hold_violation_count_q;
    reg [63:0] pause_request_cycles_q;
    reg [63:0] pause_forced_block_cycles_q;

    reg c2b_previous_stall_q;
    reg [7:0] c2b_stall_data_q;
    reg b_previous_stall_q;
    reg [7:0] b_stall_data_q;
    reg b_stall_stripe_last_q;
    reg b_stall_frame_last_q;

    reg [15:0] snapshot_valid_q;
    reg [933:0] snapshot_memory [0:SNAPSHOT_COUNT-1];

    wire input_accept = c2b_valid && c2b_ready;
    wire output_accept = b_out_valid && b_out_ready;
    wire output_blocked = frame_active_q && b_out_valid && !b_out_ready;
    wire b_waiting_for_input = frame_active_q && core_busy &&
                               (input_accept_count_q < EXPECTED_INPUTS_U32) &&
                               !c2b_valid;
    wire c2b_stalled = frame_active_q && c2b_valid && !c2b_ready;
    wire joint_stall = b_waiting_for_input && output_blocked;

    assign snapshot_selected_valid = snapshot_valid_q[snapshot_select];
    assign snapshot_selected_data = snapshot_selected_valid
                                  ? snapshot_memory[snapshot_select]
                                  : 934'd0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            frame_active_q <= 1'b0;
            frame_id_q <= 32'd0;
            uart_bytes_start_q <= 32'd0;
            core_done_seen_q <= 1'b0;
            elapsed_cycles_q <= 64'd0;
            input_accept_count_q <= 32'd0;
            output_accept_count_q <= 32'd0;
            stripe_last_accept_count_q <= 16'd0;
            frame_last_accept_count_q <= 8'd0;
            core_span_cycles_q <= 64'd0;
            last_input_cycle_q <= 64'd0;
            last_output_cycle_q <= 64'd0;
            output_blocked_cycles_q <= 64'd0;
            b_input_wait_cycles_q <= 64'd0;
            c2b_stall_cycles_q <= 64'd0;
            joint_stall_cycles_q <= 64'd0;
            c2b_hold_violation_count_q <= 32'd0;
            b_output_hold_violation_count_q <= 32'd0;
            pause_request_cycles_q <= 64'd0;
            pause_forced_block_cycles_q <= 64'd0;
            c2b_previous_stall_q <= 1'b0;
            c2b_stall_data_q <= 8'd0;
            b_previous_stall_q <= 1'b0;
            b_stall_data_q <= 8'd0;
            b_stall_stripe_last_q <= 1'b0;
            b_stall_frame_last_q <= 1'b0;
            snapshot_valid_q <= 16'd0;
            snapshot_count <= 5'd0;
            snapshot_overflow <= 1'b0;
        end else begin
            if (frame_start) begin
                frame_active_q <= 1'b1;
                frame_id_q <= expected_frame_id;
                uart_bytes_start_q <= uart_bytes;
                core_done_seen_q <= core_done;
                elapsed_cycles_q <= 64'd1;

                input_accept_count_q <= input_accept ? 32'd1 : 32'd0;
                output_accept_count_q <= output_accept ? 32'd1 : 32'd0;
                stripe_last_accept_count_q <=
                    (output_accept && b_stripe_last) ? 16'd1 : 16'd0;
                frame_last_accept_count_q <=
                    (output_accept && b_frame_last) ? 8'd1 : 8'd0;
                core_span_cycles_q <= core_done ? 64'd1 : 64'd0;
                last_input_cycle_q <=
                    (input_accept && EXPECTED_INPUTS_U32 == 32'd1) ? 64'd1 : 64'd0;
                last_output_cycle_q <=
                    (output_accept && EXPECTED_OUTPUTS_U32 == 32'd1) ? 64'd1 : 64'd0;

                output_blocked_cycles_q <= 64'd0;
                b_input_wait_cycles_q <= 64'd0;
                c2b_stall_cycles_q <= 64'd0;
                joint_stall_cycles_q <= 64'd0;
                c2b_hold_violation_count_q <= 32'd0;
                b_output_hold_violation_count_q <= 32'd0;
                pause_request_cycles_q <= 64'd0;
                pause_forced_block_cycles_q <= 64'd0;

                c2b_previous_stall_q <= c2b_valid && !c2b_ready;
                if (c2b_valid && !c2b_ready)
                    c2b_stall_data_q <= c2b_data;
                b_previous_stall_q <= b_out_valid && !b_out_ready;
                if (b_out_valid && !b_out_ready) begin
                    b_stall_data_q <= b_out_data;
                    b_stall_stripe_last_q <= b_stripe_last;
                    b_stall_frame_last_q <= b_frame_last;
                end
            end else if (frame_active_q) begin
                elapsed_cycles_q <= inc64(elapsed_cycles_q);
                if (core_done)
                    core_done_seen_q <= 1'b1;
                if (core_done && !core_done_seen_q)
                    core_span_cycles_q <= inc64(elapsed_cycles_q);

                if (input_accept) begin
                    input_accept_count_q <= input_accept_count_q + 32'd1;
                    if (input_accept_count_q + 32'd1 == EXPECTED_INPUTS_U32)
                        last_input_cycle_q <= inc64(elapsed_cycles_q);
                end
                if (output_accept) begin
                    output_accept_count_q <= output_accept_count_q + 32'd1;
                    if (b_stripe_last)
                        stripe_last_accept_count_q <= stripe_last_accept_count_q + 16'd1;
                    if (b_frame_last)
                        frame_last_accept_count_q <= frame_last_accept_count_q + 8'd1;
                    if (output_accept_count_q + 32'd1 == EXPECTED_OUTPUTS_U32)
                        last_output_cycle_q <= inc64(elapsed_cycles_q);
                end

                if (output_blocked)
                    output_blocked_cycles_q <= inc64(output_blocked_cycles_q);
                if (b_waiting_for_input)
                    b_input_wait_cycles_q <= inc64(b_input_wait_cycles_q);
                if (c2b_stalled)
                    c2b_stall_cycles_q <= inc64(c2b_stall_cycles_q);
                if (joint_stall)
                    joint_stall_cycles_q <= inc64(joint_stall_cycles_q);
                if (pause_active)
                    pause_request_cycles_q <= inc64(pause_request_cycles_q);
                if (pause_forced_block)
                    pause_forced_block_cycles_q <= inc64(pause_forced_block_cycles_q);

                if (c2b_previous_stall_q &&
                    (!c2b_valid || c2b_data !== c2b_stall_data_q))
                    c2b_hold_violation_count_q <= c2b_hold_violation_count_q + 32'd1;
                c2b_previous_stall_q <= c2b_valid && !c2b_ready;
                if (c2b_valid && !c2b_ready)
                    c2b_stall_data_q <= c2b_data;

                if (b_previous_stall_q &&
                    (!b_out_valid || b_out_data !== b_stall_data_q ||
                     b_stripe_last !== b_stall_stripe_last_q ||
                     b_frame_last !== b_stall_frame_last_q))
                    b_output_hold_violation_count_q <= b_output_hold_violation_count_q + 32'd1;
                b_previous_stall_q <= b_out_valid && !b_out_ready;
                if (b_out_valid && !b_out_ready) begin
                    b_stall_data_q <= b_out_data;
                    b_stall_stripe_last_q <= b_stripe_last;
                    b_stall_frame_last_q <= b_frame_last;
                end
            end

            if (session_done && frame_active_q) begin
                frame_active_q <= 1'b0;
                if (snapshot_count < SNAPSHOT_COUNT) begin
                    snapshot_memory[snapshot_count[3:0]] <= {
                        pause_active,
                        pause_forced_block_cycles_q,
                        pause_request_cycles_q,
                        b_output_hold_violation_count_q,
                        c2b_hold_violation_count_q,
                        joint_stall_cycles_q,
                        c2b_stall_cycles_q,
                        b_input_wait_cycles_q,
                        output_blocked_cycles_q,
                        inc64(elapsed_cycles_q),
                        last_output_cycle_q,
                        last_input_cycle_q,
                        core_span_cycles_q,
                        uart_framing_error_count,
                        loader_frame_error_count,
                        loader_protocol_error,
                        core_overflow_error,
                        core_proto_error,
                        uart_bytes - uart_bytes_start_q,
                        frame_last_accept_count_q,
                        stripe_last_accept_count_q,
                        output_accept_count_q,
                        input_accept_count_q,
                        uart_final_idle,
                        session_done,
                        (core_done_seen_q || core_done),
                        core_busy,
                        1'b1,
                        frame_id_q,
                        snapshot_count[3:0],
                        1'b1
                    };
                    snapshot_valid_q[snapshot_count[3:0]] <= 1'b1;
                    snapshot_count <= snapshot_count + 5'd1;
                end else begin
                    snapshot_overflow <= 1'b1;
                end
            end
        end
    end
endmodule

`default_nettype wire
