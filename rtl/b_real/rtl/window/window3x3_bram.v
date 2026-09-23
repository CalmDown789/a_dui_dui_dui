`timescale 1ns / 1ps

// Three rotating row banks. One bank receives the current row while the other
// two provide the previous rows. Synchronous reads add one pipeline stage.
module window3x3_bram #(
    parameter integer DATA_W = 16,
    parameter integer IMG_W  = 960
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

    (* ram_style = "block" *) reg [DATA_W-1:0] bank0 [0:IMG_W-1];
    (* ram_style = "block" *) reg [DATA_W-1:0] bank1 [0:IMG_W-1];
    (* ram_style = "block" *) reg [DATA_W-1:0] bank2 [0:IMG_W-1];

    reg [COL_W-1:0] col_count;
    reg [15:0] row_count;
    reg [1:0] row_mod3;

    reg [DATA_W-1:0] q0, q1, q2;
    reg [DATA_W-1:0] pixel_d;
    reg [COL_W-1:0] col_d;
    reg [15:0] row_d;
    reg [1:0] row_mod3_d;
    reg read_valid_d;

    reg [DATA_W-1:0] prev1_selected;
    reg [DATA_W-1:0] prev2_selected;

    initial begin
        if (DATA_W < 1)
            $error("DATA_W must be at least 1");
        if (IMG_W < 3)
            $error("IMG_W must be at least 3 for a 3x3 window");
    end

    always @* begin
        case (row_mod3_d)
            2'd0: begin prev1_selected=q2; prev2_selected=q1; end
            2'd1: begin prev1_selected=q0; prev2_selected=q2; end
            default: begin prev1_selected=q1; prev2_selected=q0; end
        endcase
    end

    // Read all banks at the requested column. The current-row bank's read
    // value is ignored; the write stores the newly accepted pixel.
    always @(posedge clk) begin
        if (rst) begin
            col_count<=0;
            row_count<=0;
            row_mod3<=0;
            q0<=0; q1<=0; q2<=0;
            pixel_d<=0; col_d<=0; row_d<=0; row_mod3_d<=0;
            read_valid_d<=1'b0;
        end else begin
            read_valid_d<=pixel_valid;
            if (pixel_valid) begin
                q0<=bank0[col_count];
                q1<=bank1[col_count];
                q2<=bank2[col_count];
                pixel_d<=pixel_in;
                col_d<=col_count;
                row_d<=row_count;
                row_mod3_d<=row_mod3;

                case (row_mod3)
                    2'd0: bank0[col_count]<=pixel_in;
                    2'd1: bank1[col_count]<=pixel_in;
                    default: bank2[col_count]<=pixel_in;
                endcase

                if (col_count == IMG_W-1) begin
                    col_count<=0;
                    row_count<=row_count+1'b1;
                    row_mod3<=(row_mod3 == 2) ? 0 : row_mod3+1'b1;
                end else begin
                    col_count<=col_count+1'b1;
                end
            end
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            w00<=0; w01<=0; w02<=0;
            w10<=0; w11<=0; w12<=0;
            w20<=0; w21<=0; w22<=0;
            window_valid<=1'b0;
        end else begin
            window_valid<=1'b0;
            if (read_valid_d) begin
                if (col_d == 0) begin
                    w00<=0; w01<=0; w02<=prev2_selected;
                    w10<=0; w11<=0; w12<=prev1_selected;
                    w20<=0; w21<=0; w22<=pixel_d;
                end else begin
                    w00<=w01; w01<=w02; w02<=prev2_selected;
                    w10<=w11; w11<=w12; w12<=prev1_selected;
                    w20<=w21; w21<=w22; w22<=pixel_d;
                end
                window_valid<=(row_d >= 2) && (col_d >= 2);
            end
        end
    end

endmodule
