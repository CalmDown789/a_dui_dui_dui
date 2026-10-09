`timescale 1ns/1ps
`default_nettype none
// Vendor ch52 GMII packet engine, validated packet CDC, EVF1 and frozen SR.
// Three buffered clocks supplied externally. This is not the physical RGMII
// top. rst is common async assertion; parent gates release on clocks/PHY ready.
module ethernet_gmii_video #(
 parameter integer IMG_W=960,IMG_H=540,STRIPE_H=64,
 parameter integer EXTERNAL_RX_RESET=0,EXTERNAL_TX_RESET=0
)(
 input wire rx_clk125,core_clk150,tx_clk125,rst,rx_domain_reset,tx_domain_reset,
 input wire gmii_rxdv,gmii_rxerr,input wire[7:0]gmii_rxd,
 output wire gmii_txen,output wire[7:0]gmii_txd,
 output wire[31:0]input_bytes_count,output_bytes_count,start_count,release_count,
 output wire[31:0]expected_frame_id,input_reject_count,output_reject_count,
 output wire frame_locked,core_busy,core_done,proto_error,overflow_error,
 output wire[15:0]stripe_count,
 output wire rx_bridge_error,tx_bridge_error,tx_fault,
 output wire[31:0]network_committed,network_rejected,network_timeouts,network_tx_packets
);
 (* ASYNC_REG="TRUE" *)reg[1:0]rr,cr,tr;
 // A physical parent owns ONE RX reset synchronizer. Fan its output out
 // only inside RX, rather than synchronizing core startup independently
 // in multiple RX consumers. The bridge's reset FSM is then owned by its
 // RX write clock; its single read gate crosses to core through its 2FF.
 // Standalone GMII mode retains the original common-reset interface.
 wire rx_request=EXTERNAL_RX_RESET?rx_domain_reset:rst;
 wire tx_request=EXTERNAL_TX_RESET?tx_domain_reset:rst;
 always @(posedge rx_clk125 or posedge rx_request)if(rx_request)rr<=3;else rr<={rr[0],1'b0};
 always @(posedge core_clk150 or posedge rst)if(rst)cr<=3;else cr<={cr[0],1'b0};
 always @(posedge tx_clk125 or posedge tx_request)if(tx_request)tr<=3;else tr<={tr[0],1'b0};
 wire rv,rrdy,rl,cv,crdy,cl,ov,ordy,ol,tv,trdy,tl;
 wire[7:0]rd,cd,od,td;wire[15:0]rlen,clen,olen,tlen;wire[95:0]rmeta,cmeta,ometa,tmeta;
 course_udp_receive_commit u_receive(.clk125(rx_clk125),.rst_n(!rr[1]),.gmii_rxdv(gmii_rxdv),.gmii_rxerr(gmii_rxerr),.gmii_rxd(gmii_rxd),
  .m_valid(rv),.m_ready(rrdy),.m_data(rd),.m_last(rl),.m_length(rlen),.m_metadata(rmeta),.committed(network_committed),.rejected(network_rejected),.timeouts(network_timeouts));
 packet_async_bridge u_rx_bridge(.wr_clk(rx_clk125),.rd_clk(core_clk150),.rst(rx_request),.rd_domain_reset(1'b0),
  .s_valid(rv),.s_ready(rrdy),.s_data(rd),.s_last(rl),.s_length(rlen),.s_metadata(rmeta),
  .m_valid(cv),.m_ready(crdy),.m_data(cd),.m_last(cl),.m_length(clen),.m_metadata(cmeta),.protocol_error(rx_bridge_error));
 ethernet_sr_pipeline #(.IMG_W(IMG_W),.IMG_H(IMG_H),.STRIPE_H(STRIPE_H))u_pipeline(
  .clk(core_clk150),.rst_n(!cr[1]),.s_valid(cv),.s_ready(crdy),.s_data(cd),.s_last(cl),.s_length(clen),.s_metadata(cmeta),
  .m_valid(ov),.m_ready(ordy),.m_data(od),.m_last(ol),.m_length(olen),.m_metadata(ometa),
  .input_bytes_count(input_bytes_count),.output_bytes_count(output_bytes_count),.start_count(start_count),.release_count(release_count),
  .expected_frame_id(expected_frame_id),.input_reject_count(input_reject_count),.output_reject_count(output_reject_count),
  .frame_locked(frame_locked),.core_busy(core_busy),.core_done(core_done),.proto_error(proto_error),.overflow_error(overflow_error),.stripe_count(stripe_count));
 packet_async_bridge #(.EXTERNAL_RD_RESET(EXTERNAL_TX_RESET))u_tx_bridge(.wr_clk(core_clk150),.rd_clk(tx_clk125),.rst(rst),.rd_domain_reset(tx_request),
  .s_valid(ov),.s_ready(ordy),.s_data(od),.s_last(ol),.s_length(olen),.s_metadata(ometa),
  .m_valid(tv),.m_ready(trdy),.m_data(td),.m_last(tl),.m_length(tlen),.m_metadata(tmeta),.protocol_error(tx_bridge_error));
 course_udp_transmit u_transmit(.clk125(tx_clk125),.rst_n(!tr[1]),
  .s_valid(tv),.s_ready(trdy),.s_data(td),.s_last(tl),.s_length(tlen),.s_metadata(tmeta),
  .gmii_txen(gmii_txen),.gmii_txd(gmii_txd),.fault(tx_fault),.packet_count(network_tx_packets));
endmodule
`default_nettype wire
