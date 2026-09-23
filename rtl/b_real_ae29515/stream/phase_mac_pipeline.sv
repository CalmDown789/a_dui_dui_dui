`timescale 1ns / 1ps

// 成员B工作 / Team member B: elastic multiply plus balanced reduction tree.
// One phase may enter each clock. Every tree level and its phase tag stop
// together under backpressure. The final 32-bit partial sum has the same
// wrap semantics as phase_mac_array; target DSP/timing mapping is unverified.
module phase_mac_pipeline #(
    parameter integer K=5,
    parameter integer CIN=16,
    parameter integer COUT=4,
    parameter integer IN_PAR=2,
    parameter integer OUT_PAR=4,
    parameter integer ACT_W=16,
    parameter integer ACT_UNSIGNED=0
)(
    input  wire                              clk,
    input  wire                              rst,
    input  wire                              in_valid,
    output wire                              in_ready,
    input  wire [2:0]                        in_phase,
    input  wire [K*K*CIN*ACT_W-1:0]         window_flat,
    input  wire [COUT*CIN*K*K*8-1:0]        weight_flat,
    output wire                              out_valid,
    input  wire                              out_ready,
    output wire [2:0]                        out_phase,
    output wire [OUT_PAR*32-1:0]            partial_sums
);
    localparam integer TAPS=K*K;
    localparam integer TERMS=IN_PAR*TAPS;
    localparam integer LEVELS=(TERMS<=1)?0:$clog2(TERMS);
    localparam integer IN_GROUPS=CIN/IN_PAR;
    localparam integer MAX_TERMS=1<<LEVELS;
    reg [LEVELS:0] valid_q;
    reg [2:0] phase_q[0:LEVELS];
    reg signed [31:0] sums_q[0:LEVELS][0:OUT_PAR-1][0:MAX_TERMS-1];
    wire [LEVELS:0] ready;
    wire [2:0] group_out=in_phase/IN_GROUPS;
    wire [2:0] group_in=in_phase%IN_GROUPS;
    assign ready[LEVELS]=!valid_q[LEVELS]||out_ready;
    assign in_ready=ready[0];
    assign out_valid=valid_q[LEVELS];
    assign out_phase=phase_q[LEVELS];

    initial begin
        if((K!=1&&K!=3&&K!=5)||CIN<1||COUT<1||IN_PAR<1||OUT_PAR<1||
           CIN%IN_PAR!=0||COUT%OUT_PAR!=0||
           (CIN/IN_PAR)*(COUT/OUT_PAR)!=8||
           (ACT_W!=8&&ACT_W!=16))
            $error("phase_mac_pipeline requires frozen eight-phase layout");
    end

    genvar o,n,s,j;
    generate
        for(o=0;o<OUT_PAR;o=o+1)begin:out_lane
            assign partial_sums[o*32+:32]=sums_q[LEVELS][o][0];
            for(n=0;n<TERMS;n=n+1)begin:mult_lane
                localparam integer I=n/TAPS;
                localparam integer TAP=n%TAPS;
                wire [31:0] oc=group_out*OUT_PAR+o;
                wire [31:0] ic=group_in*IN_PAR+I;
                wire [ACT_W-1:0] act=window_flat[(TAP*CIN+ic)*ACT_W+:ACT_W];
                wire signed [ACT_W:0] act_ext;
                if(ACT_UNSIGNED!=0)begin:unsigned_act
                    assign act_ext=$signed({1'b0,act});
                end else begin:signed_act
                    assign act_ext=$signed({act[ACT_W-1],act});
                end
                wire signed [7:0] weight=weight_flat[((oc*CIN+ic)*TAPS+TAP)*8+:8];
                (* use_dsp="yes" *) wire signed [ACT_W+8:0] product=act_ext*weight;
                always @(posedge clk)if(ready[0]&&in_valid)
                    sums_q[0][o][n]<=product;
            end
        end
        for(s=1;s<=LEVELS;s=s+1)begin:tree_stage
            localparam integer PREV_COUNT=(TERMS+(1<<(s-1))-1)>>(s-1);
            localparam integer COUNT=(TERMS+(1<<s)-1)>>s;
            assign ready[s-1]=!valid_q[s-1]||ready[s];
            for(o=0;o<OUT_PAR;o=o+1)begin:channel
                for(j=0;j<COUNT;j=j+1)begin:node
                    if(2*j+1<PREV_COUNT)begin:pair
                        (* use_dsp="no" *) wire signed [31:0] added=
                            sums_q[s-1][o][2*j]+sums_q[s-1][o][2*j+1];
                        always @(posedge clk)if(ready[s]&&valid_q[s-1])
                            sums_q[s][o][j]<=added;
                    end else begin:single
                        always @(posedge clk)if(ready[s]&&valid_q[s-1])
                            sums_q[s][o][j]<=sums_q[s-1][o][2*j];
                    end
                end
            end
            always @(posedge clk)begin
                if(rst)valid_q[s]<=0;
                else if(ready[s])begin
                    valid_q[s]<=valid_q[s-1];
                    if(valid_q[s-1])phase_q[s]<=phase_q[s-1];
                end
            end
        end
    endgenerate
    always @(posedge clk)begin
        if(rst)valid_q[0]<=0;
        else if(ready[0])begin
            valid_q[0]<=in_valid;
            if(in_valid)phase_q[0]<=in_phase;
        end
    end
endmodule
