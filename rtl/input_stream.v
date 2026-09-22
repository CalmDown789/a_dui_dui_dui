//=============================================================================
// input_stream.v —— 输入像素流发生器（C → B 的 in_valid/in_ready/in_data）
//-----------------------------------------------------------------------------
// 依据：
//   · v3.2.2 §五.9（1）输入像素流契约（C→B）
//   · v3.2.2 §五.9（4）ROM 读接口必须验证的七项边界条件
//   · 成员B对C架构接口与资源预算确认_v1.0 B-ARCH-3：每帧恰好 518400 个像素
//   · 用户指令 §五：in_ready=0 时 in_data / 当前地址 / x / y 必须保持
//   · 用户指令 §六：start 在 N 拍被接受，N+1 进入输入阶段
//
// ★ 地址写法声明（§五.9（4）第 7 项「必须二者择一并在实现说明中写明」）：
//   本模块采用 **写法 A（请求地址）**：
//     rom_addr 是本拍【请求】的地址，其数据在【下一拍】出现在 in_data/pixel_valid 上。
//     即 pixel_valid 相对 rom_addr 延后 1 拍。
//   形式化：rom_addr(t) 的数据 == in_data(t+1) == mem[pres_q(t+1)]
//           且 rom_addr(t) == pres_q(t) + in_fire(t) == pres_q(t+1)
//
// 时序（start 在 cycle N 被 c_ctrl 接受）：
//   N+1 : start_load=1 → 输入阶段开始；rom_en=1，rom_addr = 0（首个请求）
//   N+2 : in_valid=1，in_data = mem[0]  ← 第 1 个像素 (0,0)
//         （§五.9：start 后【不早于 1 拍】给出第 1 个像素；此处 = start 后 1 拍，合规）
//
// 背压保持（用户指令 §五，§五.8 条件 2 的输入侧对偶）：
//   in_valid=1 && in_ready=0 时，pres_q / x_q / y_q 全部不推进；
//   由于 rom_addr 是 pres_q 的纯函数（in_fire=0），rom_addr 逐拍恒定，
//   同步读 BRAM 输出寄存器随之恒定 ⇒ in_data 自动保持稳定。
//   🚫 绝不出现「back-pressure 导致跳像素」。
//
// 位宽说明：所有内部计数器均为**无符号**；比较常量均为参数表达式，无符号扩展一致。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module input_stream #(
    parameter integer IMG_W   = `C_IMG_W,       // 960
    parameter integer IMG_H   = `C_IMG_H,       // 540
    parameter integer PIXEL_W = `C_PIXEL_W,     // 8
    parameter integer ADDR_W  = `C_ROM_ADDR_W,  // 19
    parameter integer TOT_PIX = `C_IN_PIXELS    // 518400
) (
    input  wire                clk,
    input  wire                rst_n,       // 低有效（已含 MMCM locked 门控）
    //--- 控制 -----------------------------------------------------------------
    input  wire                start_load,  // 1 拍脉冲：进入输入阶段（cycle N+1）
    //--- 到 B 的输入流 --------------------------------------------------------
    output wire                in_valid,
    output wire [PIXEL_W-1:0]  in_data,
    input  wire                in_ready,    // B 侧反压；0 期间上式必须保持
    //--- 输入 ROM 读端口 ------------------------------------------------------
    output wire                rom_en,
    output wire [ADDR_W-1:0]   rom_addr,
    input  wire [PIXEL_W-1:0]  rom_dout,
    //--- 状态与调试 -----------------------------------------------------------
    output wire                input_active, // 输入阶段进行中
    output wire                input_done,   // 整帧输入像素已全部交付（黏滞，直到下次 start）
    output wire [15:0]         dbg_x,        // in_data 对应像素的列坐标（行主序 x）
    output wire [15:0]         dbg_y         // in_data 对应像素的行坐标（行主序 y）
);

    //-------------------------------------------------------------------------
    // 派生位宽
    //-------------------------------------------------------------------------
    localparam integer XW = (IMG_W <= 1) ? 1 : $clog2(IMG_W);
    localparam integer YW = (IMG_H <= 1) ? 1 : $clog2(IMG_H);

    //-------------------------------------------------------------------------
    // 状态寄存器
    //-------------------------------------------------------------------------
    reg  [ADDR_W-1:0] pres_q;      // 当前呈现在 in_data 上的像素索引（0..TOT_PIX）
    reg               run_q;       // 输入阶段使能
    reg               primed_q;    // ROM 同步读已填满 1 拍（第 1 拍 in_valid 必须为 0）
    reg               done_q;      // 输入完成（黏滞）
    reg  [XW-1:0]     x_q;         // 呈现像素的列坐标
    reg  [YW-1:0]     y_q;         // 呈现像素的行坐标

    //-------------------------------------------------------------------------
    // 握手与地址（★ 采用写法 A：rom_addr 是「请求地址」）
    //-------------------------------------------------------------------------
    wire in_fire = in_valid & in_ready;

    // 只有 run_q & primed_q 都成立才允许有效；pres_q 上界为防御性判断
    //   （pres_q 无符号，与参数 TOT_PIX 比较时按 32 位无符号扩展，语义明确）
    assign in_valid = run_q & primed_q & (pres_q < TOT_PIX);

    // 请求地址 = 呈现索引 + 本拍是否消耗（= 下一拍要呈现的像素地址）
    //   pres_q 单调 +1，行主序下 addr = y*IMG_W + x 恰好连续，无需除法/取模
    assign rom_addr = pres_q + {{(ADDR_W-1){1'b0}}, in_fire};
    assign rom_en   = run_q;

    // in_data 直接取 BRAM 同步读输出寄存器（无组合逻辑，保证保持性）
    assign in_data  = rom_dout;

    //-------------------------------------------------------------------------
    // 坐标推进（仅在手拍成功时推进；stall 时逐拍保持）
    //-------------------------------------------------------------------------
    wire          last_col = (x_q == IMG_W - 1);
    wire          last_row = (y_q == IMG_H - 1);
    wire [XW-1:0] x_nx     = last_col ? {XW{1'b0}} : (x_q + 1'b1);
    wire [YW-1:0] y_nx     = last_col ? (last_row ? y_q : (y_q + 1'b1)) : y_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            run_q    <= 1'b0;
            primed_q <= 1'b0;
            done_q   <= 1'b0;
            pres_q   <= {ADDR_W{1'b0}};
            x_q      <= {XW{1'b0}};
            y_q      <= {YW{1'b0}};
        end else if (start_load) begin
            // §六：cycle N+1 进入输入阶段，帧内计数器清零
            run_q    <= 1'b1;
            primed_q <= 1'b0;
            done_q   <= 1'b0;
            pres_q   <= {ADDR_W{1'b0}};
            x_q      <= {XW{1'b0}};
            y_q      <= {YW{1'b0}};
        end else if (run_q) begin
            primed_q <= 1'b1;   // 下一拍 ROM 输出即有效

            if (in_fire) begin
                pres_q <= pres_q + 1'b1;
                x_q    <= x_nx;
                y_q    <= y_nx;

                if (pres_q == (TOT_PIX - 1)) begin
                    // 最后一个像素已交付：收尾（★ 地址不回绕，停在填充区边界）
                    run_q  <= 1'b0;
                    done_q <= 1'b1;
                end
            end
        end
    end

    //-------------------------------------------------------------------------
    // 状态输出
    //-------------------------------------------------------------------------
    assign input_active = run_q;
    assign input_done   = done_q;
    assign dbg_x        = {{(16-XW){1'b0}}, x_q};
    assign dbg_y        = {{(16-YW){1'b0}}, y_q};

endmodule

`default_nettype wire
