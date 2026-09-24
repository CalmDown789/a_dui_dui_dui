`timescale 1ns / 1ps

// Team member B: PixelShuffle phase-to-coordinate mapping primitive.

// Coordinate-only PixelShuffle x2 primitive.
// This module fixes the confirmed phase convention without deciding whether
// the board-level implementation uses DDR, line buffers, or a streaming FIFO.
module pixel_shuffle2x_coord_map #(
    parameter integer X_W = 10,
    parameter integer Y_W = 10,
    parameter integer DATA_W = 8
)(
    input  wire [X_W-1:0]       in_x,
    input  wire [Y_W-1:0]       in_y,
    input  wire [1:0]           phase,
    input  wire [DATA_W-1:0]    in_data,
    output wire [X_W:0]         out_x,
    output wire [Y_W:0]         out_y,
    output wire [DATA_W-1:0]    out_data
);

    // phase 0 TL, phase 1 TR, phase 2 BL, phase 3 BR.
    assign out_x = {in_x, 1'b0} + phase[0];
    assign out_y = {in_y, 1'b0} + phase[1];
    assign out_data = in_data;

endmodule
