##############################################################################
# ACX750 multi-frame UART board profile constraints
# Target: xc7a200tfbg484-2; board I/O names match c_multiframe_synth_top.
#
# Pin evidence: C 2026-09-24 100 MHz board overlay/report for sys_clk/rst_n/LEDs/TX;
# ACX750 manual table 13 for UART_RXD=L21 and UART_TXD=M21. Reconfirm the physical
# board revision before loading a bitstream. No NSTD-1 / UCIO-1 severity downgrade.
##############################################################################

# Board 50 MHz oscillator (the MMCM output is derived from this clock).
set_property -dict {PACKAGE_PIN W19 IOSTANDARD LVCMOS33} [get_ports sys_clk]
create_clock -period 20.000 -name sys_clk [get_ports sys_clk]

# Low-active S0 pushbutton. This is an asynchronous reset input; this exception
# applies only to paths launched at the reset port, not functional data paths.
set_property -dict {PACKAGE_PIN D21 IOSTANDARD LVCMOS33} [get_ports rst_n]
set_false_path -from [get_ports rst_n]

# CH9102 UART: asynchronous RX is double-synchronized in uart_rx.v. The only
# direct data path from this port is to the first synchronizer stage; the
# rx_meta_q -> rx_sync_q path remains timed by the generated core clock.
set_property -dict {PACKAGE_PIN L21 IOSTANDARD LVCMOS33} [get_ports uart_rx]
set_false_path -from [get_ports uart_rx]
set_property -dict {PACKAGE_PIN M21 IOSTANDARD LVCMOS33} [get_ports uart_tx]

# Status LEDs, C wrapper mapping.
set_property -dict {PACKAGE_PIN U22 IOSTANDARD LVCMOS33} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN V22 IOSTANDARD LVCMOS33} [get_ports {led[1]}]
set_property -dict {PACKAGE_PIN W21 IOSTANDARD LVCMOS33} [get_ports {led[2]}]
set_property -dict {PACKAGE_PIN W22 IOSTANDARD LVCMOS33} [get_ports {led[3]}]
set_property -dict {PACKAGE_PIN Y21 IOSTANDARD LVCMOS33} [get_ports {led[4]}]
set_property -dict {PACKAGE_PIN Y22 IOSTANDARD LVCMOS33} [get_ports {led[5]}]
set_property -dict {PACKAGE_PIN N13 IOSTANDARD LVCMOS33} [get_ports {led[6]}]
set_property -dict {PACKAGE_PIN N17 IOSTANDARD LVCMOS33} [get_ports {led[7]}]

# uart_tx and LEDs have no synchronous capture clock at their board endpoints,
# so no fictitious set_output_delay is assigned. They remain visible as
# unconstrained external output endpoints in timing reports; all internal paths
# driven by the 100/150 MHz MMCM clock must still meet setup/hold requirements.

set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
