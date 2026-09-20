# Day 12 initial timing target: 100 MHz (10 ns period).
# This constrains the core clock only. Board pin locations and external
# input/output delays are intentionally absent, so this is not a complete
# board-level XDC and cannot support a board-level timing claim.
create_clock -name core_clk -period 10.000 [get_ports clk]
