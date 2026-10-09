`timescale 1ns/1ps
`default_nettype none
// Candidate: 4096B holds at least two maximum 1088B packets.
// Whole, already-validated packets cross unrelated clocks through Xilinx XPM
// FIFOs. Reserve capacity for the entire packet before accepting its first byte.
// Publish metadata only with the final data write. The reader waits until all
// corresponding bytes are visible before presenting a non-interleaved packet.
// rst must remain asserted for >=3 wr_clk cycles; both clocks must be running
// during reset release. Top level must assert reset when either clock is lost.
module packet_async_bridge #(
 parameter integer EXTERNAL_RD_RESET=0
)(
 input wire wr_clk,rd_clk,rst,rd_domain_reset,
 input wire s_valid,output wire s_ready,input wire[7:0]s_data,input wire s_last,
 input wire[15:0]s_length,input wire[95:0]s_metadata,
 output wire m_valid,input wire m_ready,output wire[7:0]m_data,output wire m_last,
 output wire[15:0]m_length,output wire[95:0]m_metadata,
 output reg protocol_error
);
 (* ASYNC_REG="TRUE" *)reg[1:0]wr_reset_q,rd_reset_q;
 // Physical parent can own the one receive-domain reset synchronizer.
 // This override affects the read gate only. XPM reset remains write-owned.
 wire rd_request=EXTERNAL_RD_RESET?rd_domain_reset:rst;
 always @(posedge wr_clk or posedge rst)if(rst)wr_reset_q<=3;else wr_reset_q<={wr_reset_q[0],1'b0};
 always @(posedge rd_clk or posedge rd_request)if(rd_request)rd_reset_q<=3;else rd_reset_q<={rd_reset_q[0],1'b0};
 // XPM's reset FSM requires BOTH edges of its reset synchronous to wr_clk.
 // Domain gates stop traffic immediately. A separate two-FF synchronizer
 // samples BOTH edges of the raw request; no async preset from the domain
 // gate is allowed to bypass its first synchronizer. INIT11 holds reset on
 // FPGA startup. Both request edges then reach XPM only on wr_clk edges.
 (* ASYNC_REG="TRUE" *)reg[1:0]fifo_reset_pipe_q=2'b11;
 always @(posedge wr_clk)fifo_reset_pipe_q<={fifo_reset_pipe_q[0],rst};
 wire fifo_reset_q=fifo_reset_pipe_q[1];
 reg writing_q,reading_q,reserved_q;reg[15:0]wr_length_q,wr_index_q,rd_length_q,rd_index_q,reserved_length_q;
 reg[95:0]wr_metadata_q,rd_metadata_q,reserved_metadata_q;
 reg[15:0]wr_last_index_q,rd_last_index_q;
 wire data_full,data_empty,meta_full,meta_empty,dwrbusy,drdbusy,mwrbusy,mrdbusy;
 wire[12:0]wr_count,rd_count;wire[7:0]fifo_data;wire[111:0]fifo_meta;
 wire wr_ok=!wr_reset_q[1]&&!dwrbusy&&!mwrbusy&&!protocol_error;
 wire reserve_ok=s_length>=64&&s_length<=1088&&!meta_full&&wr_count<=4095-s_length;
 // Register the whole-packet reservation before acknowledging its first byte.
 // One writer owns this FIFO; while waiting for the first byte, reads can only
 // increase free space. Thus the grant remains valid until consumed/reset.
 // This breaks length subtraction/comparison -> downstream ready -> upstream
 // descriptor/parser clock-enable paths without relaxing packet capacity.
 assign s_ready=wr_ok&&!data_full&&(writing_q||reserved_q);
 wire push=s_valid&&s_ready;
 wire[15:0]current_length=writing_q?wr_length_q:s_length;
 wire final_byte=writing_q?(wr_index_q==wr_last_index_q):(s_length==1);
 wire meta_push=push&&s_last&&final_byte;
 wire[111:0]meta_in={writing_q?wr_metadata_q:s_metadata,current_length};
 wire rd_ok=!rd_reset_q[1]&&!drdbusy&&!mrdbusy;
 wire meta_pop=rd_ok&&!reading_q&&!meta_empty&&rd_count>=fifo_meta[15:0];
 assign m_valid=rd_ok&&reading_q&&!data_empty;
 assign m_data=fifo_data;
 assign m_last=reading_q&&rd_index_q==rd_last_index_q;
 assign m_length=rd_length_q;assign m_metadata=rd_metadata_q;
 wire pop=m_valid&&m_ready;
 always @(posedge wr_clk)begin
  if(wr_reset_q[1])begin writing_q<=0;reserved_q<=0;reserved_length_q<=0;reserved_metadata_q<=0;
   wr_length_q<=0;wr_index_q<=0;wr_last_index_q<=0;wr_metadata_q<=0;protocol_error<=0;end
  else begin
   if(!writing_q&&!reserved_q&&s_valid&&wr_ok&&reserve_ok)begin
    reserved_q<=1;reserved_length_q<=s_length;reserved_metadata_q<=s_metadata;
   end
   if(push)begin
    if(s_last!=final_byte || (writing_q&&(s_length!=wr_length_q||s_metadata!=wr_metadata_q)) ||
     (!writing_q&&(s_length!=reserved_length_q||s_metadata!=reserved_metadata_q)))protocol_error<=1;
    if(!writing_q)reserved_q<=0;
    if(s_last)begin writing_q<=0;wr_index_q<=0;end
    else begin writing_q<=1;wr_index_q<=writing_q?wr_index_q+1:16'd1;
     if(!writing_q)begin wr_last_index_q<=s_length-1;wr_length_q<=s_length;wr_metadata_q<=s_metadata;end
    end
   end
  end
 end
 always @(posedge rd_clk)begin
  if(rd_reset_q[1])begin reading_q<=0;rd_length_q<=0;rd_last_index_q<=0;rd_index_q<=0;rd_metadata_q<=0;end
  else if(meta_pop)begin reading_q<=1;rd_last_index_q<=fifo_meta[15:0]-1;rd_length_q<=fifo_meta[15:0];rd_metadata_q<=fifo_meta[111:16];rd_index_q<=0;end
  else if(pop)begin if(m_last)reading_q<=0;else rd_index_q<=rd_index_q+1;end
 end
 xpm_fifo_async #(.FIFO_MEMORY_TYPE("block"),.ECC_MODE("no_ecc"),.RELATED_CLOCKS(0),.SIM_ASSERT_CHK(1),
   .FIFO_WRITE_DEPTH(4096),.WRITE_DATA_WIDTH(8),.READ_DATA_WIDTH(8),.READ_MODE("fwft"),.FIFO_READ_LATENCY(0),
  .CDC_SYNC_STAGES(2),.WR_DATA_COUNT_WIDTH(13),.RD_DATA_COUNT_WIDTH(13),.USE_ADV_FEATURES("1707"))u_data(
  .rst(fifo_reset_q),.sleep(1'b0),.wr_clk(wr_clk),.wr_en(push),.din(s_data),.full(data_full),.wr_data_count(wr_count),.wr_rst_busy(dwrbusy),
  .rd_clk(rd_clk),.rd_en(pop),.dout(fifo_data),.empty(data_empty),.rd_data_count(rd_count),.rd_rst_busy(drdbusy),
  .injectsbiterr(1'b0),.injectdbiterr(1'b0),.overflow(),.underflow(),.data_valid(),.prog_full(),.almost_full(),.wr_ack(),.prog_empty(),.almost_empty(),.sbiterr(),.dbiterr());
 xpm_fifo_async #(.FIFO_MEMORY_TYPE("distributed"),.ECC_MODE("no_ecc"),.RELATED_CLOCKS(0),.SIM_ASSERT_CHK(1),
  .FIFO_WRITE_DEPTH(32),.WRITE_DATA_WIDTH(112),.READ_DATA_WIDTH(112),.READ_MODE("fwft"),.FIFO_READ_LATENCY(0),
  .CDC_SYNC_STAGES(2),.USE_ADV_FEATURES("1707"))u_metadata(
  .rst(fifo_reset_q),.sleep(1'b0),.wr_clk(wr_clk),.wr_en(meta_push),.din(meta_in),.full(meta_full),.wr_rst_busy(mwrbusy),
  .rd_clk(rd_clk),.rd_en(meta_pop),.dout(fifo_meta),.empty(meta_empty),.rd_rst_busy(mrdbusy),
  .injectsbiterr(1'b0),.injectdbiterr(1'b0),.overflow(),.underflow(),.data_valid(),.prog_full(),.almost_full(),.wr_ack(),.prog_empty(),.almost_empty(),.sbiterr(),.dbiterr(),.wr_data_count(),.rd_data_count());
endmodule
`default_nettype wire
