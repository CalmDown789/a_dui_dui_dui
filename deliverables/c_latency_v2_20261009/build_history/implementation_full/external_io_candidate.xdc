# Conditional board envelope RX[-.30,+.45] TX[-.34,+.40] ns.
# RX PHY output setup/hold >=1.2ns, BUFIO follows actual duty.
# TX0 required clock-data window at PHY pins [1.0,2.6]ns.
create_generated_clock -name rgmii_tx_forward -source [get_pins u_io/u_tx/u_forward/C] -edges {2 4 6} [get_ports rgmii_txc]
set_input_delay -clock phy_rx125 -max 2.490000 [get_ports {rgmii_rxd[*] rgmii_rxctl}]
set_input_delay -clock phy_rx125 -min 0.900000 -add_delay [get_ports {rgmii_rxd[*] rgmii_rxctl}]
set_input_delay -clock phy_rx125 -max 3.210000 -clock_fall -add_delay [get_ports {rgmii_rxd[*] rgmii_rxctl}]
set_input_delay -clock phy_rx125 -min 0.900000 -clock_fall -add_delay [get_ports {rgmii_rxd[*] rgmii_rxctl}]
set_output_delay -clock rgmii_tx_forward -max 1.400000 [get_ports {rgmii_txd[*] rgmii_txctl}]
set_output_delay -clock rgmii_tx_forward -min -1.740000 -add_delay [get_ports {rgmii_txd[*] rgmii_txctl}]
set_output_delay -clock rgmii_tx_forward -max 1.400000 -clock_fall -add_delay [get_ports {rgmii_txd[*] rgmii_txctl}]
set_output_delay -clock rgmii_tx_forward -min -1.740000 -clock_fall -add_delay [get_ports {rgmii_txd[*] rgmii_txctl}]
set_load 12.0 [get_ports {rgmii_txd[*] rgmii_txctl rgmii_txc}]
set_property SLEW FAST [get_ports {rgmii_txd[*] rgmii_txctl rgmii_txc}]
set_property DRIVE 8 [get_ports {rgmii_txd[*] rgmii_txctl}]
set_property DRIVE 12 [get_ports rgmii_txc]
