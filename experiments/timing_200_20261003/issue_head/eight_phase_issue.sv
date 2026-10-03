`timescale 1ns/1ps
// Experimental direct FIFO-head sequencer. The ready/valid source must keep
// its head word stable until in_ready, just as any compliant stream producer.
// Read the same head for eight successful MAC transfers; consume it only on
// phase 7. No separate DATA_W-bit window copy is needed. MAC backpressure
// holds phase and the upstream FIFO holds the word.
module eight_phase_issue #(parameter integer DATA_W=256)(
    input wire clk,rst,in_valid,
    output wire in_ready,
    input wire [DATA_W-1:0] in_window,
    output wire out_valid,
    input wire out_ready,
    output wire [DATA_W-1:0] out_window,
    output reg [2:0] out_phase,
    output wire out_last_phase
);
    wire fire=in_valid && out_ready;
    assign out_valid=in_valid;
    assign out_window=in_window;
    assign out_last_phase=in_valid && (out_phase==3'd7);
    assign in_ready=out_ready && (out_phase==3'd7);
    always @(posedge clk) begin
        if (rst) out_phase<=0;
        else if (fire) out_phase<=out_phase+1'b1;
    end
endmodule
