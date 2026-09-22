//=============================================================================
// stripe_buffer.v —— 单个条带存储 bank（WIDTH × ROWS × DATA_W）
//-----------------------------------------------------------------------------
// 依据：v3.2.2 §五.3（输出存储：64 行条带双缓冲，**当前基线，非冻结项**）
//       v3.2.2 §五.11（「64 行」= 输出侧条带缓冲单位，**不是**计算 tile）
//
// 用途：本模块是 ping-pong 的**单个 bank**，不承担任何条带边界判定
//       （边界判定在 output_stream.v，bank 切换在 pingpong_buffer.v）。
//
// 端口：
//   写侧 1 个（B 输出流写入，每拍 1 像素）
//   读侧 1 个（UART 回读，每拍 1 字节）
//   两侧独立 ⇒ 可推断为简单双口 BRAM（RAMB36 的 SDP 模式）
//
// BRAM 推断要点（UG901）：
//   · 无复位（RAM 本体不复位）；
//   · 读地址 → 读数据之间**不插组合逻辑**；
//   · (* ram_style = "block" *) 显式要求 BRAM。
// ⚠️ BRAM block 计数口径：v3.2.2 §五.2 分层表 / §五.13（2）——
//    「理论 KiB 预算」与「Vivado BRAM_36K / BRAM_18K utilization」是**两级判据**，
//    本模块只保证「可被推断为 BRAM」，**具体 block 数必须由 report_utilization 实测**。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module stripe_buffer #(
    parameter integer WIDTH  = 1920,        // 每行像素数（= OUT_W）
    parameter integer ROWS   = 64,          // 条带最大行数（= STRIPE_H，当前基线）
    parameter integer DATA_W = 8,           // uint8
    parameter integer ADDR_W = (WIDTH*ROWS <= 1) ? 1 : $clog2(WIDTH*ROWS)
) (
    input  wire              clk,

    //--- 写端口（B 输出流） ---------------------------------------------------
    input  wire              wr_en,
    input  wire [ADDR_W-1:0] wr_addr,       // = (row_in_stripe)*WIDTH + col
    input  wire [DATA_W-1:0] wr_data,

    //--- 读端口（UART 回读） --------------------------------------------------
    input  wire              rd_en,
    input  wire [ADDR_W-1:0] rd_addr,
    output reg  [DATA_W-1:0] rd_data        // rd_en 后 1 拍有效
);

    localparam integer MEM_DEPTH = WIDTH * ROWS;

    (* ram_style = "block" *) reg [DATA_W-1:0] mem [0:MEM_DEPTH-1];

    integer i;
    initial begin
        for (i = 0; i < MEM_DEPTH; i = i + 1) begin
            mem[i] = {DATA_W{1'b0}};
        end
    end

    //-------------------------------------------------------------------------
    // 写端口（无复位：BRAM 写端口不需要复位；上层用 wr_en 控制）
    // 地址越界保护：上层计数位宽可能比本 bank 深度位宽多 1 位（为了让「条带字节数」
    //   本身可表示，如 256 B 需 9 bit），越界时**丢弃写**而不是回绕。
    //   正常运行时 wr_addr ∈ [0, MEM_DEPTH-1]，此保护仅作形式安全网。
    //-------------------------------------------------------------------------
    always @(posedge clk) begin
        if (wr_en && (wr_addr < MEM_DEPTH)) begin
            mem[wr_addr] <= wr_data;
        end
    end

    //-------------------------------------------------------------------------
    // 读端口（同步读，1 拍延迟）
    //-------------------------------------------------------------------------
    always @(posedge clk) begin
        if (rd_en && (rd_addr < MEM_DEPTH)) begin
            rd_data <= mem[rd_addr];
        end
    end

endmodule

`default_nettype wire
