`timescale 1ns / 1ps
`default_nettype none
`include "c_config.vh"

module input_rom_bank #(
    parameter integer BANK_ID = 0,
    parameter integer BANK_DEPTH = 4096,
    parameter integer ADDR_W = 12,
    parameter integer DATA_W = `C_PIXEL_W,
    parameter integer INIT_MODE = 0,
    parameter integer INIT_EN = 0
)(
    input wire clk,
    input wire en,
    input wire [ADDR_W-1:0] addr,
    output reg [DATA_W-1:0] dout
);
    (* ram_style = "block" *) reg [DATA_W-1:0] mem [0:BANK_DEPTH-1];
    integer i;

`ifdef C_SIM
    initial begin
        if (INIT_MODE == 1) begin
            for (i = 0; i < BANK_DEPTH; i = i + 1)
                mem[i] = (((BANK_ID * BANK_DEPTH + i) * 7) + ((BANK_ID * BANK_DEPTH + i) >> 8) + 13) & ((1 << DATA_W) - 1);
        end
    end
`endif

    initial begin
        if ((INIT_MODE == 0) && (INIT_EN != 0)) begin
            case (BANK_ID)
                0: $readmemh("rom_bank_000.mem", mem);
                1: $readmemh("rom_bank_001.mem", mem);
                2: $readmemh("rom_bank_002.mem", mem);
                3: $readmemh("rom_bank_003.mem", mem);
                4: $readmemh("rom_bank_004.mem", mem);
                5: $readmemh("rom_bank_005.mem", mem);
                6: $readmemh("rom_bank_006.mem", mem);
                7: $readmemh("rom_bank_007.mem", mem);
                8: $readmemh("rom_bank_008.mem", mem);
                9: $readmemh("rom_bank_009.mem", mem);
                10: $readmemh("rom_bank_010.mem", mem);
                11: $readmemh("rom_bank_011.mem", mem);
                12: $readmemh("rom_bank_012.mem", mem);
                13: $readmemh("rom_bank_013.mem", mem);
                14: $readmemh("rom_bank_014.mem", mem);
                15: $readmemh("rom_bank_015.mem", mem);
                default: ;
            endcase
        end
    end

    always @(posedge clk) begin
        if (en)
            dout <= mem[addr];
    end
endmodule

module input_rom #(
    parameter integer ADDR_W = `C_ROM_ADDR_W,
    parameter integer DATA_W = `C_PIXEL_W,
    parameter integer MEM_DEPTH = `C_ROM_DEPTH_POW2,
    parameter integer INIT_MODE = 0,
    parameter integer INIT_EN = 0,
    parameter INIT_FILE = ""
)(
    input wire clk,
    input wire en,
    input wire [ADDR_W-1:0] addr,
    output wire [DATA_W-1:0] dout
);
    localparam integer BANK_ADDR_W = (ADDR_W < 15) ? ADDR_W : 15;
    localparam integer BANK_DEPTH = (1 << BANK_ADDR_W);
    localparam integer BANKS = (MEM_DEPTH + BANK_DEPTH - 1) / BANK_DEPTH;
    localparam integer BANK_SEL_W = (BANKS <= 1) ? 1 : $clog2(BANKS);
    wire [DATA_W-1:0] bank_dout [0:BANKS-1];
    reg [BANK_SEL_W-1:0] bank_sel_q;
    genvar b;

    generate
        if (BANKS == 1) begin : g_single_bank
            input_rom_bank #(
                .BANK_ID(0), .BANK_DEPTH(BANK_DEPTH), .ADDR_W(BANK_ADDR_W),
                .DATA_W(DATA_W), .INIT_MODE(INIT_MODE), .INIT_EN(INIT_EN)
            ) u_bank (
                .clk(clk), .en(en), .addr(addr[BANK_ADDR_W-1:0]), .dout(bank_dout[0])
            );
            assign dout = bank_dout[0];
        end else begin : g_multi_bank
            for (b = 0; b < BANKS; b = b + 1) begin : g_bank
                input_rom_bank #(
                    .BANK_ID(b), .BANK_DEPTH(BANK_DEPTH), .ADDR_W(BANK_ADDR_W),
                    .DATA_W(DATA_W), .INIT_MODE(INIT_MODE), .INIT_EN(INIT_EN)
                ) u_bank (
                    .clk(clk),
                    .en(en && (addr[ADDR_W-1:BANK_ADDR_W] == b)),
                    .addr(addr[BANK_ADDR_W-1:0]),
                    .dout(bank_dout[b])
                );
            end

            always @(posedge clk) begin
                if (en)
                    bank_sel_q <= addr[ADDR_W-1:BANK_ADDR_W];
            end

            assign dout = bank_dout[bank_sel_q];
        end
    endgenerate
endmodule

`default_nettype wire