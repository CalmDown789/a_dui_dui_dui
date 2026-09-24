//=============================================================================
// readback_ctrl.v —— UART 静态回读控制器（骨架）
//-----------------------------------------------------------------------------
// 依据：
//   · v3.2.2 §五.7 输出读出带宽红线（UART 属**离线静态回读**，不进实时路径）
//   · v3.2.2 §五.11 用途②：UART 静态回读的**分段粒度 = 条带**
//   · 成员B对C架构接口与资源预算确认_v1.1 §八：buffer 满后不得丢数据 / 不回绕
//   · 用户指令 §十一：UART 慢速时 buffer 不得覆盖，允许 back-pressure，不得丢数据
//
// 工作方式：
//   · 只要有可回读条带（rd_avail）且处于使能状态，就按「条带」为单位回读；
//   · 每个条带读完（rd_last）后 `stripes_sent` 计数 +1；
//   · **一次只持有一个未发送字节**（have_q）：rd_req → 1 拍 → rd_valid 锁存 →
//     等 uart tx_ready → 发送 → 再取下一字节。有界流水，**不丢字节**。
//
// 反压与解耦：
//   · UART 慢 ⇒ 读侧慢 ⇒ 两个 bank 都满 ⇒ pingpong 拉低 wr_ready ⇒
//     output_stream 拉低 out_ready ⇒ B 收到标准背压。
//   · 这是**有限长度背压**（容量 = 2 个条带 bank），符合 §五.8（2）规则 2；
//     🚫 不要求 B 无限期缓存整个输出帧。
//
// 使能：`enable=0` 时完全不取字节（用于不需要回读的测试，例如全尺寸控制/边界测试）。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module readback_ctrl #(
    parameter integer DATA_W = `C_PIXEL_W
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              enable,       // 1 = 允许回读（否则完全静默）

    //--- 条带缓冲读端口（pingpong_buffer） -----------------------------------
    output reg               rd_req,       // 1 拍脉冲：请求 1 字节
    input  wire              rd_busy,
    input  wire              rd_avail,
    input  wire              rd_valid,     // rd_req 后 1 拍
    input  wire [DATA_W-1:0] rd_data,
    input  wire              rd_start,     // 与 rd_valid 同拍：条带首字节
    input  wire              rd_last,      // 与 rd_valid 同拍：条带末字节

    //--- UART 发送 ------------------------------------------------------------
    output reg               tx_start,
    output reg  [DATA_W-1:0] tx_data,
    input  wire              tx_ready,

    //--- 状态 ----------------------------------------------------------------
    output reg  [31:0]       bytes_sent,     // 已发送字节数
    output reg  [15:0]       stripes_sent,   // 已完整送出条带数
    output reg               busy            // 有字节在途
);

    reg              pend_q;     // rd_req 已发出，等 rd_valid
    reg              have_q;     // 已锁存一个字节待送 UART
    reg  [DATA_W-1:0] byte_q;
    reg              last_q;     // 锁存字节是否为条带末字节

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_req       <= 1'b0;
            tx_start     <= 1'b0;
            tx_data      <= {DATA_W{1'b0}};
            pend_q       <= 1'b0;
            have_q       <= 1'b0;
            byte_q       <= {DATA_W{1'b0}};
            last_q       <= 1'b0;
            bytes_sent   <= 32'd0;
            stripes_sent <= 16'd0;
            busy         <= 1'b0;
        end else begin
            // 默认：脉冲类信号清 0
            rd_req   <= 1'b0;
            tx_start <= 1'b0;

            //-----------------------------------------------------------------
            // 1) 收回读数据（rd_req 后 1 拍）
            //-----------------------------------------------------------------
            if (rd_valid) begin
                pend_q <= 1'b0;
                have_q <= 1'b1;
                byte_q <= rd_data;
                last_q <= rd_last;
                // rd_start 仅作调试可观测（条带首字节），不参与控制流
            end

            //-----------------------------------------------------------------
            // 2) 送 UART（只在 tx_start 的「当前拍」为 0 时才发起，避免重复）
            //-----------------------------------------------------------------
            if (have_q && tx_ready && !tx_start) begin
                tx_data      <= byte_q;
                tx_start     <= 1'b1;
                have_q       <= 1'b0;
                bytes_sent   <= bytes_sent + 32'd1;
                if (last_q) begin
                    stripes_sent <= stripes_sent + 16'd1;
                end
            end

            //-----------------------------------------------------------------
            // 3) 取下一字节：必须 rd_busy=1（否则 rd_en 不会真正发出，会死锁）
            //-----------------------------------------------------------------
            if (enable && rd_busy && !pend_q && !have_q && !tx_start) begin
                rd_req <= 1'b1;
                pend_q <= 1'b1;
            end

            busy <= have_q | pend_q;
        end
    end

endmodule

`default_nettype wire
