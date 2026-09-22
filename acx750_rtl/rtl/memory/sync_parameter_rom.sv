`timescale 1ns / 1ps

// Team member B: generic synchronous ROM for reviewed .mem parameter files.
// File ownership stays with its producer; this module only consumes the data.
module sync_parameter_rom #(
    parameter integer DATA_W = 8,
    parameter integer DEPTH = 1,
    parameter integer ADDR_W = (DEPTH <= 1) ? 1 : $clog2(DEPTH),
    parameter string MEM_FILE = ""
)(
    input  wire                     clk,
    input  wire                     enable,
    input  wire [ADDR_W-1:0]        address,
    output reg  [DATA_W-1:0]        data
);

    (* rom_style = "block" *) reg [DATA_W-1:0] memory [0:DEPTH-1];

    initial begin
        if (MEM_FILE == "")
            $error("MEM_FILE must name a reviewed parameter file");
        $readmemh(MEM_FILE, memory);
    end

    always @(posedge clk) begin
        if (enable)
            data <= memory[address];
    end

endmodule
