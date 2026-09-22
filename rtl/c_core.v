//=============================================================================
// c_core.v —— C 侧集成壳（单时钟域内的全部 C 侧逻辑）
//-----------------------------------------------------------------------------
// 分工（v3.2.2 §五.4 / 成员B确认_v1.0 B-ARCH-12）：
//   C 负责：输入 ROM、64 行条带 BRAM、UART/ILA、顶层、XDC 和综合实现
//   B 负责：计算核、局部缓存、PixelShuffle 与 C-B 流接口
//
// 本模块把 C 侧模块按 C-B v0.2 契约连起来：
//
//   [host start] ─► c_ctrl ──start_b──► b_core_if ──► (真实B / stub)
//                     │  input_load
//                     ▼
//                 input_stream ──in_valid/in_data──► b_core_if.in_*
//                     │ rom_en/rom_addr
//                     ▼
//                 input_rom            b_core_if.out_valid/out_data/stripe_last/frame_last
//                                          │        ▲ out_ready
//                                          ▼        │
//                                    output_stream ─┴─► pingpong_buffer ──► uart_tx
//                                                                  ▲
//                                                        readback_ctrl
//
// ★ 不实现（明确不做，避免越界）：
//   · 不做 B 的五层网络 / DSP 映射 / PixelShuffle 相位语义（属 B）；
//   · 不做多时钟域（本项目单域，v3.2.2 §五.4）；
//   · 不做整帧缓冲（整帧 2025 KiB 装不下，预算线 1396.1 KiB，§五.2 / §五.3）。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module c_core #(
    //--- 图像几何 ------------------------------------------------------------
    parameter integer IMG_W     = `C_IMG_W,       // 960
    parameter integer IMG_H     = `C_IMG_H,       // 540
    parameter integer OUT_W     = `C_OUT_W,       // 1920
    parameter integer OUT_H     = `C_OUT_H,       // 1080
    parameter integer STRIPE_H  = `C_STRIPE_H,    // 64（**当前基线，非冻结项**）
    parameter integer PIXEL_W   = `C_PIXEL_W,     // 8
    //--- 输入 ROM ------------------------------------------------------------
    parameter integer ROM_ADDR_W  = `C_ROM_ADDR_W,       // 19
    parameter integer ROM_DEPTH   = `C_ROM_DEPTH_POW2,   // 524288
    parameter integer ROM_INIT_MODE = 0,   // 0=零填充(+readmemh) 1=公式填充(SIM ONLY)
    parameter integer ROM_INIT_EN   = 0,
    parameter         ROM_INIT_FILE = "",
    //--- 时钟 / UART ---------------------------------------------------------
    parameter integer CLK_HZ    = `C_CLK_HZ,       // 200_000_000
    parameter integer UART_BAUD = `C_UART_BAUD,    // 921600
    parameter integer UART_DIV  = (CLK_HZ / UART_BAUD < 1) ? 1 : (CLK_HZ / UART_BAUD)
) (
    input  wire        clk,          // = clk_200（唯一时钟域）
    input  wire        rst_n,        // 低有效（含 MMCM locked 门控，由 c_top 给出）

    //--- 主机控制 ------------------------------------------------------------
    input  wire        start,        // 1 拍脉冲；仅在 busy=0 时被接受
    output wire        busy,
    output wire        done,         // 1 拍脉冲，位于最终像素握手后 1 拍

    //--- UART 静态回读 -------------------------------------------------------
    input  wire        rb_enable,    // 1 = 允许 UART 回读（离线验证链路）
    output wire        uart_tx,

    //--- 调试 / 状态（只读，不影响数据通路） ---------------------------------
    output wire [1:0]  dbg_buf_state,   // 00 IDLE / 01 WRITING / 10 SWAPPING / 11 DRAINING
    output wire [15:0] dbg_stripe_cnt,  // 已完成的 stripe_last 个数（应 = N_STRIPES）
    output wire [31:0] dbg_uart_bytes,
    output wire [15:0] dbg_stripes_sent,
    output wire        dbg_proto_err,
    output wire        dbg_overflow_err,
    output wire        dbg_in_done,
    output wire        dbg_b_busy,
    output wire        dbg_b_done_seen,
    output wire [15:0] dbg_in_x,
    output wire [15:0] dbg_in_y,
    output wire [15:0] dbg_out_x,
    output wire [15:0] dbg_out_y
);

    //-------------------------------------------------------------------------
    // 派生：条带缓冲地址/计数位宽（+1 使「条带字节数」本身可表示）
    //-------------------------------------------------------------------------
    localparam integer BUF_ADDR_W = (OUT_W*STRIPE_H + 1 <= 1) ? 1 : $clog2(OUT_W*STRIPE_H + 1);

    //-------------------------------------------------------------------------
    // 内部连线
    //-------------------------------------------------------------------------
    wire          start_b, input_load, run;
    wire          frame_last_accept;
    wire          c_busy, c_done;

    wire          in_valid, in_ready;
    wire [PIXEL_W-1:0] in_data;
    wire          rom_en;
    wire [ROM_ADDR_W-1:0] rom_addr;
    wire [PIXEL_W-1:0]    rom_dout;

    wire          b_busy, b_done;
    wire          b_out_valid;
    wire [PIXEL_W-1:0] b_out_data;
    wire          b_stripe_last, b_frame_last;
    wire          out_ready;

    wire          wr_push, wr_ready, wr_ready_nxt;
    wire [PIXEL_W-1:0] wr_data;
    wire [BUF_ADDR_W-1:0] wr_stripe_len;

    wire          rd_req, rd_busy, rd_avail, rd_valid, rd_start, rd_last;
    wire [PIXEL_W-1:0] rd_data;

    wire          tx_start, tx_ready, tx_serial, tx_busy;
    wire [PIXEL_W-1:0] tx_data;

    wire          b_done_seen;

    //-------------------------------------------------------------------------
    // 1. 控制框架
    //-------------------------------------------------------------------------
    c_ctrl u_ctrl (
        .clk               (clk),
        .rst_n             (rst_n),
        .start             (start),
        .busy              (c_busy),
        .done              (c_done),
        .start_b           (start_b),
        .input_load        (input_load),
        .run               (run),
        .frame_last_accept (frame_last_accept),
        .b_busy            (b_busy),
        .b_done            (b_done),
        .b_done_seen       (b_done_seen)
    );

    assign busy = c_busy;
    assign done = c_done;

    //-------------------------------------------------------------------------
    // 2. 输入通路：ROM + 像素流发生器
    //-------------------------------------------------------------------------
    input_rom #(
        .ADDR_W    (ROM_ADDR_W),
        .DATA_W    (PIXEL_W),
        .MEM_DEPTH (ROM_DEPTH),
        .INIT_MODE (ROM_INIT_MODE),
        .INIT_EN   (ROM_INIT_EN),
        .INIT_FILE (ROM_INIT_FILE)
    ) u_rom (
        .clk  (clk),
        .en   (rom_en),
        .addr (rom_addr),
        .dout (rom_dout)
    );

    input_stream #(
        .IMG_W   (IMG_W),
        .IMG_H   (IMG_H),
        .PIXEL_W (PIXEL_W),
        .ADDR_W  (ROM_ADDR_W),
        .TOT_PIX (IMG_W * IMG_H)
    ) u_in (
        .clk          (clk),
        .rst_n        (rst_n),
        .start_load   (input_load),
        .in_valid     (in_valid),
        .in_data      (in_data),
        .in_ready     (in_ready),
        .rom_en       (rom_en),
        .rom_addr     (rom_addr),
        .rom_dout     (rom_dout),
        .input_active (),
        .input_done   (dbg_in_done),
        .dbg_x        (dbg_in_x),
        .dbg_y        (dbg_in_y)
    );

    //-------------------------------------------------------------------------
    // 3. B 计算核心接口壳（默认接 SIMULATION STUB；真实 B 到位后只换实现）
    //-------------------------------------------------------------------------
    b_core_if #(
        .IMG_W    (IMG_W),
        .IMG_H    (IMG_H),
        .OUT_W    (OUT_W),
        .OUT_H    (OUT_H),
        .STRIPE_H (STRIPE_H),
        .DATA_W   (PIXEL_W)
    ) u_b (
        .clk_200     (clk),
        .rst_n       (rst_n),
        .start       (start_b),
        .busy        (b_busy),
        .done        (b_done),
        .in_valid    (in_valid),
        .in_ready    (in_ready),
        .in_data     (in_data),
        .out_valid   (b_out_valid),
        .out_data    (b_out_data),
        .out_ready   (out_ready),
        .stripe_last (b_stripe_last),
        .frame_last  (b_frame_last)
    );

    //-------------------------------------------------------------------------
    // 4. 输出流消费 + 边界判定
    //-------------------------------------------------------------------------
    output_stream #(
        .OUT_W    (OUT_W),
        .OUT_H    (OUT_H),
        .STRIPE_H (STRIPE_H),
        .DATA_W   (PIXEL_W),
        .ADDR_W   (BUF_ADDR_W)
    ) u_out (
        .clk                (clk),
        .rst_n              (rst_n),
        .run                (run),
        .frame_start        (input_load),   // 每帧起始脉冲（与输入阶段同拍）
        .out_valid          (b_out_valid),
        .out_data           (b_out_data),
        .out_stripe_last    (b_stripe_last),
        .out_frame_last     (b_frame_last),
        .out_ready          (out_ready),
        .wr_push            (wr_push),
        .wr_data            (wr_data),
        .wr_stripe_len      (wr_stripe_len),
        .wr_ready           (wr_ready),
        .wr_ready_nxt       (wr_ready_nxt),
        .dbg_x              (dbg_out_x),
        .dbg_y              (dbg_out_y),
        .stripe_idx         (),
        .stripe_cnt         (dbg_stripe_cnt),
        .frame_last_fire    (),
        .frame_last_accept  (frame_last_accept),
        .proto_err          (dbg_proto_err)
    );

    //-------------------------------------------------------------------------
    // 5. 64 行条带 ping-pong 双缓冲（**当前基线**）
    //-------------------------------------------------------------------------
    pingpong_buffer #(
        .WIDTH  (OUT_W),
        .ROWS   (STRIPE_H),
        .DATA_W (PIXEL_W),
        .ADDR_W (BUF_ADDR_W)
    ) u_pp (
        .clk           (clk),
        .rst_n         (rst_n),
        .wr_push       (wr_push),
        .wr_data       (wr_data),
        .wr_stripe_len (wr_stripe_len),
        .wr_ready      (wr_ready),
        .wr_ready_nxt  (wr_ready_nxt),
        .rd_req        (rd_req),
        .rd_avail      (rd_avail),
        .rd_valid      (rd_valid),
        .rd_data       (rd_data),
        .rd_start      (rd_start),
        .rd_last       (rd_last),
        .rd_len        (),
        .rd_busy       (rd_busy),
        .buf_state     (dbg_buf_state),
        .overflow_err  (dbg_overflow_err)
    );

    //-------------------------------------------------------------------------
    // 6. UART 回读（离线静态回读链路；不参与实时 FPS）
    //-------------------------------------------------------------------------
    uart_tx #(
        .CLK_HZ   (CLK_HZ),
        .BAUD     (UART_BAUD),
        .BAUD_DIV (UART_DIV),
        .DATA_W   (PIXEL_W)
    ) u_uart (
        .clk       (clk),
        .rst_n     (rst_n),
        .tx_start  (tx_start),
        .tx_data   (tx_data),
        .tx_ready  (tx_ready),
        .tx_serial (tx_serial),
        .tx_busy   (tx_busy)
    );

    assign uart_tx = tx_serial;

    readback_ctrl #(
        .DATA_W (PIXEL_W)
    ) u_rb (
        .clk          (clk),
        .rst_n        (rst_n),
        .enable       (rb_enable),
        .rd_req       (rd_req),
        .rd_busy      (rd_busy),
        .rd_avail     (rd_avail),
        .rd_valid     (rd_valid),
        .rd_data      (rd_data),
        .rd_start     (rd_start),
        .rd_last      (rd_last),
        .tx_start     (tx_start),
        .tx_data      (tx_data),
        .tx_ready     (tx_ready),
        .bytes_sent   (dbg_uart_bytes),
        .stripes_sent (dbg_stripes_sent),
        .busy         ()
    );

    //-------------------------------------------------------------------------
    // 7. 其余调试输出
    //-------------------------------------------------------------------------
    assign dbg_b_busy      = b_busy;
    assign dbg_b_done_seen = b_done_seen;

endmodule

`default_nettype wire
