`timescale 1ns / 1ps
`default_nettype none

// Stop-and-wait input protocol for the C-side frame store.
// Request: ASCII "SRTP", then frame_id, payload_bytes, payload_crc32,
// header_crc32 (four little-endian uint32 values; header CRC covers the first
// three fields), then exactly FRAME_PIXELS payload bytes. CRCs use IEEE CRC32.
// A valid request starts one frame. The response is the fixed-size raw Y frame;
// the host associates it with the sole outstanding request and reads exactly
// OUTPUT_BYTES before issuing the next frame ID.
module uart_frame_loader #(
    parameter integer CLK_HZ = 100000000,
    parameter integer UART_BAUD = 921600,
    parameter integer BAUD_DIV = (CLK_HZ / UART_BAUD < 1) ? 1 : (CLK_HZ / UART_BAUD),
    parameter integer FRAME_PIXELS = 518400,
    parameter integer OUTPUT_BYTES = 2073600,
    parameter integer ADDR_W = 19
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              uart_rx_pin,
    output wire              frame_wr_en,
    output wire [ADDR_W-1:0] frame_wr_addr,
    output wire [7:0]        frame_wr_data,
    output reg               frame_start,
    output reg               frame_done,
    output reg               frame_active,
    output reg  [31:0]       expected_frame_id,
    output reg  [31:0]       frame_error_count,
    output reg  [31:0]       uart_framing_error_count,
    output reg               protocol_error,
    input  wire              core_busy,
    input  wire              core_done,
    input  wire [31:0]       core_uart_bytes,
    input  wire              core_uart_tx_busy,
    input  wire              core_readback_busy
);
    localparam integer COUNT_W = (FRAME_PIXELS <= 1) ? 1 : $clog2(FRAME_PIXELS);
    localparam [31:0] FRAME_BYTES_U32 = FRAME_PIXELS;
    localparam [31:0] OUTPUT_BYTES_U32 = OUTPUT_BYTES;

    localparam [2:0] S_SEEK   = 3'd0;
    localparam [2:0] S_HEADER = 3'd1;
    localparam [2:0] S_CHECK  = 3'd2;
    localparam [2:0] S_PAYLOAD = 3'd3;
    localparam [2:0] S_OUTPUT = 3'd4;

    wire [7:0] rx_data;
    wire rx_valid;
    wire rx_framing_error;
    reg [2:0] state_q;
    reg [31:0] sync_shift_q;
    reg [127:0] header_q;
    reg [4:0] header_index_q;
    reg header_valid_q;
    reg [31:0] expected_payload_crc_q;
    reg [31:0] payload_crc_q;
    reg [COUNT_W-1:0] payload_index_q;
    reg [31:0] frame_base_bytes_q;
    reg core_done_seen_q;

    wire [31:0] sync_candidate = {sync_shift_q[23:0], rx_data};
    wire [31:0] payload_crc_next = crc32_byte(payload_crc_q, rx_data);

    assign frame_wr_en = (state_q == S_PAYLOAD) && header_valid_q && rx_valid;
    assign frame_wr_addr = {{(ADDR_W-COUNT_W){1'b0}}, payload_index_q};
    assign frame_wr_data = rx_data;

    uart_rx #(
        .BAUD_DIV (BAUD_DIV),
        .DATA_W   (8)
    ) u_uart_rx (
        .clk              (clk),
        .rst_n            (rst_n),
        .rx_serial        (uart_rx_pin),
        .rx_data          (rx_data),
        .rx_valid         (rx_valid),
        .rx_framing_error (rx_framing_error)
    );

    function [31:0] crc32_byte;
        input [31:0] crc_in;
        input [7:0] data_in;
        reg [31:0] crc;
        integer bit_index;
        begin
            crc = crc_in ^ {24'd0, data_in};
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                if (crc[0]) crc = (crc >> 1) ^ 32'hEDB88320;
                else        crc = crc >> 1;
            end
            crc32_byte = crc;
        end
    endfunction

    function [31:0] crc32_header;
        input [95:0] header_data;
        reg [31:0] crc;
        integer byte_index;
        begin
            crc = 32'hFFFFFFFF;
            for (byte_index = 0; byte_index < 12; byte_index = byte_index + 1)
                crc = crc32_byte(crc, header_data[byte_index*8 +: 8]);
            crc32_header = ~crc;
        end
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q <= S_SEEK;
            sync_shift_q <= 32'd0;
            header_q <= 128'd0;
            header_index_q <= 5'd0;
            header_valid_q <= 1'b0;
            expected_payload_crc_q <= 32'd0;
            payload_crc_q <= 32'hFFFFFFFF;
            payload_index_q <= {COUNT_W{1'b0}};
            frame_base_bytes_q <= 32'd0;
            core_done_seen_q <= 1'b0;
            frame_start <= 1'b0;
            frame_done <= 1'b0;
            frame_active <= 1'b0;
            expected_frame_id <= 32'd0;
            frame_error_count <= 32'd0;
            uart_framing_error_count <= 32'd0;
            protocol_error <= 1'b0;
        end else begin
            frame_start <= 1'b0;
            frame_done <= 1'b0;

            if (rx_framing_error) begin
                uart_framing_error_count <= uart_framing_error_count + 32'd1;
                frame_error_count <= frame_error_count + 32'd1;
                protocol_error <= 1'b1;
            end

            case (state_q)
                S_SEEK: begin
                    if (rx_valid) begin
                        sync_shift_q <= sync_candidate;
                        if (sync_candidate == 32'h53525450) begin // "SRTP"
                            header_q <= 128'd0;
                            header_index_q <= 5'd0;
                            header_valid_q <= 1'b0;
                            state_q <= S_HEADER;
                        end
                    end
                end

                S_HEADER: begin
                    if (rx_valid) begin
                        header_q[header_index_q*8 +: 8] <= rx_data;
                        if (header_index_q == 5'd15) begin
                            state_q <= S_CHECK;
                        end else begin
                            header_index_q <= header_index_q + 1'b1;
                        end
                    end
                end

                S_CHECK: begin
                    expected_payload_crc_q <= header_q[95:64];
                    header_valid_q <=
                        (header_q[31:0] == expected_frame_id) &&
                        (header_q[63:32] == FRAME_BYTES_U32) &&
                        (header_q[127:96] == crc32_header(header_q[95:0]));
                    if ((header_q[31:0] != expected_frame_id) ||
                        (header_q[63:32] != FRAME_BYTES_U32) ||
                        (header_q[127:96] != crc32_header(header_q[95:0]))) begin
                        frame_error_count <= frame_error_count + 32'd1;
                        protocol_error <= 1'b1;
                    end
                    payload_index_q <= {COUNT_W{1'b0}};
                    payload_crc_q <= 32'hFFFFFFFF;
                    state_q <= S_PAYLOAD;
                end

                S_PAYLOAD: begin
                    if (rx_valid) begin
                        payload_crc_q <= payload_crc_next;
                        if (payload_index_q == FRAME_PIXELS - 1) begin
                            if (header_valid_q && ((~payload_crc_next) == expected_payload_crc_q)) begin
                                frame_start <= 1'b1;
                                frame_active <= 1'b1;
                                frame_base_bytes_q <= core_uart_bytes;
                                core_done_seen_q <= 1'b0;
                                state_q <= S_OUTPUT;
                            end else begin
                                if (header_valid_q) begin
                                    frame_error_count <= frame_error_count + 32'd1;
                                    protocol_error <= 1'b1;
                                end
                                state_q <= S_SEEK;
                            end
                        end else begin
                            payload_index_q <= payload_index_q + 1'b1;
                        end
                    end
                end

                S_OUTPUT: begin
                    if (core_done) core_done_seen_q <= 1'b1;
                    if (rx_valid) begin
                        frame_error_count <= frame_error_count + 32'd1;
                        protocol_error <= 1'b1;
                    end
                    if ((core_done_seen_q || core_done) && !core_busy &&
                        ((core_uart_bytes - frame_base_bytes_q) == OUTPUT_BYTES_U32) &&
                        !core_uart_tx_busy && !core_readback_busy) begin
                        frame_done <= 1'b1;
                        frame_active <= 1'b0;
                        expected_frame_id <= expected_frame_id + 32'd1;
                        state_q <= S_SEEK;
                    end else if ((core_uart_bytes - frame_base_bytes_q) > OUTPUT_BYTES_U32) begin
                        frame_error_count <= frame_error_count + 32'd1;
                        protocol_error <= 1'b1;
                    end
                end

                default: begin
                    state_q <= S_SEEK;
                    frame_error_count <= frame_error_count + 32'd1;
                    protocol_error <= 1'b1;
                end
            endcase
        end
    end
endmodule

`default_nettype wire
