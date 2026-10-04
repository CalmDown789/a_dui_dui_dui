//=============================================================================
// b_core_stub.v  —— ★★★ SIMULATION STUB ONLY ★★★
//-----------------------------------------------------------------------------
// ！！本模块**不是** FSRCNN，也**不得**被当成真实网络！！
//
// 用途（用户指令 §十「B 计算模块」）：
//   B 侧完整五层 RTL 尚未交付（成员B对C架构接口与资源预算确认_v1.1 §证据边界），
//   因此先提供一个**接口完全合规的占位实现**，让 C 侧骨架可编译、可仿真、
//   可验证 ready/valid、条带边界、帧边界、ping-pong、UART 回读。
//
// 实现内容（**仅**「2×2 最近邻复制」上采样，即最简单合法的 ×2 关系）：
//   输入 IMG_W×IMG_H uint8（行主序）→ 每输入像素复制成 2×2 块
//   → 输出 OUT_W×OUT_H uint8，OUT_W = 2·IMG_W，OUT_H = 2·IMG_H
//   输出顺序 = v3.2.2 §五.8（4）条件 7「frame → stripe → row-major」
//
// 明确不做的事：
//   · 不做任何卷积、不做 PixelShuffle 的相位语义、不做量化/PReLU/Q31；
//   · 不实现任何「猜测版 FSRCNN」（用户指令 §十明确禁止）；
//   · 输出像素值无算法含义（= 输入像素复制），**不得**用于 PSNR / 算法效果结论。
//
// 与 B-ARCH-10 的关系：
//   · 真实 B 的最长连续背压能力（N）尚未给出（TODO(B_CONFIRM)）；
//   · 本 stub 用「单行缓冲 + out_valid 保持到被接受」的标准 ready/valid 语义，
//     可承受**无限期**背压（只要 out_ready 最终恢复）——
//     这是**最宽松的下限模型**；真实 B 的 N 更小，届时 C 侧无需改动。
//
// ★ 真实 B RTL 到位后：只需替换本文件（或打开 b_core_if.v 的 `C_USE_B_REAL），
//   C 侧其余模块不需要重新设计。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module b_core_stub #(
    parameter integer IMG_W    = `C_IMG_W,      // 960（输入宽）
    parameter integer IMG_H    = `C_IMG_H,      // 540（输入高）
    parameter integer OUT_W    = `C_OUT_W,      // 1920（= 2*IMG_W）
    parameter integer OUT_H    = `C_OUT_H,      // 1080（= 2*IMG_H）
    parameter integer STRIPE_H = `C_STRIPE_H,   // 64（当前基线）
    parameter integer DATA_W   = `C_PIXEL_W     // 8
) (
    input  wire              clk,
    input  wire              rst_n,
    //--- 控制（C → B） --------------------------------------------------------
    input  wire              start,       // 1 拍脉冲
    output reg               busy,
    output reg               done,
    //--- 输入像素流（C → B） --------------------------------------------------
    input  wire              in_valid,
    output reg               in_ready,
    input  wire [DATA_W-1:0] in_data,
    //--- 输出像素流（B → C，C-B v0.2 冻结信号集合） ---------------------------
    output reg               out_valid,
    output wire [DATA_W-1:0] out_data,    // 组合读（保证 stall 期间稳定）
    input  wire              out_ready,
    output wire              stripe_last, // 组合，与最后一个有效数据拍绑定
    output wire              frame_last
);

    localparam integer XW  = (IMG_W <= 1) ? 1 : $clog2(IMG_W);
    localparam integer YW  = (IMG_H <= 1) ? 1 : $clog2(IMG_H);
    localparam integer OXW = (OUT_W <= 1) ? 1 : $clog2(OUT_W);

    localparam [1:0] S_IDLE = 2'd0,
                     S_FILL = 2'd1,
                     S_EMIT = 2'd2;

    //-------------------------------------------------------------------------
    // 一行输入缓存（仅 IMG_W 字节；**绝不**缓存整帧）
    //   期望映射为分布式 RAM（LUTRAM）：小、单拍组合读出、不占 BRAM。
    //   ⚠️ 第一版给 rowbuf 写了整片 initial 初值，导致
    //      WARNING [Synth 8-7137]（Set/reset 同优先级）+ [Synth 8-4767]
    //      "RAM dissolved into registers"（被拆成 960×8 个 FF）。
    //      本版**删除初值**：FILL 阶段先写满、EMIT 阶段才读，不依赖上电初值。
    //-------------------------------------------------------------------------
    (* ram_style = "distributed" *) reg [DATA_W-1:0] rowbuf [0:IMG_W-1];

    reg [1:0]     st;
    reg [XW-1:0]  fill_cnt;      // 已收输入像素数（行内）
    reg [YW-1:0]  in_row;        // 当前输入行
    reg [OXW-1:0] out_x;         // 当前输出列
    reg           half;          // 0 = 输出行 2*in_row；1 = 输出行 2*in_row+1
    reg [15:0]    stripe_base;   // 当前条带起始输出行
    reg [15:0]    stripe_h;      // 当前条带行数

    localparam [15:0] FIRST_H = (OUT_H < STRIPE_H) ? OUT_H[15:0] : STRIPE_H[15:0];

    wire [15:0] in_row16 = {{(16-YW){1'b0}}, in_row};
    wire [15:0] out_y    = {in_row16[14:0], 1'b0} + {{15{1'b0}}, half};

    wire [15:0] stripe_last_row = stripe_base + stripe_h - 16'd1;

    wire at_row_end        = (out_x == (OUT_W - 1));
    wire row_is_stripe_end = (out_y == stripe_last_row);
    wire row_is_frame_end  = (out_y == (OUT_H - 1));

    wire emit_fire = out_valid & out_ready;

    //-------------------------------------------------------------------------
    // 组合输出与 sideband
    //   · out_data 组合读出 ⇒ out_x 冻结时数据天然稳定（§五.8 条件 2）
    //   · sideband 与「有效传输拍」绑定 ⇒ stall 期间与数据一起保持（条件 2/4）
    //   · frame_last ⇒ stripe_last（条件 5）：末行必然是本条带最后一行
    //-------------------------------------------------------------------------
    assign out_data    = rowbuf[out_x >> 1];
    assign stripe_last = out_valid & at_row_end & row_is_stripe_end;
    assign frame_last  = out_valid & at_row_end & row_is_frame_end;

    //-------------------------------------------------------------------------
    // 下一互条带几何
    //-------------------------------------------------------------------------
    wire [15:0] next_base = stripe_base + STRIPE_H;
    wire [15:0] next_rem  = (OUT_H > next_base) ? (OUT_H - next_base) : 16'd0;
    wire [15:0] next_h    = (next_rem < STRIPE_H) ? next_rem : STRIPE_H;

    //-------------------------------------------------------------------------
    // 主状态机
    //-------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st          <= S_IDLE;
            busy        <= 1'b0;
            done        <= 1'b0;
            in_ready    <= 1'b0;
            out_valid   <= 1'b0;
            fill_cnt    <= {XW{1'b0}};
            in_row      <= {YW{1'b0}};
            out_x       <= {OXW{1'b0}};
            half        <= 1'b0;
            stripe_base <= 16'd0;
            stripe_h    <= FIRST_H;
        end else begin
            done <= 1'b0;

            case (st)
                //=============================================================
                S_IDLE: begin
                    busy      <= 1'b0;
                    in_ready  <= 1'b0;
                    out_valid <= 1'b0;
                    if (start) begin
                        busy        <= 1'b1;
                        in_ready    <= 1'b1;
                        fill_cnt    <= {XW{1'b0}};
                        in_row      <= {YW{1'b0}};
                        out_x       <= {OXW{1'b0}};
                        half        <= 1'b0;
                        stripe_base <= 16'd0;
                        stripe_h    <= FIRST_H;
                        st          <= S_FILL;
                    end
                end
                //=============================================================
                S_FILL: begin
                    // 收满一整行输入（IMG_W 个像素）；只按 in_valid && in_ready 计数
                    out_valid <= 1'b0;
                    if (in_valid & in_ready) begin
                        rowbuf[fill_cnt] <= in_data;
                        if (fill_cnt == (IMG_W - 1)) begin
                            in_ready  <= 1'b0;
                            out_x     <= {OXW{1'b0}};
                            half      <= 1'b0;
                            out_valid <= 1'b1;
                            st        <= S_EMIT;
                        end else begin
                            fill_cnt <= fill_cnt + 1'b1;
                        end
                    end
                end
                //=============================================================
                S_EMIT: begin
                    // ★ 关键：out_valid 只在「继续留在 EMIT」时置 1；
                    //   离开 EMIT（回 FILL 或回 IDLE）的那一拍必须显式置 0，
                    //   否则会多发出一个「伪造 beat」（数据是上一行的陈旧值）。
                    if (!emit_fire) begin
                        // out_valid 保持到被接受（§五.8 条件 3）
                        out_valid <= 1'b1;
                    end else begin
                        if (at_row_end) begin
                            out_x <= {OXW{1'b0}};

                            // ---- 条带几何推进（无论边界落在前半行还是后半行）----
                            if (row_is_stripe_end & ~row_is_frame_end) begin
                                stripe_base <= next_base;
                                stripe_h    <= next_h;
                            end

                            if (!half) begin
                                half      <= 1'b1;          // 同一输入行产出第二个输出行
                                out_valid <= 1'b1;
                            end else begin
                                half <= 1'b0;
                                if (in_row == (IMG_H - 1)) begin
                                    // ---- 整帧结束 ----
                                    busy      <= 1'b0;
                                    in_ready  <= 1'b0;
                                    out_valid <= 1'b0;
                                    done      <= 1'b1;
                                    st        <= S_IDLE;
                                end else begin
                                    in_row    <= in_row + 1'b1;
                                    fill_cnt  <= {XW{1'b0}};
                                    in_ready  <= 1'b1;
                                    out_valid <= 1'b0;          // ← 离开 EMIT：必须清 0
                                    st        <= S_FILL;
                                end
                            end
                        end else begin
                            out_x     <= out_x + 1'b1;
                            out_valid <= 1'b1;
                        end
                    end
                end
                //=============================================================
                default: st <= S_IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
