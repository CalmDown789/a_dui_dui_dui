//=============================================================================
// output_stream.v —— B→C 输出流消费 + 条带/帧边界判定 + 写侧握手
//-----------------------------------------------------------------------------
// 依据：
//   · v3.2.2 §五.8（1）(2)(4) C-B 输出接口契约 v0.2 + 冻结条件 8 条
//   · v3.2.2 §五.10 规则 1/2：`out_ready` 是**唯一**正式握手信号，且**寄存输出**
//   · v3.2.2 §五.8（5）C18 六种背压场景：判据是**逐字节输出序列一致 + 边界位置一致**
//   · 成员B对C架构接口与资源预算确认_v1.0 §七 out_valid 节拍与 sideband 保持规则
//
// 核心语义（逐条对齐 §五.8（4））：
//   条件 1  有效传输 = out_valid && out_ready 同拍  → 本模块唯一的 accept
//   条件 2  out_valid=1 && out_ready=0 时发送端不得推进 → 本模块是**接收端**，
//           只需保证自己不在 out_ready=0 时消费（accept 本身就要求 out_ready=1）
//   条件 3  out_valid=0 期间 sideband 不采样 → 所有判定都以 accept 为门
//   条件 4  边界必须与最后一个有效数据拍绑定 → 用**自己数的** x/y 复算边界再比对
//   条件 5  frame_last = 1 时必有 stripe_last = 1 → 违例记 proto_err
//   条件 6  复位后 out_valid/stripe_last/frame_last 回到无效 → 复位清空所有状态
//   条件 7  输出顺序 frame → stripe → row-major
//   条件 8  语义不可重解释 → 任何歧义回到契约修订，不在 RTL 里自行解释
//
// ★ out_ready 寄存器化说明（§五.10 规则 1/2）：
//   out_ready(t+1) = wr_ready(t)。合法性证明：
//     · wr_ready 只依赖寄存状态（bank_full / wr_cnt / rd_busy）；
//     · 状态改变只可能由「上一次 out_ready=1 的写」或「读侧完成」引起；
//     · 若上一次写没有把 bank 写满 ⇒ wr_ready 保持 1，下一拍继续合法；
//     · 若上一次写正好写满 ⇒ bank 满，wr_ready 变 0（除非另一 bank 空闲，此时
//       交换已在同一沿完成、新 bank 为空）⇒ 也不会出现「out_ready=1 而不可写」。
//   ⇒ 不存在「out_ready=1 而缓冲区实际不可写」的情形（§五.10 规则 2）。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module output_stream #(
    parameter integer OUT_W    = `C_OUT_W,      // 1920
    parameter integer OUT_H    = `C_OUT_H,      // 1080
    parameter integer STRIPE_H = `C_STRIPE_H,   // 64（**当前基线，非冻结项**）
    parameter integer DATA_W   = `C_PIXEL_W,    // 8
    // 注意：地址/计数位宽取 clog2(WIDTH*STRIPE_H + 1)，使「条带字节数」本身可表示
    //   （例：OUT_W=64/STRIPE_H=4 时条带 256 B，需 9 bit 才能表示 256；8 bit 只能到 255）
    parameter integer ADDR_W   = (OUT_W*STRIPE_H + 1 <= 1) ? 1 : $clog2(OUT_W*STRIPE_H + 1)
) (
    input  wire                clk,
    input  wire                rst_n,
    input  wire                run,          // 1 = 允许接收输出（来自 c_ctrl）
    input  wire                frame_start,  // ★ 1 拍脉冲：清帧内坐标/条带状态
    //--- B → C（C-B v0.2 冻结信号集合） --------------------------------------
    input  wire                out_valid,
    input  wire [DATA_W-1:0]   out_data,
    input  wire                out_stripe_last,
    input  wire                out_frame_last,
    output reg                 out_ready,    // ★ 寄存输出（§五.10 规则 1）
    //--- 条带缓冲写端口 -------------------------------------------------------
    output wire                wr_push,
    output wire [DATA_W-1:0]   wr_data,
    output wire [ADDR_W-1:0]   wr_stripe_len,
    input  wire                wr_ready,      // 本拍写 bank 可接收（供内部核对）
    input  wire                wr_ready_nxt,  // ★ 下一拍可接收（out_ready 寄存源）
    //--- 状态 / 边界 ----------------------------------------------------------
    output wire [15:0]         dbg_x,        // 当前等待像素的列坐标
    output wire [15:0]         dbg_y,        // 当前等待像素的行坐标
    output wire [4:0]          stripe_idx,   // 当前条带序号（0..N_STRIPES-1）
    output wire [15:0]         stripe_cnt,   // 已完成的 stripe_last 个数（应 = N_STRIPES）
    output wire                frame_last_accept, // **组合**：最终像素本拍握手成功（= cycle F）
    output reg                 frame_last_fire, // 最终像素握手后 1 拍脉冲（= B 的 done 语义）
    output reg                 proto_err     // 边界/协议不一致（黏滞，需复位）
);

    //-------------------------------------------------------------------------
    // 派生常量
    //-------------------------------------------------------------------------
    localparam integer N_STRIPES = (OUT_H + STRIPE_H - 1) / STRIPE_H;   // 1080/64 → 17
    localparam integer XW        = (OUT_W <= 1) ? 1 : $clog2(OUT_W);    // 11
    localparam integer YW        = (OUT_H <= 1) ? 1 : $clog2(OUT_H);    // 11
    localparam [15:0]  FIRST_H   = (OUT_H < STRIPE_H) ? OUT_H[15:0] : STRIPE_H[15:0];
    localparam [ADDR_W-1:0] FIRST_LEN = FIRST_H * OUT_W;   // 常量折叠，不产生硬件

    //-------------------------------------------------------------------------
    // ★ 条带几何全部用**常量**表达（第二版修正）
    //   只有「末条带」与其它条带不同，而末条带行数在**展开期**即可算出：
    //       LAST_H = OUT_H − (N_STRIPES−1) × STRIPE_H        （1080 − 16×64 = 56）
    //   于是「下一互条带」不需要任何减法 / 取小 / 乘法，只需一个常量 mux。
    //
    //   反例（第一版实测）：写成 `next_rem = OUT_H − next_base; next_h = min(...);
    //   wr_stripe_len = next_h × OUT_W` 时，Vivado 把乘法映射成 DSP48E1，
    //   并把「减法 → 取小 → 乘法 → 寄存器」串成一条 9.285 ns 的路径：
    //     WNS = −4.470 ns @200MHz，关键路径
    //       u_out/stripe_base_q[7] → CARRY4 → LUT1 → CARRY4 → LUT6×2
    //       → DSP48E1(A*(B:0x780)) → LUT2 → wr_stripe_len_q[*]/D
    //-------------------------------------------------------------------------
    localparam integer LAST_H   = OUT_H - (N_STRIPES - 1) * STRIPE_H;   // 56
    localparam [15:0]  NEXT_H_LAST = LAST_H[15:0];
    localparam [ADDR_W-1:0] FULL_LEN = STRIPE_H * OUT_W;               // 122880
    localparam [ADDR_W-1:0] LAST_LEN = LAST_H  * OUT_W;               // 107520
    localparam [4:0]   PENULT_IDX = (N_STRIPES >= 2) ? (N_STRIPES - 2) : 5'd31;
    localparam         NSTR_L = N_STRIPES;   // 供比较使用（常量）

    //-------------------------------------------------------------------------
    // 坐标 / 条带寄存器
    //-------------------------------------------------------------------------
    reg  [XW-1:0]     x_q;
    reg  [YW-1:0]     y_q;
    reg  [4:0]        stripe_idx_q;
    reg  [15:0]       stripe_base_q;    // 当前条带起始输出行
    reg  [15:0]       stripe_last_row_q;    // 当前条带末行（**寄存**，避免 add 落在比较路径上）
    reg  [15:0]       stripe_cnt_q;         // 已完成条带计数

    //-------------------------------------------------------------------------
    // 握手（★ 唯一的有效传输定义）
    //-------------------------------------------------------------------------
    wire accept = out_valid & out_ready;

    assign wr_push      = accept;
    assign wr_data      = out_data;

    //-------------------------------------------------------------------------
    // ★ 条带字节数必须**寄存**（只在帧起始 / 条带边界更新）
    //   反例（第一版实测）：写成组合 `stripe_h_q * OUT_W` 时，Vivado 会把它
    //   映射成 DSP48E1（`A*(B:0x780)`，1920 = 0x780），再串上 17 位比较器
    //   `wr_cnt_q == wr_stripe_len-1`，于是成为 **200MHz 的关键路径**：
    //     实测 WNS = −2.225 ns，关键路径 u_out/stripe_h_q_reg[6]
    //       → DSP48E1(3.367ns) → LUT6 → CARRY4 ×2 → LUT5 → wr_cnt_q[*]/CE
    //   寄存后乘法只驱动 FF，不再落在跨条带边界的关键路径上。
    //   语义不变：`wr_stripe_len` 本来就只在条带切换时改变。
    //-------------------------------------------------------------------------
    reg [ADDR_W-1:0] wr_stripe_len_q;
    assign wr_stripe_len = wr_stripe_len_q;

    //-------------------------------------------------------------------------
    // 边界复算（用自己数的 x/y，绝不直接用 B 的 sideband 判边界）
    //-------------------------------------------------------------------------
    wire exp_stripe_last = (x_q == (OUT_W - 1)) && (y_q == stripe_last_row_q);
    wire exp_frame_last  = exp_stripe_last && (stripe_idx_q == (N_STRIPES - 1));

    // 复位后坐标系尚未开跑时的防御：只有 run 期间的 accept 才判边界
    wire chk = accept & run;

    // 组合输出：最终像素本拍握手成功（c_ctrl 用它把 done 定在第 F+1 拍）
    assign frame_last_accept = chk & exp_frame_last;

    //-------------------------------------------------------------------------
    // out_ready：寄存输出
    //-------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_ready <= 1'b0;
        end else if (!run) begin
            out_ready <= 1'b0;
        end else begin
            // ★ 寄存的是「**下一拍**写 bank 是否可接收」而不是当前拍可用性：
            //   当前拍可用性在条带收尾那一拍会立刻变 0，若直接寄存当前值，
            //   会出现「out_ready=1 而写 bank 已满」的一拍，导致越界写 / 丢像素。
            out_ready <= wr_ready_nxt;
        end
    end

    //-------------------------------------------------------------------------
    // 坐标 / 条带推进（只在 accept 时推进 —— stall 时全部冻结）
    //-------------------------------------------------------------------------
    wire          last_col = (x_q == (OUT_W - 1));
    wire [XW-1:0] x_nx     = last_col ? {XW{1'b0}} : (x_q + 1'b1);
    wire [YW-1:0] y_nx     = last_col ? ((y_q == (OUT_H - 1)) ? y_q : (y_q + 1'b1)) : y_q;

    // 下一互条带几何：**全部常量 mux**（无减法 / 无取小 / 无乘法）
    wire [15:0] next_base     = stripe_base_q + STRIPE_H;
    wire        next_is_last  = (stripe_idx_q == PENULT_IDX);
    wire [15:0] next_h        = next_is_last ? NEXT_H_LAST : STRIPE_H[15:0];
    wire [15:0] next_last_row = next_base + next_h - 16'd1;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            x_q             <= {XW{1'b0}};
            y_q             <= {YW{1'b0}};
            stripe_idx_q    <= 5'd0;
            stripe_base_q   <= 16'd0;
            stripe_last_row_q <= FIRST_H - 16'd1;
            stripe_cnt_q    <= 16'd0;
            wr_stripe_len_q <= FIRST_LEN;
            frame_last_fire <= 1'b0;
            proto_err       <= 1'b0;
        end else if (frame_start) begin
            // ★ 每帧起始必须复位帧内状态（否则第 2 帧会沿用第 1 帧的
            //   坐标与条带几何 → 条带长度错、边界错、写侧与读侧失配甚至死锁）
            x_q             <= {XW{1'b0}};
            y_q             <= {YW{1'b0}};
            stripe_idx_q    <= 5'd0;
            stripe_base_q   <= 16'd0;
            stripe_last_row_q <= FIRST_H - 16'd1;
            stripe_cnt_q    <= 16'd0;
            wr_stripe_len_q <= FIRST_LEN;
            frame_last_fire <= 1'b0;
        end else begin
            frame_last_fire <= 1'b0;    // 默认 0，只在最终拍后 1 拍拉高

            if (chk) begin
                // ---- 自检：out_ready 不得在写 bank 不可接收时放行 ----
                //   （`wr_ready` 由 pingpong_buffer 组合给出，二者必须一致）
                if (!wr_ready) begin
                    proto_err <= 1'b1;
                    `ifdef C_SIM
                    if (!proto_err) begin
                        $display("[PROTO_ERR] write accepted while buffer not ready @t=%0t (x=%0d y=%0d)",
                                 $time, x_q, y_q);
                    end
                    `endif
                end

                // ---- 条件 4/5：边界必须与最后一个有效数据拍绑定 ----
                if (out_stripe_last !== exp_stripe_last) begin
                    proto_err <= 1'b1;
                    `ifdef C_SIM
                    if (!proto_err) begin
                        $display("[PROTO_ERR] stripe_last mismatch @t=%0t : got=%b exp=%b (x=%0d y=%0d stripe=%0d)",
                                 $time, out_stripe_last, exp_stripe_last, x_q, y_q, stripe_idx_q);
                    end
                    `endif
                end

                if (out_frame_last !== exp_frame_last) begin
                    proto_err <= 1'b1;
                    `ifdef C_SIM
                    if (!proto_err) begin
                        $display("[PROTO_ERR] frame_last mismatch @t=%0t : got=%b exp=%b (x=%0d y=%0d stripe=%0d)",
                                 $time, out_frame_last, exp_frame_last, x_q, y_q, stripe_idx_q);
                    end
                    `endif
                end

                // ---- 条件 5：frame_last = 1 时必须有 stripe_last = 1 ----
                if (out_frame_last && !out_stripe_last) begin
                    proto_err <= 1'b1;
                    `ifdef C_SIM
                    if (!proto_err) begin
                        $display("[PROTO_ERR] frame_last without stripe_last @t=%0t (x=%0d y=%0d)",
                                 $time, x_q, y_q);
                    end
                    `endif
                end

                // ---- 坐标推进 ----
                x_q <= x_nx;
                y_q <= y_nx;

                // ---- 条带推进（与 pingpong 的 bank 交换同沿） ----
                if (exp_stripe_last) begin
                    stripe_cnt_q <= stripe_cnt_q + 16'd1;
                    if (stripe_idx_q == (N_STRIPES - 1)) begin
                        frame_last_fire <= 1'b1;   // 最终像素握手后 1 拍（= B 的 done 语义）
                    end else begin
                        stripe_idx_q      <= stripe_idx_q + 5'd1;
                        stripe_base_q     <= next_base;
                        stripe_last_row_q <= next_last_row;
                        // 条带字节数用**常量 mux**（无乘法 ⇒ 不再推断 DSP48E1）
                        wr_stripe_len_q   <= next_is_last ? LAST_LEN : FULL_LEN;
                    end
                end
            end
        end
    end

    //-------------------------------------------------------------------------
    // 调试输出
    //-------------------------------------------------------------------------
    assign dbg_x      = {{(16-XW){1'b0}}, x_q};
    assign dbg_y      = {{(16-YW){1'b0}}, y_q};
    assign stripe_idx = stripe_idx_q;
    assign stripe_cnt = stripe_cnt_q;

endmodule

`default_nettype wire
