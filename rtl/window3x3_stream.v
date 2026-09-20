`timescale 1ns / 1ps

module window3x3_stream #(
    parameter integer DATA_W = 8,
    parameter integer IMG_W  = 4
)(
    input  wire                  clk,
    input  wire                  rst,

    input  wire [DATA_W-1:0]     pixel_in,
    input  wire                  pixel_valid,

    output reg  [DATA_W-1:0]     w00,
    output reg  [DATA_W-1:0]     w01,
    output reg  [DATA_W-1:0]     w02,
    output reg  [DATA_W-1:0]     w10,
    output reg  [DATA_W-1:0]     w11,
    output reg  [DATA_W-1:0]     w12,
    output reg  [DATA_W-1:0]     w20,
    output reg  [DATA_W-1:0]     w21,
    output reg  [DATA_W-1:0]     w22,

    output reg                   window_valid
);

    localparam integer COL_W = (IMG_W <= 1) ? 1 : $clog2(IMG_W);

    // Before an accepted clock edge, these counters identify pixel_in.
    reg [COL_W-1:0] col_count;
    reg [15:0]      row_count;

    // At the current column, linebuf1 and linebuf2 provide pixels from
    // the previous row and the row before that, respectively.
    reg [DATA_W-1:0] linebuf1 [0:IMG_W-1];
    reg [DATA_W-1:0] linebuf2 [0:IMG_W-1];

    wire [DATA_W-1:0] prev_row_pixel;
    wire [DATA_W-1:0] prev2_row_pixel;

    assign prev_row_pixel  = linebuf1[col_count];
    assign prev2_row_pixel = linebuf2[col_count];

    // Row and column counters advance only when a pixel is accepted.
    always @(posedge clk) begin
        if (rst) begin
            col_count <= {COL_W{1'b0}};
            row_count <= 16'd0;
        end
        else if (pixel_valid) begin
            if (col_count == IMG_W - 1) begin
                col_count <= {COL_W{1'b0}};
                row_count <= row_count + 1'b1;
            end
            else begin
                col_count <= col_count + 1'b1;
            end
        end
    end

    // Read the old values at this column, then overwrite the column.
    // The line buffers are intentionally not reset. Their contents are
    // ignored until two complete rows have been accepted.
    always @(posedge clk) begin
        if (!rst && pixel_valid) begin
            linebuf2[col_count] <= linebuf1[col_count];
            linebuf1[col_count] <= pixel_in;
        end
    end

    // Three horizontal shift-register rows form the 3x3 window.
    always @(posedge clk) begin
        if (rst) begin
            w00 <= {DATA_W{1'b0}};
            w01 <= {DATA_W{1'b0}};
            w02 <= {DATA_W{1'b0}};
            w10 <= {DATA_W{1'b0}};
            w11 <= {DATA_W{1'b0}};
            w12 <= {DATA_W{1'b0}};
            w20 <= {DATA_W{1'b0}};
            w21 <= {DATA_W{1'b0}};
            w22 <= {DATA_W{1'b0}};
            window_valid <= 1'b0;
        end
        else begin
            window_valid <= 1'b0;

            if (pixel_valid) begin
                if (col_count == 0) begin
                    // Start a new row without carrying horizontal history
                    // across the image boundary.
                    w00 <= {DATA_W{1'b0}};
                    w01 <= {DATA_W{1'b0}};
                    w02 <= prev2_row_pixel;
                    w10 <= {DATA_W{1'b0}};
                    w11 <= {DATA_W{1'b0}};
                    w12 <= prev_row_pixel;
                    w20 <= {DATA_W{1'b0}};
                    w21 <= {DATA_W{1'b0}};
                    w22 <= pixel_in;
                end
                else begin
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
