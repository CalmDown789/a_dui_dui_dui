//=============================================================================
// b_core_if.v —— B 侧计算核心接口壳（C-B v0.2 冻结端口的**唯一落点**）
//-----------------------------------------------------------------------------
// 依据：
//   · v3.2.2 §五.8（1）C-B 输出接口契约 v0.2
//   · v3.2.2 §五.9（1）输入侧接口契约
//   · 成员B对C架构接口与资源预算确认_v1.1 §六「C-B v0.2 数据与控制接口」
//
// 设计目的（用户指令 §十 / §二十一.17）：
//   把「C 侧与 B 侧之间的全部信号」集中在这一个壳里。
//   ★ 真实 B RTL 到位后，**只需要**：
//       (a) 把 b_core_real.v 加入工程；
//       (b) 编译时打开 `C_USE_B_REAL；
//     C 侧其余模块（c_ctrl / input_stream / output_stream / pingpong_buffer /
//     uart_tx / readback_ctrl / c_core / c_top）**不需要任何改动**。
//
// 端口方向严格按契约（注意 `in_ready` 与 `busy/done` 是 B→C，其余 in_* 是 C→B）：
//   C → B : start, in_valid, in_data, out_ready
//   B → C : busy, done, in_ready, out_valid, out_data, stripe_last, frame_last
//
// ⚠️ 冻结语句（不得改动，除非回到 §五.8 修订契约）：
//   · out_data 固定 8 bit uint8；不输出 4 相位打包总线，不输出 INT16 中间激活；
//   · stripe_last / frame_last 必须与最后一个有效数据拍**同拍**；
//   · 有效传输 = out_valid && out_ready 同拍；out_valid=1&&out_ready=0 期间
//     out_valid / out_data / stripe_last / frame_last 必须保持稳定。
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
    // 真实 B RTL 通道（成员B交付后启用）
    //   TODO(B_CONFIRM): 成员B的完整五层 RTL 尚未交付。
    //   启用前置条件（成员B对C架构接口与资源预算确认_v1.1 §十 第 5 条）：
    //     · 96×54 整数向量全层逐值对拍通过；
    //     · B-ARCH-1~12 十二项回填完成；
    //     · B-ARCH-10 的七项背压参数给出（v1.1 §八 已给合同级 N=0，见 docs/B_INTERFACE_CONTRACT.md §3.4）。
    //=========================================================================
    b_core_real u_b_core (
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
    // ★ 占位通道（默认）：SIMULATION STUB ONLY
    //   2×2 最近邻复制上采样，接口完全合规；**不是** FSRCNN。
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
