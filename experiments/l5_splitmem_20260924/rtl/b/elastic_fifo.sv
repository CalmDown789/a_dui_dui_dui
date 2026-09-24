`timescale 1ns / 1ps

// Ordered ready/valid FIFO. Wide words use independent 64-bit distributed
// RAM slices, each with a local read pointer to limit LUTRAM address fanout.
module elastic_fifo #(
    parameter integer DATA_W = 256,
    parameter integer DEPTH = 32
)(
    input  wire                  clk,
    input  wire                  rst,
    input  wire                  in_valid,
    output wire                  in_ready,
    input  wire [DATA_W-1:0]     in_data,
    output wire                  out_valid,
    input  wire                  out_ready,
    output wire [DATA_W-1:0]     out_data,
    output wire [$clog2(DEPTH+1)-1:0] occupancy
);
    localparam integer PTR_W = (DEPTH <= 1) ? 1 : $clog2(DEPTH);
    localparam integer COUNT_W = $clog2(DEPTH+1);
    localparam integer RD_SEG_W = 64;
    localparam integer RD_SEGS = (DATA_W + RD_SEG_W - 1) / RD_SEG_W;
    reg [PTR_W-1:0] wr_ptr;
    reg [COUNT_W-1:0] count;
    wire pop = out_valid && out_ready;
    wire push = in_valid && in_ready;

    assign out_valid = (count != 0);
    assign in_ready = (count < DEPTH) || pop;
    assign occupancy = count;

    initial begin
        if (DATA_W < 1 || DEPTH < 1)
            $error("elastic_fifo requires positive width and depth");
    end

    generate
        if (DATA_W > 1024) begin : g_wide_read
            genvar s;
            for (s = 0; s < RD_SEGS; s = s + 1) begin : g_read_slice
                localparam integer SLICE_W =
                    ((DATA_W - s*RD_SEG_W) < RD_SEG_W) ?
                    (DATA_W - s*RD_SEG_W) : RD_SEG_W;
                (* ram_style = "distributed" *) reg [SLICE_W-1:0] mem_slice [0:DEPTH-1];
                (* DONT_TOUCH = "TRUE" *) reg [PTR_W-1:0] rd_ptr_local;
                always @(posedge clk) begin
                    if (push)
                        mem_slice[wr_ptr] <= in_data[s*RD_SEG_W +: SLICE_W];
                    if (rst)
                        rd_ptr_local <= 0;
                    else if (pop)
                        rd_ptr_local <= (rd_ptr_local == DEPTH-1) ? 0 : rd_ptr_local + 1'b1;
                end
                assign out_data[s*RD_SEG_W +: SLICE_W] = mem_slice[rd_ptr_local];
            end
        end else begin : g_narrow_read
            (* ram_style = "distributed" *) reg [DATA_W-1:0] mem [0:DEPTH-1];
            reg [PTR_W-1:0] rd_ptr_local;
            always @(posedge clk) begin
                if (push)
                    mem[wr_ptr] <= in_data;
                if (rst)
                    rd_ptr_local <= 0;
                else if (pop)
                    rd_ptr_local <= (rd_ptr_local == DEPTH-1) ? 0 : rd_ptr_local + 1'b1;
            end
            assign out_data = mem[rd_ptr_local];
        end
    endgenerate

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= 0;
            count <= 0;
        end else begin
            if (push)
                wr_ptr <= (wr_ptr == DEPTH-1) ? 0 : wr_ptr + 1'b1;
            case ({push,pop})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule