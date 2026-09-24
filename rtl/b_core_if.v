//=============================================================================
// b_core_if.v —— B 侧计算核心接口壳（C-B v0.2 冻结端口的**唯一落点**）
//-----------------------------------------------------------------------------
// 依据：
//   · v3.2.2 §五.8（1）C-B 输出接口契约 v0.2
//   · v3.2.2 §五.9（1）输入侧接口契约
//   · 成员B对C架构接口与资源预算确认_v1.1 §六「C-B v0.2 数据与控制接口」
//   · **B 五层真实 RTL 交接单** `acx750_rtl/docs/member_b_c_real_core_handoff.md`
//     @ `CalmDown789/a_dui_dui_dui` 分支 `member-b-five-layer-stream` commit `ae29515`
//
// 设计目的（用户指令 §十 / §二十一.17）：
//   把「C 侧与 B 侧之间的全部信号」集中在这一个壳里。
//   C 侧其余模块（c_ctrl / input_stream / output_stream / pingpong_buffer /
//   uart_tx / readback_ctrl / c_core / c_top）**不需要任何改动**。
//
// 两条通道：
//   · `C_USE_B_REAL` 定义  → 真实五层 B RTL（正式验收路径）
//   · 未定义（默认）        → `b_core_stub` 2×2 最近邻占位
//                             **仅用于基础回归 / 隔离测试，绝不可作为 FSRCNN 验收路径**
//
// ⚠️ 冻结语句（不得改动，除非回到 §五.8 修订契约）：
//   · out_data 固定 8 bit uint8；不输出 4 相位打包总线，不输出 INT16 中间激活；
//   · stripe_last / frame_last 必须与最后一个有效数据拍**同拍**；
//   · 有效传输 = out_valid && out_ready 同拍；out_valid=1&&out_ready=0 期间
//     out_valid / out_data / stripe_last / frame_last 必须保持稳定。
//
// ── 13 端口逐项核对（方向以**C 侧**为参照；宽度见 c_config.vh） ──────────────
//   端口名        | C 侧方向 | 宽度      | 握手/语义
//   --------------|---------|-----------|------------------------------------------
//   clk_200       | in      | 1         | C 提供的唯一时钟域（200 MHz 目标）
//   rst_n         | in      | 1         | 低有效复位（B 内部同步采样）
//   start         | in      | 1         | C→B：启动一帧；**只在一帧开始有效一次**
//   busy          | out     | 1         | B→C：计算中
//   done          | out     | 1         | B→C：一帧完成脉冲
//   in_valid      | in      | 1         | C→B：输入像素有效
//   in_ready      | out     | 1         | B→C：**背压**；in_valid&&in_ready 才算传输
//   in_data       | in      | DATA_W(8) | C→B：Y 像素
//   out_valid     | out     | 1         | B→C：输出像素有效
//   out_data      | out     | DATA_W(8) | B→C：Y 像素（uint8）
//   out_ready     | in      | 1         | C→B：C 侧接收能力
//   stripe_last   | out     | 1         | B→C：本条纹最后一个有效像素（与数据同拍）
//   frame_last    | out     | 1         | B→C：本帧最后一个有效像素（与数据同拍）
//
// ⚠️ **必须显式传参**（B 交接单 §「C 正式接入时必须做的最小适配」第 1 条）：
//   `b_core_real` 的默认参数是整帧 960/540/64。若 C 侧实例不传参，**小尺寸 TB 会静默**
//   按 960×540 展开（编译期就错，且不会报错）。故此处一律显式传入 IMG_W/IMG_H/STRIPE_H。
//
// ⚠️ **参数 ROM 的装载路径**：真实核 `fsrcnn_network_mem_top.sv` 用**裸文件名**调用
//   `$readmemh`（如 `$readmemh("feature_weights_packed.mem",w1)`），因此
//   `rom/member_a_d16_s8_m1_c16/` 的 19 个 `.mem` 必须位于**仿真进程的工作目录**。
//   由 `scripts/run_sim.tcl` 负责逐 TB 复制。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module b_core_if #(
    parameter integer IMG_W    = `C_IMG_W,
    parameter integer IMG_H    = `C_IMG_H,
    parameter integer OUT_W    = `C_OUT_W,
    parameter integer OUT_H    = `C_OUT_H,
    parameter integer STRIPE_H = `C_STRIPE_H,
    parameter integer DATA_W   = `C_PIXEL_W
) (
    //--- 时钟与复位（C 提供，唯一时钟域） -------------------------------------
    input  wire              clk_200,
    input  wire              rst_n,
    //--- 控制 ----------------------------------------------------------------
    input  wire              start,
    output wire              busy,
    output wire              done,
    //--- 输入像素流（C → B） --------------------------------------------------
    input  wire              in_valid,
    output wire              in_ready,
    input  wire [DATA_W-1:0] in_data,
    //--- 输出像素流（B → C） --------------------------------------------------
    output wire              out_valid,
    output wire [DATA_W-1:0] out_data,
    input  wire              out_ready,
    output wire              stripe_last,
    output wire              frame_last
);

`ifdef C_USE_B_REAL
    //=========================================================================
    // ★ 真实五层 B RTL（正式验收路径）
    //   来源：`ae29515`，`rtl/b_real_ae29515/`（见该目录 PROVENANCE.md，逐文件 SHA-256）
    //   端口：13 个，与 C-B v0.2 同名（逐项核对见本文件头部表）
    //   参数：**必须显式传**，否则小尺寸 TB 会静默按 960×540 展开
    //=========================================================================
    b_core_real #(
        .IMG_W    (IMG_W),        // → fsrcnn_network_mem_top.IMG_W
        .IMG_H    (IMG_H),        // → fsrcnn_network_mem_top.IMG_H
        .STRIPE_H (STRIPE_H)      // → fsrcnn_network_mem_top.STRIPE_ROWS
    ) u_b_core (
        .clk_200     (clk_200),
        .rst_n       (rst_n),
        .start       (start),
        .busy        (busy),
        .done        (done),
        .in_valid    (in_valid),
        .in_ready    (in_ready),
        .in_data     (in_data),
        .out_valid   (out_valid),
        .out_data    (out_data),
        .out_ready   (out_ready),
        .stripe_last (stripe_last),
        .frame_last  (frame_last)
    );
`else
    //=========================================================================
    // 占位通道（默认）：SIMULATION STUB ONLY
    //   2×2 最近邻复制上采样，接口完全合规；**不是** FSRCNN。
    //   仅用于基础回归 / 隔离测试 —— 其输出不得用于 PSNR / 效果 / 验收结论。
    //=========================================================================
    b_core_stub #(
        .IMG_W    (IMG_W),
        .IMG_H    (IMG_H),
        .OUT_W    (OUT_W),
        .OUT_H    (OUT_H),
        .STRIPE_H (STRIPE_H),
        .DATA_W   (DATA_W)
    ) u_b_core (
        .clk         (clk_200),
        .rst_n       (rst_n),
        .start       (start),
        .busy        (busy),
        .done        (done),
        .in_valid    (in_valid),
        .in_ready    (in_ready),
        .in_data     (in_data),
        .out_valid   (out_valid),
        .out_data    (out_data),
        .out_ready   (out_ready),
        .stripe_last (stripe_last),
        .frame_last  (frame_last)
    );
`endif

endmodule

`default_nettype wire
