`timescale 1ns / 1ps

// 成员B工作 / Team member B: one spatial window through 8 phases to INT32.
// Parameter buses are supplied by member-A-owned ROM integration. This
// MAC products and balanced reduction levels are elastic clock stages;
// target timing and DSP mapping still require synthesis.
module mac_issue_stage #(
    parameter integer K=3,
    parameter integer CIN=8,
    parameter integer COUT=8,
    parameter integer IN_PAR=1,
    parameter integer OUT_PAR=8,
    parameter integer ACT_W=16,
    parameter integer ACT_UNSIGNED=0
)(
    input  wire                          clk,
    input  wire                          rst,
    input  wire                          window_valid,
    output wire                          window_ready,
    input  wire [K*K*CIN*ACT_W-1:0]      window_flat,
    input  wire [COUT*CIN*K*K*8-1:0]     weight_flat,
    input  wire [COUT*32-1:0]           bias_flat,
    output wire                          result_valid,
    input  wire                          result_ready,
    output wire [COUT*32-1:0]           result_flat
);
    wire issue_valid,issue_ready,acc_phase_ready,partial_valid;
    wire [K*K*CIN*ACT_W-1:0] issue_window;
    wire [2:0] issue_phase;
    wire [OUT_PAR*32-1:0] partial_sums;
    wire [2:0] partial_phase;
    eight_phase_issue #(.DATA_W(K*K*CIN*ACT_W)) issue (
        .clk(clk),.rst(rst),.in_valid(window_valid),.in_ready(window_ready),
        .in_window(window_flat),.out_valid(issue_valid),.out_ready(issue_ready),
        .out_window(issue_window),.out_phase(issue_phase),.out_last_phase()
    );
    phase_mac_pipeline #(.K(K),.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),
        .OUT_PAR(OUT_PAR),.ACT_W(ACT_W),.ACT_UNSIGNED(ACT_UNSIGNED)) mac (
        .clk(clk),.rst(rst),.in_valid(issue_valid),.in_ready(issue_ready),
        .in_phase(issue_phase),.window_flat(issue_window),.weight_flat(weight_flat),
        .out_valid(partial_valid),.out_ready(acc_phase_ready),
        .out_phase(partial_phase),.partial_sums(partial_sums)
    );
    phase_accumulator #(.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),
        .OUT_PAR(OUT_PAR)) acc (
        .clk(clk),.rst(rst),.phase_valid(partial_valid),.phase_ready(acc_phase_ready),
        .phase(partial_phase),.partial_sums(partial_sums),.bias_flat(bias_flat),
        .out_valid(result_valid),.out_ready(result_ready),.out_data(result_flat)
    );
endmodule
