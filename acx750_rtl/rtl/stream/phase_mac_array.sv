`timescale 1ns / 1ps

// 成员B工作 / Team member B: functional parallel MAC datapath for one phase.
// Window is tap-major HWC; weight_flat is OIHW. The combinational reduction
// is a bit-exact integration baseline. Timing closure needs a pipelined tree.
module phase_mac_array #(
    parameter integer K=5,
    parameter integer CIN=16,
    parameter integer COUT=4,
    parameter integer IN_PAR=2,
    parameter integer OUT_PAR=4,
    parameter integer ACT_W=16,
    parameter integer ACT_UNSIGNED=0
)(
    input  wire [2:0]                          phase,
    input  wire [K*K*CIN*ACT_W-1:0]          window_flat,
    input  wire [COUT*CIN*K*K*8-1:0]         weight_flat,
    output reg  [OUT_PAR*32-1:0]             partial_sums
);
    localparam integer TAPS=K*K;
    localparam integer IN_GROUPS=CIN/IN_PAR;
    integer o,i,t,oc,ic,group_out,group_in;
    reg signed [ACT_W:0] act_ext;
    reg signed [7:0] weight;
    reg signed [47:0] sum;
    always @*begin
        group_out=phase/IN_GROUPS;
        group_in=phase%IN_GROUPS;
        partial_sums=0;
        for(o=0;o<OUT_PAR;o=o+1)begin
            oc=group_out*OUT_PAR+o;
            sum=0;
            for(i=0;i<IN_PAR;i=i+1)begin
                ic=group_in*IN_PAR+i;
                for(t=0;t<TAPS;t=t+1)begin
                    if(ACT_UNSIGNED!=0)
                        act_ext={1'b0,window_flat[(t*CIN+ic)*ACT_W+:ACT_W]};
                    else
                        act_ext={window_flat[(t*CIN+ic)*ACT_W+ACT_W-1],
                                 window_flat[(t*CIN+ic)*ACT_W+:ACT_W]};
                    weight=weight_flat[((oc*CIN+ic)*TAPS+t)*8+:8];
                    sum=sum+act_ext*weight;
                end
            end
            partial_sums[o*32+:32]=sum[31:0];
        end
    end
    initial begin
        if((K!=1&&K!=3&&K!=5)||CIN<1||COUT<1||IN_PAR<1||OUT_PAR<1||
           CIN%IN_PAR!=0||COUT%OUT_PAR!=0||
           (CIN/IN_PAR)*(COUT/OUT_PAR)!=8||
           (ACT_W!=8&&ACT_W!=16))
            $error("phase_mac_array requires frozen eight-phase layer layout");
    end
endmodule
