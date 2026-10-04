`timescale 1ns / 1ps
`default_nettype none

module tb_c_uart_param_probe;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst_n = 1'b0;
    reg uart_rx = 1'b1;
    wire uart_tx;
    wire [7:0] led;
    wire a,b,c;
    wire [31:0] d,e,f;
    wire g,h;

    c_multiframe_top #(
        .IMG_W(96), .IMG_H(54), .OUT_W(192), .OUT_H(108),
        .STRIPE_H(64), .USE_MMCM(0), .CLK_HZ(100000000), .UART_BAUD(25000000)
    ) dut (
        .sys_clk(clk), .rst_n(rst_n), .uart_rx(uart_rx), .uart_tx(uart_tx), .led(led),
        .dbg_frame_start(a), .dbg_frame_done(b), .dbg_frame_active(c),
        .dbg_expected_frame_id(d), .dbg_frame_error_count(e), .dbg_uart_bytes(f),
        .dbg_core_busy(g), .dbg_core_done(h),
        .dbg_obs_control(5'd0),
        .dbg_obs_snapshot_data(), .dbg_obs_snapshot_valid(),
        .dbg_obs_snapshot_count(), .dbg_obs_snapshot_overflow(),
        .dbg_obs_pause_effective(), .dbg_obs_pause_forced_block(), .dbg_obs_clk()
    );

    initial begin
        #1;
        $display("UART_PARAM_PROBE tb_div=%0d tx_div=%0d rx_div=%0d tx_baud=%0d",
                 100000000/25000000, dut.u_core.UART_DIV,
                 dut.u_frame_loader.BAUD_DIV, dut.u_core.u_uart.BAUD);
        $display("RESULT: PASS UART parameter probe");
        $finish;
    end
endmodule

`default_nettype wire
