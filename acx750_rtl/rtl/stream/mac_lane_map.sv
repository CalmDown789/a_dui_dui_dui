`timescale 1ns / 1ps

// 成员B工作 / Team member B: one lane's OIHW address during an 8-phase issue.
// Instantiate with constant LANE per MAC lane. PHASE is shared by every lane.
// This is an address/control map, not a multiplier or implemented DSP claim.
module mac_lane_map #(
    parameter integer K = 5,
    parameter integer CIN = 16,
    parameter integer COUT = 4,
    parameter integer IN_PAR = 2,
    parameter integer OUT_PAR = 4,
    parameter integer LANE = 0
)(
    input  wire [2:0] phase,
    output wire [7:0] out_channel,
    output wire [7:0] in_channel,
    output wire [5:0] tap_index,
    output wire [31:0] weight_oihw_address
);
    localparam integer TAPS=K*K;
    localparam integer IN_GROUPS=CIN/IN_PAR;
    localparam integer OUT_GROUPS=COUT/OUT_PAR;
    localparam integer LANES=IN_PAR*OUT_PAR*TAPS;
    localparam integer LOCAL_OUT=LANE/(IN_PAR*TAPS);
    localparam integer LOCAL_IN=(LANE/TAPS)%IN_PAR;
    localparam integer LOCAL_TAP=LANE%TAPS;
    wire [7:0] out_group=phase/IN_GROUPS;
    wire [7:0] in_group=phase%IN_GROUPS;
    assign out_channel=out_group*OUT_PAR+LOCAL_OUT;
    assign in_channel=in_group*IN_PAR+LOCAL_IN;
    assign tap_index=LOCAL_TAP;
    assign weight_oihw_address=((out_channel*CIN+in_channel)*TAPS)+tap_index;

    initial begin
        if(K<1||CIN<1||COUT<1||IN_PAR<1||OUT_PAR<1||
           CIN%IN_PAR!=0||COUT%OUT_PAR!=0||
           IN_GROUPS*OUT_GROUPS!=8||LANE<0||LANE>=LANES)
            $error("mac_lane_map parameters must cover exactly eight phases");
    end
endmodule
