//=============================================================================
// uart_tx.v —— UART 发送器（8N1，波特率参数化）
//-----------------------------------------------------------------------------
// 依据：v3.2.2 §五.7「输出读出带宽红线」
//   · 8N1：1 起始位 + 8 数据位 + 1 停止位 = **10 bit/Byte**
//   · 921600 bps → 2,073,600 Byte × 10 / 921600 ≈ **22.5 s/帧**
//   · ★ UART 属**离线静态回读**，不参与 P3/P4 实时计算路径；
//     🚫 不得用 UART 传输时间证明或推断 FPGA 实时 FPS。
//
// 设计约束（用户指令 §十一）：
//   · UART 慢速时 buffer 不得覆盖 → 由 pingpong_buffer 的 ready/valid 反压保证；
//   · buffer 满时允许 back-pressure，不得丢数据；
//   · 不生成整帧 UART dump 文件（TB 只解码、不落盘）。
//
// 发送时序（LSB first）：
//   tx_start 单拍脉冲 → tx_ready 拉低 → 起始位(BAUD_DIV 拍) → D0..D7(各 BAUD_DIV 拍)
//   → 停止位(BAUD_DIV 拍) → 回 IDLE，tx_ready 拉高
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module uart_tx #(
    parameter integer CLK_HZ   = `C_CLK_HZ,     // 200000000
    parameter integer BAUD     = `C_UART_BAUD,  // 921600
    // 允许直接覆盖分频比（小规模 TB 用；正常由 CLK_HZ/BAUD 推出）
    parameter integer BAUD_DIV = (CLK_HZ / BAUD < 1) ? 1 : (CLK_HZ / BAUD),
    parameter integer DATA_W   = 8
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              tx_start,     // 1 拍脉冲
    input  wire [DATA_W-1:0] tx_data,
    output reg               tx_ready,     // 1 = 可接收新字节（IDLE）
    output reg               tx_serial,    // 8N1，空闲为高
    output reg               tx_busy
);

    localparam integer CW = (BAUD_DIV <= 2) ? 2 : $clog2(BAUD_DIV);
    // 用 localparam 承载「分频末值」，避免对 parameter 做位选（部分工具不接受）
    localparam [CW-1:0] DIV_LAST = BAUD_DIV - 1;

    localparam [1:0] S_IDLE  = 2'd0,
                     S_START = 2'd1,
                     S_DATA  = 2'd2,
                     S_STOP  = 2'd3;

    reg [1:0]        st;
    reg [CW-1:0]     cnt;
    reg [2:0]        bitidx;
    reg [DATA_W-1:0] sh;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st        <= S_IDLE;
            cnt       <= {CW{1'b0}};
            bitidx    <= 3'd0;
            sh        <= {DATA_W{1'b0}};
            tx_serial <= 1'b1;      // 空闲高
            tx_ready  <= 1'b1;
            tx_busy   <= 1'b0;
        end else begin
            case (st)
                //-------------------------------------------------------------
                S_IDLE: begin
                    tx_serial <= 1'b1;
                    tx_ready  <= 1'b1;
                    tx_busy   <= 1'b0;
                    cnt       <= {CW{1'b0}};
                    bitidx    <= 3'd0;
                    if (tx_start) begin
                        sh        <= tx_data;
                        tx_serial <= 1'b0;                  // 起始位
                        tx_ready  <= 1'b0;
                        tx_busy   <= 1'b1;
                        cnt       <= DIV_LAST;
                        st        <= S_START;
                    end
                end
                //-------------------------------------------------------------
                S_START: begin
                    if (cnt == {CW{1'b0}}) begin
                        cnt       <= DIV_LAST;
                        tx_serial <= sh[0];                 // D0（LSB first）
                        bitidx    <= 3'd0;
                        st        <= S_DATA;
                    end else begin
                        cnt <= cnt - 1'b1;
                    end
                end
                //-------------------------------------------------------------
                S_DATA: begin
                    if (cnt == {CW{1'b0}}) begin
                        cnt <= DIV_LAST;
                        if (bitidx == (DATA_W - 1)) begin
                            tx_serial <= 1'b1;              // 停止位
                            st        <= S_STOP;
                        end else begin
                            bitidx    <= bitidx + 3'd1;
                            tx_serial <= sh[bitidx + 3'd1];
                        end
                    end else begin
                        cnt <= cnt - 1'b1;
                    end
                end
                //-------------------------------------------------------------
                S_STOP: begin
                    if (cnt == {CW{1'b0}}) begin
                        st       <= S_IDLE;
                        tx_busy  <= 1'b0;
                        tx_ready <= 1'b1;
                    end else begin
                        cnt <= cnt - 1'b1;
                    end
                end
                //-------------------------------------------------------------
                default: st <= S_IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
