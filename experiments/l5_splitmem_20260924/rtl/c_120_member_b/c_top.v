// 成员B工作：120 MHz fallback, 50 MHz input ×24/10; source copied from c-side-latest@6b87af3.
//=============================================================================
// c_top.v —— 板级顶层（ACX750-200T / xc7a200tfbg484-2）
//-----------------------------------------------------------------------------
// 依据：
//   · v3.2.2 §五.4 时钟与复位（C 侧基线，已冻结）
//       50MHz 晶振 W19 → MMCME2_BASE：24.0 / 1 / 6.0 → clk_200 = 200MHz
//       sys_rst = rst_n 按下 或 ~mmcm_locked（MMCM 锁定前全体保持复位）
//   · v3.2.2 §五.5 XDC 基线与引脚（可直接复用 bench/onboard_dual_int8/constr）
//   · v3.2.2 §8.4 ①「顶层骨架 fsrcnn_top 搭建」
//
// 本模块只做三件事：
//   1) 时钟生成（MMCM；50MHz × 24 / 10 = 120MHz）
//   2) 复位汇聚（按键 + locked 门控）
//   3) 例化 c_core 并把状态映射到 LED（板级冒烟可观测）
//
// ★ 不实现：UART RX、ILA、UDP、多时钟域（均超出本轮骨架范围）
//
// TODO(UART_PIN_CONFIRM)   : uart_tx 的 FPGA 管脚未确认（v3.2.2 §五.5 / §8.4⑥），
//   constr/c_top.xdc 中该约束已注释保留，首次串口联通时用 IO Planner 确认。
// TODO(C_DECIDE)           : 真实「start」触发源尚未冻结（UART RX 命令 / 按键 / 上位机）。
//   本骨架提供 AUTO_START_EN 参数作板级冒烟用；冻结后替换为真实触发源。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module c_top #(
    //--- 图像几何 ------------------------------------------------------------
    parameter integer IMG_W     = `C_IMG_W,
    parameter integer IMG_H     = `C_IMG_H,
    parameter integer OUT_W     = `C_OUT_W,
    parameter integer OUT_H     = `C_OUT_H,
    parameter integer STRIPE_H  = `C_STRIPE_H,     // 64（**当前基线，非冻结项**）
    parameter integer PIXEL_W   = `C_PIXEL_W,
    //--- 输入 ROM ------------------------------------------------------------
    parameter integer ROM_ADDR_W    = `C_ROM_ADDR_W,
    parameter integer ROM_DEPTH     = `C_ROM_DEPTH_POW2,
    parameter integer ROM_INIT_MODE = 0,           // 0=零填充(+readmemh) 1=公式填充(SIM ONLY)
    parameter integer ROM_INIT_EN   = 0,
    parameter         ROM_INIT_FILE = "",
    //--- 时钟 ----------------------------------------------------------------
    parameter integer USE_MMCM   = 1,              // 0 = 旁路（仿真用 sys_clk 直接当 clk_200）
    parameter integer CLK_HZ     = 120000000,      // 120 MHz fallback
    //--- UART ----------------------------------------------------------------
    parameter integer UART_BAUD  = `C_UART_BAUD,
    parameter integer RB_ENABLE  = 1,              // 1 = 允许 UART 回读
    //--- 板级冒烟：自动启动（真实触发源未冻结，见文件头 TODO） ---------------
    parameter integer AUTO_START_EN = 1,
    parameter integer AUTO_START_CYCLES = 12_000_000   // @120MHz = 100 ms
) (
    input  wire       sys_clk,      // 板载 50MHz 有源晶振 → W19
    input  wire       rst_n,        // 按键 S0 → D21，按下为低
    output wire [7:0] led,          // LED0..LED7 → U22 V22 W21 W22 Y21 Y22 N13 N17
    output wire       uart_tx       // → CH9102（管脚待确认，见文件头 TODO）
);

    //-------------------------------------------------------------------------
    // 1. 时钟生成：50MHz → 200MHz（参数化，120MHz 退路只改一个常量）
    //-------------------------------------------------------------------------
    wire clk_200;
    wire mmcm_locked;

    generate
        if (USE_MMCM != 0) begin : g_mmcm
            wire clkfb;

            MMCME2_BASE #(
                .BANDWIDTH          ("OPTIMIZED"),
                .CLKFBOUT_MULT_F    (`C_MMCM_CLKFBOUT_MULT_F),   // 24.0
                .CLKFBOUT_PHASE     (0.0),
                .CLKIN1_PERIOD      (`C_MMCM_CLKIN1_PERIOD),     // 20.0 ns = 50MHz
                .CLKOUT0_DIVIDE_F   (10.0),  // 50MHz × 24 / 10 = 120MHz
                .CLKOUT0_DUTY_CYCLE (0.5),
                .CLKOUT0_PHASE      (0.0),
                .DIVCLK_DIVIDE      (`C_MMCM_DIVCLK_DIVIDE),     // 1
                .REF_JITTER1        (0.010),
                .STARTUP_WAIT       ("FALSE")
            ) u_mmcm (
                .CLKOUT0   (clk_200),
                .CLKOUT0B  (),
                .CLKOUT1   (),
                .CLKOUT1B  (),
                .CLKOUT2   (),
                .CLKOUT2B  (),
                .CLKOUT3   (),
                .CLKOUT3B  (),
                .CLKOUT4   (),
                .CLKOUT5   (),
                .CLKOUT6   (),
                .CLKFBOUT  (clkfb),
                .CLKFBOUTB (),
                .LOCKED    (mmcm_locked),
                .CLKIN1    (sys_clk),
                .PWRDWN    (1'b0),
                .RST       (~rst_n),
                .CLKFBIN   (clkfb)
            );
        end else begin : g_bypass
            // 仿真旁路：直接把 sys_clk 当 clk_200（TB 驱动 200MHz）
            assign clk_200      = sys_clk;
            assign mmcm_locked  = 1'b1;
        end
    endgenerate

    //-------------------------------------------------------------------------
    // 2. 复位汇聚：按键复位 或 MMCM 未锁定 → 系统复位（低有效给下游）
    //    注：按键是异步输入，XDC 必须 set_false_path -from [get_ports rst_n]
    //-------------------------------------------------------------------------
    wire sys_rst_n = rst_n & mmcm_locked;

    //-------------------------------------------------------------------------
    // 3. start 触发（板级冒烟用；真实触发源见文件头 TODO(C_DECIDE)）
    //    计数到 AUTO_START_CYCLES 后 start 保持为 1：
    //      · busy=1 期间不会被重复接受（c_ctrl 硬约束）
    //      · done 后 busy=0 → 立即启动下一帧 ⇒ 板上成为「连续跑帧」冒烟台
    //        （与 bench/onboard_dual_int8 自检工程的「跑满即重来」风格一致）
    //-------------------------------------------------------------------------
    localparam [24:0] AUTO_MAX = AUTO_START_CYCLES;

    reg [24:0] auto_cnt;
    reg        start_q;

    always @(posedge clk_200 or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            auto_cnt <= 25'd0;
            start_q  <= 1'b0;
        end else begin
            start_q <= 1'b0;
            if (AUTO_START_EN != 0) begin
                if (auto_cnt != AUTO_MAX) begin
                    auto_cnt <= auto_cnt + 25'd1;
                end else begin
                    start_q <= 1'b1;
                end
            end
        end
    end

    //-------------------------------------------------------------------------
    // 4. C 侧核心
    //-------------------------------------------------------------------------
    wire        busy, done;
    wire [1:0]  buf_state;
    wire [15:0] stripe_cnt;
    wire [31:0] uart_bytes;
    wire [15:0] stripes_sent;
    wire        proto_err, overflow_err, in_done, b_busy, b_done_seen;
    wire [15:0] in_x, in_y, out_x, out_y;

    c_core #(
        .IMG_W         (IMG_W),
        .IMG_H         (IMG_H),
        .OUT_W         (OUT_W),
        .OUT_H         (OUT_H),
        .STRIPE_H      (STRIPE_H),
        .PIXEL_W       (PIXEL_W),
        .ROM_ADDR_W    (ROM_ADDR_W),
        .ROM_DEPTH     (ROM_DEPTH),
        .ROM_INIT_MODE (ROM_INIT_MODE),
        .ROM_INIT_EN   (ROM_INIT_EN),
        .ROM_INIT_FILE (ROM_INIT_FILE),
        .CLK_HZ        (CLK_HZ),
        .UART_BAUD     (UART_BAUD)
    ) u_core (
        .clk               (clk_200),
        .rst_n             (sys_rst_n),
        .start             (start_q),
        .busy              (busy),
        .done              (done),
        .rb_enable         (RB_ENABLE != 0),
        .uart_tx           (uart_tx),
        .dbg_buf_state     (buf_state),
        .dbg_stripe_cnt    (stripe_cnt),
        .dbg_uart_bytes    (uart_bytes),
        .dbg_stripes_sent  (stripes_sent),
        .dbg_proto_err     (proto_err),
        .dbg_overflow_err  (overflow_err),
        .dbg_in_done       (in_done),
        .dbg_b_busy        (b_busy),
        .dbg_b_done_seen   (b_done_seen),
        .dbg_in_x          (in_x),
        .dbg_in_y          (in_y),
        .dbg_out_x         (out_x),
        .dbg_out_y         (out_y)
    );

    //-------------------------------------------------------------------------
    // 5. done 锁存 + 心跳
    //-------------------------------------------------------------------------
    reg done_latch, err_latch;
    reg [26:0] hb_cnt;

    always @(posedge clk_200 or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            done_latch <= 1'b0;
            err_latch  <= 1'b0;
            hb_cnt     <= 27'd0;
        end else begin
            if (done) begin
                done_latch <= 1'b1;
            end
            if (proto_err | overflow_err) begin
                err_latch <= 1'b1;
            end
            hb_cnt <= hb_cnt + 27'd1;
        end
    end

    //-------------------------------------------------------------------------
    // 6. LED 映射（板级可观测）
    //    LED0 busy | LED1 done(锁存) | LED2 心跳 | LED3 协议错(锁存)
    //    LED4 溢出错(锁存) | LED5/6 buf_state | LED7 有回读活动
    //-------------------------------------------------------------------------
    assign led[0] = busy;
    assign led[1] = done_latch;
    assign led[2] = hb_cnt[26];
    assign led[3] = err_latch ? proto_err : 1'b0;
    assign led[4] = overflow_err;
    assign led[5] = buf_state[0];
    assign led[6] = buf_state[1];
    assign led[7] = (stripes_sent != 16'd0);

endmodule

`default_nettype wire
