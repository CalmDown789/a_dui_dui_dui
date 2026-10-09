`timescale 1ns/1ps
`default_nettype none
// 1 Gb/s ONLY. Explicit values must come from the audited current PHY readback.
// These phase candidates still require complete board min/max I/O constraints.
module ethernet_rgmii_calibrated_clocks #(
 parameter integer PHY_RX_DELAY_ENABLED=-1,PHY_TX_DELAY_ENABLED=-1
)(
 input wire sys_clk50,rgmii_rxc,reset_n,
 output wire core_clk150,rx_clk125,tx_clk125,tx_forward_clk125,
 output wire sys_locked,rx_locked,common_reset,
 output wire management_clk50,tx_serialize_clk250,
 output wire rx_io_clk125
);
 wire configuration_valid;
 if((PHY_RX_DELAY_ENABLED==0||PHY_RX_DELAY_ENABLED==1)&&
    (PHY_TX_DELAY_ENABLED==0||PHY_TX_DELAY_ENABLED==1))begin:g_valid_configuration
  assign configuration_valid=1'b1;
 end else begin:g_missing_configuration
  // Keep the unresolved configuration cell in the functional reset cone.
  // An empty unconnected cell could be trimmed by synthesis. Simulation
  // must reject this cell; a physical build must reject all black boxes.
  REQUIRE_AUDITED_PHY_DELAY_VALUES_0_OR_1 u_missing_configuration(.configuration_valid(configuration_valid));
 end
 wire serialize_raw;
 wire sys_in,rx_in,sfb,sfbb,rfb,rfbb,core_raw,tx_raw,tx90_raw,rx_raw;
 IBUF u_sys_input(.I(sys_clk50),.O(sys_in));
 IBUF u_rx_input(.I(rgmii_rxc),.O(rx_in));
 BUFG u_management_clock(.I(sys_in),.O(management_clk50));
 MMCME2_BASE #(.BANDWIDTH("OPTIMIZED"),.CLKIN1_PERIOD(20.0),.DIVCLK_DIVIDE(1),.CLKFBOUT_MULT_F(15.0),
  .CLKOUT0_DIVIDE_F(5.0),.CLKOUT1_DIVIDE(6),.CLKOUT2_DIVIDE(6),.CLKOUT2_PHASE(90.0),.CLKOUT3_DIVIDE(3),.STARTUP_WAIT("FALSE"))u_sys_mmcm(
  .CLKIN1(sys_in),.CLKFBIN(sfbb),.RST(!reset_n),.PWRDWN(1'b0),.CLKFBOUT(sfb),.CLKFBOUTB(),
  .CLKOUT0(core_raw),.CLKOUT0B(),.CLKOUT1(tx_raw),.CLKOUT1B(),.CLKOUT2(tx90_raw),.CLKOUT2B(),
  .CLKOUT3(serialize_raw),.CLKOUT3B(),.CLKOUT4(),.CLKOUT5(),.CLKOUT6(),.LOCKED(sys_locked));
 BUFG u_sys_feedback(.I(sfb),.O(sfbb));
 BUFG u_core_clock(.I(core_raw),.O(core_clk150));
 BUFG u_serialize_clock(.I(serialize_raw),.O(tx_serialize_clk250));
 BUFG u_tx_clock(.I(tx_raw),.O(tx_clk125));
 if(PHY_TX_DELAY_ENABLED==0)begin:g_tx_extra_phase
  BUFG u_tx_forward_clock(.I(tx90_raw),.O(tx_forward_clk125));
 end else begin:g_tx_phy_phase
  assign tx_forward_clk125=tx_clk125;
 end
 // Both source pins are in BANK14. Keep system MMCM and RX PLL in the
 // same CMT instead of forcing a second MMCM onto a non-dedicated input.
 PLLE2_BASE #(.BANDWIDTH("OPTIMIZED"),.CLKIN1_PERIOD(8.0),.DIVCLK_DIVIDE(1),.CLKFBOUT_MULT(8),
  .CLKOUT0_DIVIDE(8),.CLKOUT0_PHASE(PHY_RX_DELAY_ENABLED==0?90.0:0.0),.STARTUP_WAIT("FALSE"))u_rx_pll(
  .CLKIN1(rx_in),.CLKFBIN(rfbb),.RST(!reset_n),.PWRDWN(1'b0),.CLKFBOUT(rfb),
  .CLKOUT0(rx_raw),.CLKOUT1(),.CLKOUT2(),.CLKOUT3(),.CLKOUT4(),.CLKOUT5(),.LOCKED(rx_locked));
 BUFG u_rx_feedback(.I(rfb),.O(rfbb));
 BUFG u_rx_clock(.I(rx_raw),.O(rx_clk125));
 // When the PHY has already centered RXC, capture in the dedicated I/O
 // clock network. The PLL's compensated fabric clock can arrive earlier
 // than the input data at an IDDR at a slow corner; it is unsuitable as
 // the zero-phase physical capture clock for this mode. Fabric processing
 // still uses the locked PLL clock. Both clocks derive from PHY RXC and
 // every IDDR-to-fabric setup/hold path must remain timed.
 if(PHY_RX_DELAY_ENABLED==1)begin:g_rx_phy_centered_io
  BUFIO u_rx_io_clock(.I(rx_in),.O(rx_io_clk125));
 end else begin:g_rx_mac_centered_io
  assign rx_io_clk125=rx_clk125;
 end
 // Loss of either lock asserts reset immediately, even when a clock stops.
 // Release waits for synchronizers and 1024 running core cycles. The GMII
 // layer separately synchronizes release in every domain; XPM rst follows
 // its write clock. PHY hardware reset is deliberately not driven here.
 // 200 MHz is only the calibrated I/O delay reference, never SR compute.
 wire ref_feedback,ref_feedback_global,ref_raw,ref_clk,ref_locked,delay_ready;
 
 MMCME2_BASE #(.CLKIN1_PERIOD(20.0),.CLKFBOUT_MULT_F(20.0),.CLKOUT0_DIVIDE_F(5.0))u_ref_mmcm(
  .CLKIN1(management_clk50),.CLKFBIN(ref_feedback_global),.CLKFBOUT(ref_feedback),.CLKFBOUTB(),
  .CLKOUT0(ref_raw),.CLKOUT0B(),.CLKOUT1(),.CLKOUT1B(),.CLKOUT2(),.CLKOUT2B(),
  .CLKOUT3(),.CLKOUT3B(),.CLKOUT4(),.CLKOUT5(),.CLKOUT6(),
  .LOCKED(ref_locked),.RST(!reset_n),.PWRDWN(1'b0));
 BUFG u_ref_feedback(.I(ref_feedback),.O(ref_feedback_global));
 BUFG u_ref_clock(.I(ref_raw),.O(ref_clk));
 (* ASYNC_REG="TRUE" *)reg[1:0]reference_bad=3;
 always @(posedge ref_clk or negedge ref_locked)if(!ref_locked)reference_bad<=3;else reference_bad<={reference_bad[0],1'b0};
 (* ASYNC_REG="TRUE" *)reg[1:0]delay_ready_sync=0;
 always @(posedge ref_clk)delay_ready_sync<={delay_ready_sync[0],delay_ready};
 reg[5:0]delay_reset_count=0;
 reg delay_control_reset=1,calibration_was_ready=0;
 // Register the async primitive's reset: a binary counter decode can glitch
 // at 61->62 and produce a final reset pulse shorter than the required 50ns.
 // Every release here follows 64 continuous 200MHz cycles (320ns).
 always @(posedge ref_clk or posedge reference_bad[1])begin
  if(reference_bad[1])begin delay_reset_count<=0;delay_control_reset<=1;calibration_was_ready<=0;end
  else if(calibration_was_ready&&!delay_ready_sync[1])begin
   delay_reset_count<=0;delay_control_reset<=1;calibration_was_ready<=0;
  end else begin
   if(!(&delay_reset_count))delay_reset_count<=delay_reset_count+1'b1;
   else delay_control_reset<=0;
   if(delay_ready_sync[1]&&!delay_control_reset)calibration_was_ready<=1;
  end
 end
 (* IODELAY_GROUP="RGMII_RX_DELAY" *)IDELAYCTRL u_delay_control(.REFCLK(ref_clk),.RST(delay_control_reset),.RDY(delay_ready));
 wire clocks_bad=!delay_ready||delay_control_reset||!ref_locked||!configuration_valid||!reset_n||!sys_locked||!rx_locked;
 (* ASYNC_REG="TRUE" *)reg[1:0]bad_sync=2'b11;
 reg[9:0]settle_count=0;reg startup_reset=1;
 always @(posedge core_clk150 or posedge clocks_bad)
  if(clocks_bad)bad_sync<=2'b11;else bad_sync<={bad_sync[0],1'b0};
 // Counter reset is synchronous in its own domain. Only bad_sync receives
 // the raw asynchronous fault. Its second stage asynchronously presets the
 // exported startup register, even when the core clock has stopped; release
 // waits for synchronized bad_sync and all 1024 running core-clock cycles.
 always @(posedge core_clk150)begin
  if(bad_sync[1])settle_count<=0;
  else if(startup_reset&&!(&settle_count))settle_count<=settle_count+1'b1;
 end
 always @(posedge core_clk150 or posedge bad_sync[1])begin
  if(bad_sync[1])startup_reset<=1;
  else if(&settle_count)startup_reset<=0;
 end
 assign common_reset=startup_reset;
endmodule
`default_nettype wire
