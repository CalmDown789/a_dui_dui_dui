`timescale 1ns / 1ps

// Member B 2026-09-26 experiment. For L3 and L5, a two-slot partial FIFO
// breaks the accumulator-ready combinational path back into the MAC tree.
// Its input ready depends only on registered occupancy. Other layers keep
// the original direct partial/phase/ready connection.
module mac_issue_stage #(
    parameter integer K=3,
    parameter integer CIN=8,
    parameter integer COUT=8,
    parameter integer IN_PAR=1,
    parameter integer OUT_PAR=8,
    parameter integer ACT_W=16,
    parameter integer ACT_UNSIGNED=0,
    parameter integer PIPE_SELECTED_OPERANDS=0
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
    wire mac_partial_ready, acc_partial_valid;
    wire [OUT_PAR*32-1:0] acc_partial_sums;
    wire [2:0] acc_partial_phase;

    eight_phase_issue #(.DATA_W(K*K*CIN*ACT_W)) issue (
        .clk(clk),.rst(rst),.in_valid(window_valid),.in_ready(window_ready),
        .in_window(window_flat),.out_valid(issue_valid),.out_ready(issue_ready),
        .out_window(issue_window),.out_phase(issue_phase),.out_last_phase()
    );
    phase_mac_pipeline #(.K(K),.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),
        .OUT_PAR(OUT_PAR),.ACT_W(ACT_W),.ACT_UNSIGNED(ACT_UNSIGNED),
        .PIPE_SELECTED_OPERANDS(PIPE_SELECTED_OPERANDS)) mac (
        .clk(clk),.rst(rst),.in_valid(issue_valid),.in_ready(issue_ready),
        .in_phase(issue_phase),.window_flat(issue_window),.weight_flat(weight_flat),
        .out_valid(partial_valid),.out_ready(mac_partial_ready),
        .out_phase(partial_phase),.partial_sums(partial_sums)
    );
    generate
        if (((K==3)&&(CIN==8)&&(COUT==8)) || ((K==5)&&(CIN==16)&&(COUT==4))) begin : g_l5_partial_buffer
            // Frozen L3 OUT_PAR=8: 259 bits; frozen L5 OUT_PAR=4: 131 bits.
            // Retain the existing generate label to keep L5 hierarchy stable.
            // Keep the expression parameterized so the concatenation width
            // is never silently truncated if a legal lane setting is used.
            mac_partial_fifo2 #(.DATA_W(3+OUT_PAR*32)) partial_fifo (
                .clk(clk),.rst(rst),
                .in_valid(partial_valid),.in_ready(mac_partial_ready),
                .in_data({partial_phase,partial_sums}),
                .out_valid(acc_partial_valid),.out_ready(acc_phase_ready),
                .out_data({acc_partial_phase,acc_partial_sums}),.occupancy()
            );
        end else begin : g_direct_partial
            assign mac_partial_ready=acc_phase_ready;
            assign acc_partial_valid=partial_valid;
            assign acc_partial_phase=partial_phase;
            assign acc_partial_sums=partial_sums;
        end
    endgenerate
    phase_accumulator #(.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),
        .OUT_PAR(OUT_PAR)) acc (
        .clk(clk),.rst(rst),.phase_valid(acc_partial_valid),.phase_ready(acc_phase_ready),
        .phase(acc_partial_phase),.partial_sums(acc_partial_sums),.bias_flat(bias_flat),
        .out_valid(result_valid),.out_ready(result_ready),.out_data(result_flat)
    );
endmodule

// Two-slot ordered ready/valid FIFO. Full + pop intentionally does not
// accept input that cycle: there is no combinational out_ready -> in_ready
// dependency. Once occupancy is one, simultaneous push/pop sustains one
// token each clock. The output word is held throughout output backpressure.
module mac_partial_fifo2 #(
    parameter integer DATA_W=131
)(
    input  wire clk,
    input  wire rst,
    input  wire in_valid,
    output wire in_ready,
    input  wire [DATA_W-1:0] in_data,
    output wire out_valid,
    input  wire out_ready,
    output wire [DATA_W-1:0] out_data,
    output wire [1:0] occupancy
);
    reg [DATA_W-1:0] data_q[0:1];
    reg wr_ptr, rd_ptr;
    reg [1:0] count;
    wire push=in_valid&&in_ready;
    wire pop=out_valid&&out_ready;
    assign in_ready=(count<2'd2);
    assign out_valid=(count!=2'd0);
    assign out_data=data_q[rd_ptr];
    assign occupancy=count;

    initial if(DATA_W<1)$error("mac_partial_fifo2 requires DATA_W>=1");
    always @(posedge clk)begin
        if(rst)begin
            wr_ptr<=0;
            rd_ptr<=0;
            count<=0;
        end else begin
            if(push)begin
                data_q[wr_ptr]<=in_data;
                wr_ptr<=!wr_ptr;
            end
            if(pop)rd_ptr<=!rd_ptr;
            case({push,pop})
                2'b10: count<=count+2'd1;
                2'b01: count<=count-2'd1;
                default: count<=count;
            endcase
        end
    end
endmodule
