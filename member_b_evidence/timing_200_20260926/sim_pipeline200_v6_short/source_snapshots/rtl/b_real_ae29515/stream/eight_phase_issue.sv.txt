`timescale 1ns / 1ps

// 成员B工作 / Team member B: eight-cycle window issue controller.
// Each accepted spatial window is held for eight successful output transfers.
// The phase denotes the scheduled MAC slice (0..7); layer-specific output
// channel and input-channel lane mapping belongs to the layer datapath.
module eight_phase_issue #(
    parameter integer DATA_W = 256
)(
    input  wire                  clk,
    input  wire                  rst,
    input  wire                  in_valid,
    output wire                  in_ready,
    input  wire [DATA_W-1:0]     in_window,
    output wire                  out_valid,
    input  wire                  out_ready,
    output reg  [DATA_W-1:0]     out_window,
    output reg  [2:0]           out_phase,
    output wire                  out_last_phase
);
    reg active;
    wire fire=out_valid&&out_ready;
    assign out_valid=active;
    assign out_last_phase=active&&(out_phase==3'd7);
    assign in_ready=!active||(fire&&(out_phase==3'd7));

    initial if(DATA_W<1)$error("DATA_W must be positive");
    always @(posedge clk)begin
        if(rst)begin
            active<=0;
            out_window<=0;
            out_phase<=0;
        end else begin
            if(fire)begin
                if(out_phase==3'd7)begin
                    if(in_valid&&in_ready)begin
                        out_window<=in_window;
                        out_phase<=0;
                        active<=1;
                    end else begin
                        active<=0;
                        out_phase<=0;
                    end
                end else out_phase<=out_phase+1'b1;
            end else if(in_valid&&in_ready)begin
                out_window<=in_window;
                out_phase<=0;
                active<=1;
            end
        end
    end
endmodule
