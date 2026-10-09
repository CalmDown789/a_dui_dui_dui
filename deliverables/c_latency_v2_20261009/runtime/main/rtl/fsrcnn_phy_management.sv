`timescale 1ns/1ps
`default_nettype none
// GSR-only, uninterrupted 50 MHz management plane. S0 is deliberately absent.
// This module configures RX1/TX0 only after exact identity/readback validation.
module fsrcnn_phy_management #(
 parameter integer BOOT_CYCLES=5000000,
 parameter integer MDIO_HALF_CYCLES=250,
 parameter integer STATUS_REPLAY_CYCLES=100000000,
 parameter integer UART_BAUD_DIV=434
)(input wire clk50,output wire mdc,inout wire mdio,
 output wire uart_tx,output wire cfg_ok,cfg_failed,cfg_done);
 localparam integer CW=(BOOT_CYCLES<16)?4:$clog2(BOOT_CYCLES+1);
 reg[CW-1:0]boot_count=0;
 always @(posedge clk50)if(boot_count<BOOT_CYCLES)boot_count<=boot_count+1'b1;
 // Eight initial clock cycles initialize every management register and UART.
 // Then all resets release synchronously to this clock and remain released.
 // A registered sticky release prevents a comparator glitch on later binary
 // counter transitions from asynchronously resetting an in-flight MDIO write.
 reg cfg_rst_n=0;
 always @(posedge clk50)if(boot_count==7)cfg_rst_n<=1;
 wire boot_ready=(boot_count==BOOT_CYCLES);
 wire identity_ok,page_saved,tx_write_attempted,restore_verified;
 wire[1:0]restore_attempts;
 wire[7:0]failure_code,restore_failure_code,diag_valid,diag_state;
 wire[15:0]id2,id3,tx_old,tx_actual,rx_old,rx_actual,original_page,restored_page;
 fsrcnn_phy_startup_config #(.MDIO_HALF_CYCLES(MDIO_HALF_CYCLES))u_startup(
  .clk_50(clk50),.cfg_rst_n(cfg_rst_n),.boot_ready(boot_ready),.mdc(mdc),.mdio(mdio),
  .cfg_ok(cfg_ok),.cfg_failed(cfg_failed),.cfg_done(cfg_done),
  .identity_ok(identity_ok),.page_saved(page_saved),.tx_write_attempted(tx_write_attempted),
  .restore_verified(restore_verified),.restore_attempts(restore_attempts),
  .failure_code(failure_code),.restore_failure_code(restore_failure_code),
  .diag_valid(diag_valid),.diag_state(diag_state),.id2(id2),.id3(id3),
  .tx_old(tx_old),.tx_actual(tx_actual),.rx_old(rx_old),.rx_actual(rx_actual),
  .original_page(original_page),.restored_page(restored_page));
 wire byte_valid,byte_ready;wire[7:0]byte_data;
 fsrcnn_phy_status_once #(.REPLAY_INTERVAL_CYCLES(STATUS_REPLAY_CYCLES))u_status(
  .clk_50(clk50),.cfg_rst_n(cfg_rst_n),.cfg_done(cfg_done),.cfg_ok(cfg_ok),.cfg_failed(cfg_failed),
  .identity_ok(identity_ok),.page_saved(page_saved),.tx_write_attempted(tx_write_attempted),
  .restore_verified(restore_verified),.restore_attempts(restore_attempts),
  .failure_code(failure_code),.restore_failure_code(restore_failure_code),
  .diag_valid(diag_valid),.diag_state(diag_state),.id2(id2),.id3(id3),
  .tx_old(tx_old),.tx_actual(tx_actual),.rx_old(rx_old),.rx_actual(rx_actual),
  .original_page(original_page),.restored_page(restored_page),
  .byte_valid(byte_valid),.byte_data(byte_data),.byte_ready(byte_ready),.packet_sent(),.frame_done());
 fsrcnn_phy_uart_tx #(.CLK_HZ(50000000),.BAUD(115200),.BAUD_DIV(UART_BAUD_DIV))u_uart(
  .clk(clk50),.rst_n(cfg_rst_n),.tx_start(byte_valid&&byte_ready),
  .tx_data(byte_data),.tx_ready(byte_ready),.tx_serial(uart_tx),.tx_busy());
endmodule
`default_nettype wire
