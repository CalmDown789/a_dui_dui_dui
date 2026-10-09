`timescale 1ns/1ps
`default_nettype none
// Input MUST be a whole packet published by packet_async_bridge. That bridge
// waits for the full packet before m_valid, so every vendor TX request can read
// one byte without gaps. Header peer/length remain latched through FCS and IFG.
module course_udp_transmit(
 input wire clk125,rst_n,
 input wire s_valid,output wire s_ready,input wire[7:0]s_data,input wire s_last,
 input wire[15:0]s_length,input wire[95:0]s_metadata,
 output wire gmii_txen,output wire[7:0]gmii_txd,
 output reg fault,output reg[31:0]packet_count
);
 localparam IDLE=0,START=1,RUN=2,GAP=3;
 reg[1:0]state_q;reg start_q;reg[15:0]length_q,index_q;reg[95:0]peer_q;reg[11:0]timer_q;
 wire req,done;
 assign s_ready=rst_n&&state_q==RUN&&req;
 always @(posedge clk125)begin
  if(!rst_n)begin state_q<=IDLE;start_q<=0;length_q<=0;index_q<=0;peer_q<=0;timer_q<=0;fault<=0;packet_count<=0;end
  else begin
   start_q<=0;
   case(state_q)
    IDLE:if(s_valid&&!fault)begin
     if(s_length<64||s_length>1088)fault<=1;
     else begin length_q<=s_length;peer_q<=s_metadata;index_q<=0;timer_q<=0;state_q<=START;end
    end
    START:begin start_q<=1;state_q<=RUN;end
    RUN:begin
     timer_q<=timer_q+1;
     if(req)begin
      if(!s_valid||s_last!=(index_q==length_q-1)||s_length!=length_q||s_metadata!=peer_q)fault<=1;
      index_q<=index_q+1;
     end
     if(done)begin
      if(index_q!=length_q)fault<=1;
      packet_count<=packet_count+1;state_q<=GAP;timer_q<=0;
     end else if(timer_q==2047)begin fault<=1;state_q<=GAP;timer_q<=0;end
    end
    // Longer than the mandated96bit interframe gap, including vendor pipeline.
    GAP:if(timer_q==31)state_q<=IDLE;else timer_q<=timer_q+1;
    default:state_q<=IDLE;
   endcase
  end
 end
 eth_udp_tx_gmii u_vendor(.clk125m(clk125),.reset_p(!rst_n),.tx_en_pulse(start_q),.tx_done(done),
  .dst_mac(peer_q[95:48]),.src_mac(48'h000a3501fec0),.dst_ip(peer_q[47:16]),.src_ip(32'hc0a80002),
  .dst_port(peer_q[15:0]),.src_port(16'd5000),.data_length(length_q),.payload_req_o(req),.payload_dat_i(s_data),
  .gmii_tx_clk(),.gmii_txen(gmii_txen),.gmii_txd(gmii_txd));
endmodule
`default_nettype wire
