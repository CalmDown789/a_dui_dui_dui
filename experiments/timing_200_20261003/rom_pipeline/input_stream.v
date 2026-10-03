// Experimental C input path. Pair with latency-three rom_pipeline/input_rom.v.
// Ports and delivered data/coordinate order are unchanged. Startup latency
// increases; three requests may be in flight and reserve response-queue entries.
`timescale 1ns/1ps
`default_nettype none
`include "c_config.vh"
module input_stream #(
    parameter integer IMG_W=`C_IMG_W, IMG_H=`C_IMG_H,
    parameter integer PIXEL_W=`C_PIXEL_W, ADDR_W=`C_ROM_ADDR_W,
    parameter integer TOT_PIX=`C_IN_PIXELS
)(
    input wire clk, rst_n, start_load,
    output wire in_valid,
    output wire [PIXEL_W-1:0] in_data,
    input wire in_ready,
    output wire rom_en,
    output wire [ADDR_W-1:0] rom_addr,
    input wire [PIXEL_W-1:0] rom_dout,
    output wire input_active, input_done,
    output wire [15:0] dbg_x, dbg_y
);
    localparam integer XW=(IMG_W<=1)?1:$clog2(IMG_W);
    localparam integer YW=(IMG_H<=1)?1:$clog2(IMG_H);
    reg run_q, done_q, exhausted_q;
    reg [ADDR_W-1:0] req_addr_q;
    reg [XW-1:0] req_x_q, x_p1, x_p2, x_p3;
    reg [YW-1:0] req_y_q, y_p1, y_p2, y_p3;
    reg pending1_q, pending2_q, pending3_q, last_p1, last_p2, last_p3;
    reg [2:0] count_q;
    reg [1:0] wr_q, rd_q;
    (* ram_style="registers" *) reg [PIXEL_W-1:0] data_q[0:3];
    (* ram_style="registers" *) reg [XW-1:0] x_q[0:3];
    (* ram_style="registers" *) reg [YW-1:0] y_q[0:3];
    reg last_q[0:3];

    // Capacity includes responses already queued and all pipeline stages.
    // An output handshake can release one credit on the same edge.
    wire [3:0] reserved={1'b0,count_q}+{3'b0,pending1_q}+{3'b0,pending2_q}+{3'b0,pending3_q};
    wire pop=in_valid && in_ready;
    wire request=run_q && !exhausted_q && !start_load &&
                 ((reserved<4) || pop);
    wire response=pending3_q;
    assign rom_en=request;
    assign rom_addr=req_addr_q;
    assign in_valid=(count_q!=0) && !start_load;
    assign in_data=data_q[rd_q];
    assign dbg_x={{(16-XW){1'b0}},x_q[rd_q]};
    assign dbg_y={{(16-YW){1'b0}},y_q[rd_q]};
    assign input_active=run_q;
    assign input_done=done_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            run_q<=0; done_q<=0; exhausted_q<=(TOT_PIX<=0);
            req_addr_q<=0; req_x_q<=0; req_y_q<=0;
            pending1_q<=0; pending2_q<=0; pending3_q<=0;
            x_p1<=0; x_p2<=0; x_p3<=0; y_p1<=0; y_p2<=0; y_p3<=0;
            last_p1<=0; last_p2<=0; last_p3<=0;
            count_q<=0; wr_q<=0; rd_q<=0;
        end else if (start_load) begin
            run_q<=1; done_q<=0; exhausted_q<=(TOT_PIX<=0);
            req_addr_q<=0; req_x_q<=0; req_y_q<=0;
            pending1_q<=0; pending2_q<=0; pending3_q<=0;
            x_p1<=0; x_p2<=0; x_p3<=0; y_p1<=0; y_p2<=0; y_p3<=0;
            last_p1<=0; last_p2<=0; last_p3<=0;
            count_q<=0; wr_q<=0; rd_q<=0;
        end else begin
            // Bank request at N, BRAM read N+1, DO_REG N+2,
            // queue capture N+3. Metadata follows those same edges.
            pending1_q<=request;
            pending2_q<=pending1_q;
            pending3_q<=pending2_q;
            if (request) begin
                x_p1<=req_x_q; y_p1<=req_y_q;
                last_p1<=(req_addr_q==TOT_PIX-1);
                req_addr_q<=req_addr_q+1'b1;
                if (req_addr_q==TOT_PIX-1) exhausted_q<=1;
                if (req_x_q==IMG_W-1) begin
                    req_x_q<=0;
                    if (req_y_q!=IMG_H-1) req_y_q<=req_y_q+1'b1;
                end else req_x_q<=req_x_q+1'b1;
            end
            if (pending1_q) begin
                x_p2<=x_p1; y_p2<=y_p1; last_p2<=last_p1;
            end
            if (pending2_q) begin
                x_p3<=x_p2; y_p3<=y_p2; last_p3<=last_p2;
            end
            if (response) begin
                data_q[wr_q]<=rom_dout;
                x_q[wr_q]<=x_p3; y_q[wr_q]<=y_p3;
                last_q[wr_q]<=last_p3;
                wr_q<=wr_q+1'b1;
            end
            if (pop) begin
                rd_q<=rd_q+1'b1;
                if (last_q[rd_q]) begin run_q<=0; done_q<=1; end
            end
            case ({response,pop})
                2'b10: count_q<=count_q+1'b1;
                2'b01: count_q<=count_q-1'b1;
                default: count_q<=count_q;
            endcase
        end
    end
`ifndef SYNTHESIS
    always @(posedge clk) if (rst_n && !start_load) begin
        if (reserved>4) $fatal(1,"C ROM response credit overflow");
        if (response && count_q==4 && !pop)
            $fatal(1,"C ROM response overwrites full queue");
        if (done_q && (count_q!=0 || pending1_q || pending2_q || pending3_q))
            $fatal(1,"C ROM done with outstanding responses");
    end
`endif
endmodule
`default_nettype wire
