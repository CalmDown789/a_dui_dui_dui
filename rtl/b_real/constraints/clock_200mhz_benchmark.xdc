# Microbenchmark constraint only. This does not freeze the ACX750 board clock.
create_clock -name benchmark_clk -period 5.000 [get_ports clk]
