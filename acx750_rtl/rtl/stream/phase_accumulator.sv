`timescale 1ns / 1ps

// 成员B工作 / Team member B: assemble eight MAC phases into one HWC pixel.
// Each phase contributes OUT_PAR signed 32-bit partial sums. Partial sums
// already include all IN_PAR input channels and K*K taps assigned to that
// phase. Bias is applied once at phase 7, then the widened result saturates.
module phase_accumulator #(
    parameter integer CIN=16,
    parameter integer COUT=4,
    parameter integer IN_PAR=2,
    parameter integer OUT_PAR=4
)(
    input  wire                      clk,
    input  wire                      rst,
    input  wire                      phase_valid,
    output wire                      phase_ready,
    input  wire [2:0]                phase,
    input  wire [OUT_PAR*32-1:0]     partial_sums,
    input  wire [COUT*32-1:0]       bias_flat,
    output reg                       out_valid,
    input  wire                      out_ready,
    output reg  [COUT*32-1:0]       out_data
);
    localparam integer IN_GROUPS=CIN/IN_PAR;
    localparam integer OUT_GROUPS=COUT/OUT_PAR;
    reg signed [47:0] accum[0:COUT-1];
    reg [2:0] expected_phase;
    wire fire=phase_valid&&phase_ready;
    assign phase_ready=!out_valid||out_ready;

    function automatic [31:0] sat_i32;
        input signed [47:0] value;
        begin
            if(value>48'sd2147483647)sat_i32=32'h7fffffff;
            else if(value< -48'sd2147483648)sat_i32=32'h80000000;
            else sat_i32=value[31:0];
        end
    endfunction

    initial begin
        if(CIN<1||COUT<1||IN_PAR<1||OUT_PAR<1||
           CIN%IN_PAR!=0||COUT%OUT_PAR!=0||IN_GROUPS*OUT_GROUPS!=8)
            $error("phase_accumulator parameters must cover eight phases");
    end

    integer c,group;
    reg signed [47:0] next_sum;
    always @(posedge clk)begin
        if(rst)begin
            out_valid<=0;
            out_data<=0;
            expected_phase<=0;
            for(c=0;c<COUT;c=c+1)accum[c]<=0;
        end else begin
            if(out_valid&&out_ready)out_valid<=0;
            if(fire)begin
`ifndef SYNTHESIS
                if(phase!==expected_phase)
                    $fatal(1,"phase_accumulator phase order violation");
`endif
                expected_phase<=expected_phase+1'b1;
                group=phase/IN_GROUPS;
                for(c=0;c<COUT;c=c+1)begin
                    next_sum=(phase==0)?48'sd0:accum[c];
                    if(c/OUT_PAR==group)
                        next_sum=next_sum+$signed(partial_sums[(c%OUT_PAR)*32+:32]);
                    accum[c]<=next_sum;
                    if(phase==3'd7)
                        out_data[c*32+:32]<=sat_i32(next_sum+$signed(bias_flat[c*32+:32]));
                end
                if(phase==3'd7)out_valid<=1;
            end
        end
    end
endmodule
