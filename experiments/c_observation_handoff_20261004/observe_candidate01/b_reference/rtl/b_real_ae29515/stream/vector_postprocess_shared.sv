`timescale 1ns / 1ps

// 成员B工作 / Team member B: two-slot, time-shared PReLU/Q31 postprocess.
// LANES=2 for 16 channels, LANES=1 for 8/4 channels. A new vector can be
// accepted every eight clocks when the downstream side keeps up. Each slot
// remains occupied until its fully assembled output token is consumed.
module vector_postprocess_shared #(
    parameter integer CHANNELS=16,
    parameter integer LANES=2,
    parameter integer OUT_W=16,
    parameter integer OUT_SIGNED=1,
    parameter integer APPLY_PRELU=1
)(
    input  wire                      clk,
    input  wire                      rst,
    input  wire                      in_valid,
    output wire                      in_ready,
    input  wire [CHANNELS*32-1:0]     accum_flat,
    input  wire [CHANNELS*16-1:0]     prelu_flat,
    input  wire [CHANNELS*32-1:0]     q31_flat,
    output wire                      out_valid,
    input  wire                      out_ready,
    output wire [CHANNELS*OUT_W-1:0] out_flat
);
    localparam integer GROUPS=CHANNELS/LANES;
    reg [CHANNELS*32-1:0] input_slot[0:1];
    reg [CHANNELS*OUT_W-1:0] output_slot[0:1];
    reg [3:0] issued[0:1],completed[0:1];
    reg [1:0] occupied,ready_slot;
    reg write_slot,issue_slot,read_slot;
    reg [3:0] meta_valid;
    reg [3:0] meta_group[0:3];
    reg [3:0] meta_slot;
    wire issue_valid=occupied[issue_slot]&&(issued[issue_slot]<GROUPS);
    wire [3:0] issue_group=issued[issue_slot];
    wire input_fire=in_valid&&in_ready;
    wire output_fire=out_valid&&out_ready;
    wire [LANES-1:0] lane_valid;
    wire [LANES*OUT_W-1:0] lane_data;
    assign in_ready=!occupied[write_slot];
    assign out_valid=ready_slot[read_slot];
    assign out_flat=output_slot[read_slot];
    initial begin
        if(CHANNELS<1||LANES<1||CHANNELS%LANES!=0||GROUPS>8)
            $error("vector_postprocess_shared needs 1..8 groups");
    end
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1)begin:units
        wire [31:0] selected_accum=
            input_slot[issue_slot][(issue_group*LANES+lane)*32+:32];
        wire [15:0] selected_prelu=
            prelu_flat[(issue_group*LANES+lane)*16+:16];
        wire [31:0] selected_q31=
            q31_flat[(issue_group*LANES+lane)*32+:32];
        prelu_requantize #(.OUT_W(OUT_W),.OUT_SIGNED(OUT_SIGNED),
            .APPLY_PRELU(APPLY_PRELU)) post (
            .clk(clk),.rst(rst),.in_valid(issue_valid),
            .accumulator_int32(selected_accum),.prelu_q15(selected_prelu),
            .multiplier_q31(selected_q31),
            .out_data(lane_data[lane*OUT_W+:OUT_W]),.out_valid(lane_valid[lane])
        );
    end endgenerate
    integer i;
    always @(posedge clk)begin
        if(rst)begin
            occupied<=0;ready_slot<=0;
            write_slot<=0;issue_slot<=0;read_slot<=0;
            issued[0]<=0;issued[1]<=0;
            completed[0]<=0;completed[1]<=0;
            input_slot[0]<=0;input_slot[1]<=0;
            output_slot[0]<=0;output_slot[1]<=0;
            meta_valid<=0;meta_slot<=0;
            for(i=0;i<4;i=i+1)meta_group[i]<=0;
        end else begin
            meta_valid<={meta_valid[2:0],issue_valid};
            meta_slot<={meta_slot[2:0],issue_slot};
            meta_group[0]<=issue_group;
            for(i=1;i<4;i=i+1)meta_group[i]<=meta_group[i-1];
            if(input_fire)begin
                input_slot[write_slot]<=accum_flat;
                issued[write_slot]<=0;
                completed[write_slot]<=0;
                occupied[write_slot]<=1;
                ready_slot[write_slot]<=0;
                write_slot<=!write_slot;
            end
            if(issue_valid)begin
                issued[issue_slot]<=issued[issue_slot]+1'b1;
                if(issue_group==GROUPS-1)issue_slot<=!issue_slot;
            end
            if(lane_valid[0])begin
                for(i=0;i<LANES;i=i+1)
                    output_slot[meta_slot[3]][(meta_group[3]*LANES+i)*OUT_W+:OUT_W]
                        <=lane_data[i*OUT_W+:OUT_W];
                completed[meta_slot[3]]<=completed[meta_slot[3]]+1'b1;
                if(completed[meta_slot[3]]==GROUPS-1)
                    ready_slot[meta_slot[3]]<=1;
            end
            if(output_fire)begin
                occupied[read_slot]<=0;
                ready_slot[read_slot]<=0;
                read_slot<=!read_slot;
            end
        end
    end
`ifndef SYNTHESIS
    always @(posedge clk)if(!rst)begin
        for(integer v=1;v<LANES;v=v+1)
            if(lane_valid[v]!==lane_valid[0])$fatal(1,"postprocess lane valid skew");
        if(lane_valid[0]&&!meta_valid[3])$fatal(1,"postprocess metadata latency mismatch");
    end
`endif
endmodule
