`timescale 1ns / 1ps

// Functional single-plane 5x5 stream window with no implicit padding.
// window_flat tap index is row-major: (row * 5 + column) * DATA_W.
module window5x5_stream #(
    parameter integer DATA_W = 8,
    parameter integer IMG_W  = 6
)(
    input  wire                       clk,
    input  wire                       rst,
    input  wire [DATA_W-1:0]          pixel_in,
    input  wire                       pixel_valid,
    output wire [(25*DATA_W)-1:0]     window_flat,
    output reg                        window_valid
);

    localparam integer COL_W = (IMG_W <= 1) ? 1 : $clog2(IMG_W);

    reg [COL_W-1:0] col_count;
    reg [15:0] row_count;
    reg [DATA_W-1:0] linebuf1 [0:IMG_W-1];
    reg [DATA_W-1:0] linebuf2 [0:IMG_W-1];
    reg [DATA_W-1:0] linebuf3 [0:IMG_W-1];
    reg [DATA_W-1:0] linebuf4 [0:IMG_W-1];
    reg [DATA_W-1:0] shifts [0:24];

    wire [DATA_W-1:0] prev1;
    wire [DATA_W-1:0] prev2;
    wire [DATA_W-1:0] prev3;
    wire [DATA_W-1:0] prev4;

    assign prev1 = linebuf1[col_count];
    assign prev2 = linebuf2[col_count];
    assign prev3 = linebuf3[col_count];
    assign prev4 = linebuf4[col_count];

    genvar tap;
    generate
        for (tap=0; tap<25; tap=tap+1) begin : g_flatten
            assign window_flat[(tap*DATA_W) +: DATA_W] = shifts[tap];
        end
    endgenerate

    initial begin
        if (DATA_W < 1)
            $error("DATA_W must be at least 1");
        if (IMG_W < 5)
            $error("IMG_W must be at least 5 for a 5x5 window");
    end

    always @(posedge clk) begin
        if (rst) begin
            col_count <= 0;
            row_count <= 0;
        end else if (pixel_valid) begin
            if (col_count == IMG_W - 1) begin
                col_count <= 0;
                row_count <= row_count + 1'b1;
            end else begin
                col_count <= col_count + 1'b1;
            end
        end
    end

    always @(posedge clk) begin
        if (!rst && pixel_valid) begin
            linebuf4[col_count] <= linebuf3[col_count];
            linebuf3[col_count] <= linebuf2[col_count];
            linebuf2[col_count] <= linebuf1[col_count];
            linebuf1[col_count] <= pixel_in;
        end
    end

    integer i;
    integer row;
    always @(posedge clk) begin
        if (rst) begin
            for (i=0; i<25; i=i+1)
                shifts[i] <= 0;
            window_valid <= 1'b0;
        end else begin
            window_valid <= 1'b0;
            if (pixel_valid) begin
                if (col_count == 0) begin
                    for (row=0; row<5; row=row+1) begin
                        shifts[row*5+0] <= 0;
                        shifts[row*5+1] <= 0;
                        shifts[row*5+2] <= 0;
                        shifts[row*5+3] <= 0;
                    end
                end else begin
                    for (row=0; row<5; row=row+1) begin
                        shifts[row*5+0] <= shifts[row*5+1];
                        shifts[row*5+1] <= shifts[row*5+2];
                        shifts[row*5+2] <= shifts[row*5+3];
                        shifts[row*5+3] <= shifts[row*5+4];
                    end
                end

                shifts[4]  <= prev4;
                shifts[9]  <= prev3;
                shifts[14] <= prev2;
                shifts[19] <= prev1;
                shifts[24] <= pixel_in;
                window_valid <= (row_count >= 4) && (col_count >= 4);
            end
        end
    end

endmodule
