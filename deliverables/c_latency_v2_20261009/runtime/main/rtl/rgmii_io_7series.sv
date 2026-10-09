`timescale 1ns/1ps
`default_nettype none
// Only DDR conversion. Parent supplies buffered, phase-validated clocks and
// asynchronously asserted / synchronously released resets for each clock.
// No PHY delay assumptions, generated clock, or I/O timing exception here.
module rgmii_io_7series(
 input wire rx_sample_clk,rx_reset,
 input wire[3:0]rgmii_rxd,input wire rgmii_rxctl,
 output wire[7:0]gmii_rxd,output wire gmii_rxdv,gmii_rxerr,
 input wire tx_data_clk,tx_forward_clk,tx_reset,
 input wire[7:0]gmii_txd,input wire gmii_txen,gmii_txerr,
 output wire[3:0]rgmii_txd,output wire rgmii_txctl,rgmii_txc
);
 wire[4:0]rise_bits,fall_bits;
 wire[4:0]rx_bits={rgmii_rxctl,rgmii_rxd};
 for(genvar k=0;k<5;k=k+1)begin:g_rx
  IDDR #(.DDR_CLK_EDGE("SAME_EDGE_PIPELINED"),.INIT_Q1(1'b0),.INIT_Q2(1'b0),.SRTYPE("ASYNC"))u_iddr(
   .C(rx_sample_clk),.CE(1'b1),.D(rx_bits[k]),.R(rx_reset),.S(1'b0),.Q1(rise_bits[k]),.Q2(fall_bits[k]));
 end
 assign gmii_rxd={fall_bits[3:0],rise_bits[3:0]};
 assign gmii_rxdv=rise_bits[4];
 assign gmii_rxerr=rise_bits[4]^fall_bits[4];
 for(genvar k=0;k<4;k=k+1)begin:g_tx
  ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.INIT(1'b0),.SRTYPE("ASYNC"))u_oddr(
   .C(tx_data_clk),.CE(1'b1),.D1(gmii_txd[k]),.D2(gmii_txd[k+4]),.R(tx_reset),.S(1'b0),.Q(rgmii_txd[k]));
 end
 ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.INIT(1'b0),.SRTYPE("ASYNC"))u_ctl(
  .C(tx_data_clk),.CE(1'b1),.D1(gmii_txen),.D2(gmii_txen^gmii_txerr),.R(tx_reset),.S(1'b0),.Q(rgmii_txctl));
 ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.INIT(1'b0),.SRTYPE("ASYNC"))u_clock(
  .C(tx_forward_clk),.CE(1'b1),.D1(1'b1),.D2(1'b0),.R(tx_reset),.S(1'b0),.Q(rgmii_txc));
endmodule
`default_nettype wire
