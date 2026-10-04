`timescale 1ns / 1ps
`default_nettype none

// 8N1 UART receiver. The asynchronous pin is synchronized before sampling.
module uart_rx #(
    parameter integer BAUD_DIV = 162,
    parameter integer DATA_W = 8
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              rx_serial,
    output reg  [DATA_W-1:0] rx_data,
    output reg               rx_valid,
    output reg               rx_framing_error
);
    localparam integer CW = (BAUD_DIV <= 2) ? 2 : $clog2(BAUD_DIV);
    localparam integer HALF_DIV = (BAUD_DIV <= 2) ? 1 : (BAUD_DIV / 2);
    localparam [CW-1:0] DIV_LAST = BAUD_DIV - 1;
    localparam [CW-1:0] HALF_LAST = HALF_DIV - 1;

    localparam [1:0] S_IDLE  = 2'd0;
    localparam [1:0] S_START = 2'd1;
    localparam [1:0] S_DATA  = 2'd2;
    localparam [1:0] S_STOP  = 2'd3;

    (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) reg rx_meta_q, rx_sync_q;
    reg [1:0] state_q;
    reg [CW-1:0] count_q;
    reg [2:0] bit_q;
    reg [DATA_W-1:0] shift_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_meta_q <= 1'b1;
            rx_sync_q <= 1'b1;
            state_q <= S_IDLE;
            count_q <= {CW{1'b0}};
            bit_q <= 3'd0;
            shift_q <= {DATA_W{1'b0}};
            rx_data <= {DATA_W{1'b0}};
            rx_valid <= 1'b0;
            rx_framing_error <= 1'b0;
        end else begin
            rx_meta_q <= rx_serial;
            rx_sync_q <= rx_meta_q;
            rx_valid <= 1'b0;
            rx_framing_error <= 1'b0;

            case (state_q)
                S_IDLE: begin
                    count_q <= {CW{1'b0}};
                    if (!rx_sync_q) begin
                        count_q <= HALF_LAST;
                        state_q <= S_START;
                    end
                end
                S_START: begin
                    if (count_q == {CW{1'b0}}) begin
                        if (!rx_sync_q) begin
                            count_q <= DIV_LAST;
                            bit_q <= 3'd0;
                            shift_q <= {DATA_W{1'b0}};
                            state_q <= S_DATA;
                        end else begin
                            state_q <= S_IDLE;
                        end
                    end else begin
                        count_q <= count_q - 1'b1;
                    end
                end
                S_DATA: begin
                    if (count_q == {CW{1'b0}}) begin
                        shift_q[bit_q] <= rx_sync_q;
                        count_q <= DIV_LAST;
                        if (bit_q == DATA_W - 1) begin
                            state_q <= S_STOP;
                        end else begin
                            bit_q <= bit_q + 1'b1;
                        end
                    end else begin
                        count_q <= count_q - 1'b1;
                    end
                end
                S_STOP: begin
                    if (count_q == {CW{1'b0}}) begin
                        state_q <= S_IDLE;
                        if (rx_sync_q) begin
                            rx_data <= shift_q;
                            rx_valid <= 1'b1;
                        end else begin
                            rx_framing_error <= 1'b1;
                        end
                    end else begin
                        count_q <= count_q - 1'b1;
                    end
                end
                default: state_q <= S_IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
