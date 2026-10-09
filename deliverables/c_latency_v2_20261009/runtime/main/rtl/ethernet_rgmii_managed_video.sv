`timescale 1ns/1ps
`default_nettype none
// Candidate RX1/TX0 image. Physical DDR timing must pass before release.
module ethernet_rgmii_managed_video #(
 parameter integer IMG_W=960,IMG_H=540,STRIPE_H=16
)(input wire sys_clk50,reset_n,rgmii_rxc,rgmii_rxctl,input wire[3:0]rgmii_rxd,
 output wire rgmii_txc,rgmii_txctl,output wire[3:0]rgmii_txd,
 output wire phy_reset_n,output wire[7:0]led,
 output wire mdc,inout wire mdio,output wire uart_tx);
 wire cc,rc,ric,tc,fc,sc,sl,rl,rst,mc,cfg_ok,cfg_failed,cfg_done;
 ethernet_rgmii_calibrated_clocks #(.PHY_RX_DELAY_ENABLED(1),.PHY_TX_DELAY_ENABLED(0))u_clocks(
  .sys_clk50(sys_clk50),.rgmii_rxc(rgmii_rxc),.reset_n(reset_n&&cfg_ok),
  .core_clk150(cc),.rx_clk125(rc),.rx_io_clk125(ric),.tx_clk125(tc),
  .tx_forward_clk125(fc),.tx_serialize_clk250(sc),.sys_locked(sl),.rx_locked(rl),.common_reset(rst),.management_clk50(mc));
 fsrcnn_phy_management u_management(.clk50(mc),.mdc(mdc),.mdio(mdio),
  .uart_tx(uart_tx),.cfg_ok(cfg_ok),.cfg_failed(cfg_failed),.cfg_done(cfg_done));
 (* ASYNC_REG="TRUE" *)reg[1:0]rr=3,tr=3;
 always @(posedge rc or posedge rst)if(rst)rr<=3;else rr<={rr[0],1'b0};
 always @(posedge tc or posedge rst)if(rst)tr<=3;else tr<={tr[0],1'b0};
 wire[7:0]rd,td;wire dv,er,en,rx_fault,tx_fault,wire_fault,locked,busy,done,pe,oe;
 rgmii_io_calibrated_7series u_io(.rx_sample_clk(ric),.rx_reset(rr[1]),.rgmii_rxd(rgmii_rxd),.rgmii_rxctl(rgmii_rxctl),
  .gmii_rxd(rd),.gmii_rxdv(dv),.gmii_rxerr(er),.tx_serialize_clk(sc),.tx_reset(rst),
  .gmii_txd(td),.gmii_txen(en),.gmii_txerr(1'b0),.rgmii_txd(rgmii_txd),.rgmii_txctl(rgmii_txctl),.rgmii_txc(rgmii_txc));
 ethernet_gmii_video #(.IMG_W(IMG_W),.IMG_H(IMG_H),.STRIPE_H(STRIPE_H),.EXTERNAL_RX_RESET(1),.EXTERNAL_TX_RESET(1))u_video(
  .rx_clk125(rc),.core_clk150(cc),.tx_clk125(tc),.rst(rst),.rx_domain_reset(rr[1]),.tx_domain_reset(tr[1]),
  .gmii_rxdv(dv),.gmii_rxerr(er),.gmii_rxd(rd),.gmii_txen(en),.gmii_txd(td),
  .input_bytes_count(),.output_bytes_count(),.start_count(),.release_count(),.expected_frame_id(),
  .input_reject_count(),.output_reject_count(),.frame_locked(locked),.core_busy(busy),.core_done(done),
  .proto_error(pe),.overflow_error(oe),.stripe_count(),.rx_bridge_error(rx_fault),.tx_bridge_error(tx_fault),.tx_fault(wire_fault),
  .network_committed(),.network_rejected(),.network_timeouts(),.network_tx_packets());
 assign phy_reset_n=1'b1;
 assign led={cfg_failed|rx_fault|tx_fault|wire_fault|pe|oe,done,busy,locked,!rst,rl,sl,cfg_ok};
endmodule
`default_nettype wire
