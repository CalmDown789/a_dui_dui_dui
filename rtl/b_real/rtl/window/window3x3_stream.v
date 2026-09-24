`timescale 1ns / 1ps

// Functional single-plane 3x3 stream window with no implicit padding.
// The board/protocol wrapper is responsible for starting a frame with rst.
module window3x3_stream #(
    parameter integer DATA_W = 8,
    parameter integer IMG_W  = 4
)(
    input  wire                  clk,
    input  wire                  rst,
    input  wire [DATA_W-1:0]     pixel_in,
    input  wire                  pixel_valid,

    output reg  [DATA_W-1:0]     w00, w01, w02,
    output reg  [DATA_W-1:0]     w10, w11, w12,
    output reg  [DATA_W-1:0]     w20, w21, w22,
    output reg                   window_valid
);

    localparam integer COL_W = (IMG_W <= 1) ? 1 : $clog2(IMG_W);

    reg [COL_W-1:0] col_count;
    reg [15:0] row_count;
    reg [DATA_W-1:0] linebuf1 [0:IMG_W-1];
    reg [DATA_W-1:0] linebuf2 [0:IMG_W-1];

    wire [DATA_W-1:0] prev_row_pixel;
    wire [DATA_W-1:0] prev2_row_pixel;

    assign prev_row_pixel  = linebuf1[col_count];
    assign prev2_row_pixel = linebuf2[col_count];

    initial begin
        if (DATA_W < 1)
            $error("DATA_W must be at least 1");
        if (IMG_W < 3)
            $error("IMG_W must be at least 3 for a 3x3 window");
    end

    always @(posedge clk) begin
        if (rst) begin
            col_count <= {COL_W{1'b0}};
            row_count <= 16'd0;
        end else if (pixel_valid) begin
            if (col_count == IMG_W - 1) begin
                col_count <= {COL_W{1'b0}};
                row_count <= row_count + 1'b1;
            end else begin
                col_count <= col_count + 1'b1;
            end
        end
    end

    // Old values at this column feed the window before the nonblocking writes
    // advance both line buffers. The memories need not be reset because their
    // contents are ignored until two complete rows have been accepted.
    always @(posedge clk) begin
        if (!rst && pixel_valid) begin
            linebuf2[col_count] <= linebuf1[col_count];
            linebuf1[col_count] <= pixel_in;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            w00 <= 0; w01 <= 0; w02 <= 0;
            w10 <= 0; w11 <= 0; w12 <= 0;
            w20 <= 0; w21 <= 0; w22 <= 0;
            window_valid <= 1'b0;
        end else begin
            window_valid <= 1'b0;

            if (pixel_valid) begin
                if (col_count == 0) begin
                    w00 <= 0;
                    w01 <= 0;
                    w02 <= prev2_row_pixel;
                    w10 <= 0;
                    w11 <= 0;
                    w12 <= prev_row_pixel;
                    w20 <= 0;
                    w21 <= 0;
                    w22 <= pixel_in;
                end else begin
                    w00 <= w01;
                    w01 <= w02;
                    w02 <= prev2_row_pixel;
                    w10 <= w11;
                    w11 <= w12;
                    w12 <= prev_row_pixel;
                    w20 <= w21;
                    w21 <= w22;
                    w22 <= pixel_in;
                end

                window_valid <= (row_count >= 2) && (col_count >= 2);
            end
        end
    end

endmodule
