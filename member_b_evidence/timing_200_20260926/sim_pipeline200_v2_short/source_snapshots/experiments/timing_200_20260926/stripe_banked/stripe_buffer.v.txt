`timescale 1ns / 1ps
`default_nettype none

// Isolated two-cycle stripe read candidate. Each 4096-word bank contains both
// read stages before the top-level bank mux. No storage/data/selector reset.
// Confirm DO*_REG or local pre-mux FFs in the synthesized netlist; source-level
// pipelining alone is not evidence that the intended physical split survived.
module stripe_buffer #(
    parameter integer WIDTH = 1920,
    parameter integer ROWS = 64,
    parameter integer DATA_W = 8,
    parameter integer ADDR_W = (WIDTH*ROWS <= 1) ? 1 : $clog2(WIDTH*ROWS)
)(
    input wire clk,
    input wire wr_en,
    input wire [ADDR_W-1:0] wr_addr,
    input wire [DATA_W-1:0] wr_data,
    input wire rd_en,
    input wire [ADDR_W-1:0] rd_addr,
    output wire [DATA_W-1:0] rd_data
);
    localparam integer MEM_DEPTH = WIDTH*ROWS;
    localparam integer BANK_DEPTH = 4096;
    localparam integer BANKS = (MEM_DEPTH+BANK_DEPTH-1)/BANK_DEPTH;
    localparam integer BANK_SEL_W = (BANKS <= 1) ? 1 : $clog2(BANKS);

    // Assignment pads addresses narrower than 12 bits and truncates higher
    // bits. It avoids illegal rd_addr[11:0] slices for small parameter tests.
    wire [11:0] wr_local_addr = wr_addr;
    wire [11:0] rd_local_addr = rd_addr;
    wire [BANK_SEL_W-1:0] wr_bank = wr_addr >> 12;
    wire [BANK_SEL_W-1:0] rd_bank = rd_addr >> 12;
    wire write_ok = wr_en && (wr_addr < MEM_DEPTH);
    wire read_ok = rd_en && (rd_addr < MEM_DEPTH);
    wire [BANKS*DATA_W-1:0] bank_read_data;
    reg [BANK_SEL_W-1:0] rd_bank_q0;
    reg [BANK_SEL_W-1:0] rd_bank_q1;

    initial begin
        if (WIDTH < 1 || ROWS < 1 || DATA_W < 1 || ADDR_W < 1)
            $error("stripe_buffer requires positive geometry and widths");
    end

    genvar bank_index;
    generate for (bank_index=0; bank_index<BANKS; bank_index=bank_index+1) begin : g_bank
        localparam integer WORDS =
            ((MEM_DEPTH-bank_index*BANK_DEPTH) < BANK_DEPTH) ?
            (MEM_DEPTH-bank_index*BANK_DEPTH) : BANK_DEPTH;
        // Preserve the inference boundary, while allowing q1 to be absorbed
        // into this bank's BRAM output register when the tool supports it.
        (* keep_hierarchy = "yes" *) stripe_buffer_bank4096 #(
            .WORDS(WORDS), .DATA_W(DATA_W)
        ) memory (
            .clk(clk),
            .wr_en(write_ok && (wr_bank == bank_index)),
            .wr_addr(wr_local_addr), .wr_data(wr_data),
            .rd_en(read_ok && (rd_bank == bank_index)),
            .rd_addr(rd_local_addr),
            .rd_data(bank_read_data[bank_index*DATA_W+:DATA_W])
        );
    end endgenerate

    always @(posedge clk) begin
        if (read_ok) rd_bank_q0 <= rd_bank;
        rd_bank_q1 <= rd_bank_q0;
    end
    // At E1, q1 and the two-stage selector correspond to the request at E0.
    // After invalid/disabled reads, both the selected bank and data hold.
    assign rd_data = bank_read_data[rd_bank_q1*DATA_W+:DATA_W];
endmodule

// One inference unit, at most one 4096x8 BRAM36 in the production geometry.
// Simultaneous same-address read/write retains the original read-first RTL
// semantics (both RHS values are sampled before nonblocking writes commit).
module stripe_buffer_bank4096 #(
    parameter integer WORDS = 4096,
    parameter integer DATA_W = 8
)(
    input wire clk,
    input wire wr_en,
    input wire [11:0] wr_addr,
    input wire [DATA_W-1:0] wr_data,
    input wire rd_en,
    input wire [11:0] rd_addr,
    output wire [DATA_W-1:0] rd_data
);
    (* ram_style = "block", ram_decomp = "power" *)
    reg [DATA_W-1:0] mem [0:WORDS-1];
    reg [DATA_W-1:0] read_q0;
    reg [DATA_W-1:0] read_q1;
    always @(posedge clk) begin
        if (wr_en && (wr_addr < WORDS)) mem[wr_addr] <= wr_data;
        if (rd_en && (rd_addr < WORDS)) read_q0 <= mem[rd_addr];
        read_q1 <= read_q0;
    end
    assign rd_data = read_q1;
endmodule

`default_nettype wire
