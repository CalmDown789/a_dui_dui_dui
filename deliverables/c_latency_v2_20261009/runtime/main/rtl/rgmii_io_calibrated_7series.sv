`timescale 1ns/1ps
`default_nettype none
// Calibrated BUFIO RX and a single-rising-edge 250 MHz TX data serializer.
// The TX module forwards 125 MHz via the native ODDR falling-clock arc.
// Timing constraints remain in the physical build, never in the RTL.
module rgmii_io_calibrated_7series(
 input wire rx_sample_clk,rx_reset,
 input wire[3:0]rgmii_rxd,input wire rgmii_rxctl,
 output wire[7:0]gmii_rxd,output wire gmii_rxdv,gmii_rxerr,
 input wire tx_serialize_clk,tx_reset,
 input wire[7:0]gmii_txd,input wire gmii_txen,gmii_txerr,
 output wire[3:0]rgmii_txd,output wire rgmii_txctl,rgmii_txc
);
 wire[4:0]rise_bits,fall_bits;
 wire[4:0]rx_bits={rgmii_rxctl,rgmii_rxd};
 for(genvar k=0;k<5;k=k+1)begin:g_rx
  wire delayed_bit;
  (* IODELAY_GROUP="RGMII_RX_DELAY" *) IDELAYE2 #(
   .DELAY_SRC("IDATAIN"),.HIGH_PERFORMANCE_MODE("TRUE"),.IDELAY_TYPE("FIXED"),
   .IDELAY_VALUE(k==1?11:10),.REFCLK_FREQUENCY(200.0),.SIGNAL_PATTERN("DATA"))u_delay(
   .IDATAIN(rx_bits[k]),.DATAIN(1'b0),.DATAOUT(delayed_bit),.C(1'b0),.CE(1'b0),
   .INC(1'b0),.LD(1'b0),.LDPIPEEN(1'b0),.REGRST(1'b0),.CINVCTRL(1'b0),
   .CNTVALUEIN(5'b0),.CNTVALUEOUT());
  IDDR #(.DDR_CLK_EDGE("SAME_EDGE_PIPELINED"),.INIT_Q1(1'b0),.INIT_Q2(1'b0),.SRTYPE("ASYNC"))u_iddr(
   .C(rx_sample_clk),.CE(1'b1),.D(delayed_bit),.R(rx_reset),.S(1'b0),.Q1(rise_bits[k]),.Q2(fall_bits[k]));
 end
 assign gmii_rxd={fall_bits[3:0],rise_bits[3:0]};
 assign gmii_rxdv=rise_bits[4];
 assign gmii_rxerr=rise_bits[4]^fall_bits[4];
 rgmii_tx_iob250 u_tx(.clk250(tx_serialize_clk),.reset_request(tx_reset),
  .gmii_txd(gmii_txd),.gmii_txen(gmii_txen),.gmii_txerr(gmii_txerr),
  .rgmii_txd(rgmii_txd),.rgmii_txctl(rgmii_txctl),.rgmii_txc(rgmii_txc),
  .reset250(),.phase_debug());
endmodule
`default_nettype wire
