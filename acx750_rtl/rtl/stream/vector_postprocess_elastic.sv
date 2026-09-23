`timescale 1ns / 1ps

// 成员B工作 / Team member B: parallel per-channel fixed-point postprocess
// with a reserved-capacity FIFO for its four-cycle non-stallable pipeline.
// Parallel Q31/PReLU units are a functional baseline; DSP/fabric sharing
// remains to be optimized before claiming the 16-DSP postprocess allowance.
module vector_postprocess_elastic #(
    parameter integer CHANNELS=16,
    parameter integer OUT_W=16,
    parameter integer OUT_SIGNED=1,
    parameter integer APPLY_PRELU=1,
    parameter integer FIFO_DEPTH=8
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
    wire [CHANNELS*OUT_W-1:0] post_data;
    wire [CHANNELS-1:0] post_valid;
    wire fifo_ready;
    wire [$clog2(FIFO_DEPTH+1)-1:0] occupancy;
    reg [3:0] pending;
    wire fire=in_valid&&in_ready;
    wire [4:0] pending_count=pending[0]+pending[1]+pending[2]+pending[3];
    assign in_ready=(occupancy+pending_count<FIFO_DEPTH);
    initial if(CHANNELS<1||FIFO_DEPTH<5)
        $error("vector_postprocess_elastic parameters invalid");
    always @(posedge clk)begin
        if(rst)pending<=0;
        else pending<={pending[2:0],fire};
    end
    genvar c;
    generate for(c=0;c<CHANNELS;c=c+1)begin:post_channels
        prelu_requantize #(.OUT_W(OUT_W),.OUT_SIGNED(OUT_SIGNED),
            .APPLY_PRELU(APPLY_PRELU)) post (
            .clk(clk),.rst(rst),.in_valid(fire),
            .accumulator_int32(accum_flat[c*32+:32]),
            .prelu_q15(prelu_flat[c*16+:16]),
            .multiplier_q31(q31_flat[c*32+:32]),
            .out_data(post_data[c*OUT_W+:OUT_W]),.out_valid(post_valid[c])
        );
    end endgenerate
    elastic_fifo #(.DATA_W(CHANNELS*OUT_W),.DEPTH(FIFO_DEPTH)) fifo (
        .clk(clk),.rst(rst),.in_valid(post_valid[0]),.in_ready(fifo_ready),
        .in_data(post_data),.out_valid(out_valid),.out_ready(out_ready),
        .out_data(out_flat),.occupancy(occupancy)
    );
`ifndef SYNTHESIS
    integer i;
    always @(posedge clk)if(!rst)begin
        if(post_valid[0]&&!fifo_ready)$fatal(1,"postprocess FIFO overflow");
        for(i=1;i<CHANNELS;i=i+1)
            if(post_valid[i]!==post_valid[0])$fatal(1,"postprocess channel valid skew");
    end
`endif
endmodule
