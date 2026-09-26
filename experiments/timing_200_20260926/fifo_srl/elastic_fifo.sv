`timescale 1ns / 1ps

// Member B experiment, 2026-09-26: only the L5 6400-bit, depth-4 FIFO
// changes storage structure. All other parameter combinations retain the
// l5_splitmem_20260924 baseline implementation below.
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
        if ((DATA_W == 6400) && (DEPTH == 4)) begin : g_l5_srl
            // A push inserts the newest word at stage 0 and shifts older
            // words toward stage 3. The oldest valid word is at count-1.
            // No binary write address reaches the storage elements.
            genvar ss, bit_index;
            for (ss = 0; ss < RD_SEGS; ss = ss + 1) begin : g_slice
                // The baseline already partitions the read address by 64
                // data bits. Preserve that locality, but track occupancy-1
                // instead of a circular read pointer. This 2-bit register
                // equals (count-1) mod 4, including 3 while the FIFO is empty.
                // Empty data is invalid; the SRL contents need no reset.
                (* DONT_TOUCH = "TRUE" *) reg [1:0] read_index_local;
                always @(posedge clk) begin
                    if (rst)
                        read_index_local <= 2'd3;
                    else begin
                        case ({push,pop})
                            2'b10: read_index_local <= read_index_local + 2'd1;
                            2'b01: read_index_local <= read_index_local - 2'd1;
                            default: read_index_local <= read_index_local;
                        endcase
                    end
                end
                for (bit_index = 0; bit_index < RD_SEG_W;
                     bit_index = bit_index + 1) begin : g_bit
                    // Dynamic SRL inference template: unreset shift chain,
                    // common clock enable, and variable output tap.
                    (* shreg_extract = "yes", srl_style = "srl" *)
                    reg [3:0] data_shift;
                    always @(posedge clk) begin
                        if (push)
                            data_shift <= {data_shift[2:0],
                                           in_data[ss*RD_SEG_W + bit_index]};
                    end
                    assign out_data[ss*RD_SEG_W + bit_index] =
                        data_shift[read_index_local];
                end
            end
        end else if (DATA_W > 1024) begin : g_wide_read
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
