`timescale 1ns / 1ps

// 成员B工作 / Team member B: ordered ready/valid FIFO for layer tokens.
// DEPTH may be set to 32 for F12/F23/F34/F45. No combinational data bypass.
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
    reg [DATA_W-1:0] mem [0:DEPTH-1];
    reg [PTR_W-1:0] rd_ptr, wr_ptr;
    reg [COUNT_W-1:0] count;
    wire pop = out_valid && out_ready;
    wire push = in_valid && in_ready;

    assign out_valid = (count != 0);
    assign out_data = mem[rd_ptr];
    assign in_ready = (count < DEPTH) || pop;
    assign occupancy = count;

    initial begin
        if (DATA_W < 1 || DEPTH < 1)
            $error("elastic_fifo requires positive width and depth");
    end

    always @(posedge clk) begin
        if (rst) begin
            rd_ptr <= 0;
            wr_ptr <= 0;
            count <= 0;
        end else begin
            if (push) begin
                mem[wr_ptr] <= in_data;
                wr_ptr <= (wr_ptr == DEPTH-1) ? 0 : wr_ptr + 1'b1;
            end
            if (pop)
                rd_ptr <= (rd_ptr == DEPTH-1) ? 0 : rd_ptr + 1'b1;
            case ({push,pop})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
