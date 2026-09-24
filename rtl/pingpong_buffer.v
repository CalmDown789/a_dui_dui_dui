//=============================================================================
// pingpong_buffer.v —— 64 行条带 ping-pong 双缓冲（**当前基线，非冻结项**）
//-----------------------------------------------------------------------------
// 依据：
//   · v3.2.2 §五.3  输出存储：64 行条带双缓冲（240 KiB），末条带 56 行
//   · v3.2.2 §五.11 「64 行」= 输出侧条带缓冲单位，**不是计算 tile**
//   · v3.2.2 §五.10 `out_ready` 与 `buffer_free` 职责划分（四条硬规则）
//   · 成员B对C架构接口与资源预算确认_v1.1 §八：buffer 满后不丢弃 / 不覆盖 / 不回绕，
//     停止写入并逐级反压，out_ready 恢复后从原状态继续，**允许无限期停顿**
//
// 结构：
//   bank0 / bank1 = 两个 stripe_buffer 实例（各 WIDTH × ROWS）
//   写侧：B 输出流，每拍 1 像素；**写地址由本模块自己数**（线性 = row*WIDTH + col）
//   读侧：UART 回读，rd_req 请求 1 字节，1 拍后 rd_valid 出数据
//
// 关键设计点（都是「不丢数据」所必需）：
//   1. 「条带收尾」与「bank 交换」在**同一个时钟沿**完成 —— 不留覆盖窗口、不留空拍；
//   2. 另一 bank 未释放时，写侧**硬反压**（wr_ready=0），绝不覆盖；
//   3. 反压只冻结写指针，不改变任何已写内容；恢复后从原位置继续；
//   4. 所有边界判定基于**真实握手**（wr_push），不使用仿真时间 / cycle 计数。
//
// §五.10 硬规则对照：
//   规则 1/2：out_ready 由本模块的 wr_ready **寄存**产生（见 output_stream.v）；
//             内部 buffer_free 状态不对外作为端口（B 侧只认 out_ready）；
//   规则 3  ：本模块输出 buf_state[1:0] = IDLE / WRITING / SWAPPING / DRAINING。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module pingpong_buffer #(
    parameter integer WIDTH  = 1920,        // 每行像素数（OUT_W）
    parameter integer ROWS   = 64,          // 条带最大行数（STRIPE_H，当前基线）
    parameter integer DATA_W = 8,
    // 计数位宽取 clog2(WIDTH*ROWS + 1)：让「条带字节数」本身可表示
    //   （例：64×4 = 256 B，8 bit 只能到 255，必须 9 bit）
    parameter integer ADDR_W = (WIDTH*ROWS + 1 <= 1) ? 1 : $clog2(WIDTH*ROWS + 1)
) (
    input  wire              clk,
    input  wire              rst_n,
    //--- 写侧（来自 output_stream，基于 out_valid && out_ready 真实握手） -------
    input  wire              wr_push,       // 1 = 本拍提交一个输出像素
    input  wire [DATA_W-1:0] wr_data,
    input  wire [ADDR_W-1:0] wr_stripe_len, // 本条带总字节数 = WIDTH × stripe_h（组合量）
    output wire              wr_ready,      // 本拍写 bank 可接收（供内部越界检查）
    output wire              wr_ready_nxt,  // ★ 下一拍可接收（供 out_ready 寄存用）
    //--- 读侧（UART 回读） ----------------------------------------------------
    input  wire              rd_req,        // 1 = 请求 1 字节
    output wire              rd_avail,      // 存在待回读条带
    output wire              rd_valid,      // rd_req 后 1 拍有效
    output wire [DATA_W-1:0] rd_data,
    output wire              rd_start,      // 与 rd_valid 同拍：本条带首字节
    output wire              rd_last,       // 与 rd_valid 同拍：本条带末字节
    output wire [ADDR_W-1:0] rd_len,        // 当前回读条带总字节数
    output wire              rd_busy,
    //--- 状态与错误 -----------------------------------------------------------
    output wire [1:0]        buf_state,     // 00 IDLE / 01 WRITING / 10 SWAPPING / 11 DRAINING
    output reg               overflow_err   // 写满仍被写（协议违例，黏滞，需复位）
);

    //=========================================================================
    // 0. 状态寄存器声明（先声明后使用）
    //=========================================================================
    reg               wr_bank_q;            // 当前写 bank（0/1）
    reg  [ADDR_W-1:0] wr_cnt_q;             // 当前写 bank 已写字节数（兼作写地址）
    reg               wr_pending_full_q;    // 写 bank 已满、等待交换（此期间写侧反压）
    reg               bank_full_q [0:1];    // 该 bank 已写完一条带、待/在回读
    reg  [ADDR_W-1:0] bank_len_q  [0:1];    // 该 bank 内容长度（字节）

    reg               rd_busy_q;
    reg               rd_bank_q;
    reg  [ADDR_W-1:0] rd_ptr_q;             // 回读指针（bank 内线性地址）
    reg  [ADDR_W-1:0] rd_len_q;
    reg               rd_v_q, rd_first_q, rd_last_q;
    // ★ 回读释放握手（**单一驱动**：见下方说明）
    reg               rd_done_q;        // 1 拍脉冲：本条带回读完毕
    reg               rd_done_bank_q;   // 被释放的 bank

    //=========================================================================
    // 1. 两个条带 bank 实例
    //=========================================================================
    wire              wr_en_b0, wr_en_b1;
    wire              rd_en_b0, rd_en_b1;
    wire [DATA_W-1:0] rd_data_b0, rd_data_b1;

    assign wr_en_b0 = wr_push & (wr_bank_q == 1'b0);
    assign wr_en_b1 = wr_push & (wr_bank_q == 1'b1);
    assign rd_en_b0 = rd_req & rd_busy_q & (rd_bank_q == 1'b0);
    assign rd_en_b1 = rd_req & rd_busy_q & (rd_bank_q == 1'b1);

    stripe_buffer #(
        .WIDTH (WIDTH), .ROWS (ROWS), .DATA_W (DATA_W), .ADDR_W (ADDR_W)
    ) u_bank0 (
        .clk (clk),
        .wr_en (wr_en_b0), .wr_addr (wr_cnt_q), .wr_data (wr_data),
        .rd_en (rd_en_b0), .rd_addr (rd_ptr_q), .rd_data (rd_data_b0)
    );

    stripe_buffer #(
        .WIDTH (WIDTH), .ROWS (ROWS), .DATA_W (DATA_W), .ADDR_W (ADDR_W)
    ) u_bank1 (
        .clk (clk),
        .wr_en (wr_en_b1), .wr_addr (wr_cnt_q), .wr_data (wr_data),
        .rd_en (rd_en_b1), .rd_addr (rd_ptr_q), .rd_data (rd_data_b1)
    );

    wire [DATA_W-1:0] rd_data_mux = rd_bank_q ? rd_data_b1 : rd_data_b0;

    //=========================================================================
    // 2. 写侧判定（纯组合，基于寄存状态）
    //=========================================================================
    wire other       = ~wr_bank_q;
    wire rd_on_other = (rd_busy_q & (rd_bank_q == other));
    wire other_free  = ~bank_full_q[other] & ~rd_on_other;

    // 本拍是否为本条带最后一个像素（用**本模块自己数的** wr_cnt，不依赖 B 的 stripe_last）
    wire wr_last_beat = wr_push & (wr_cnt_q == (wr_stripe_len - 1'b1));

    // 本拍写 bank 是否可接收（不含本拍写入造成的后果）
    assign wr_ready = ~bank_full_q[wr_bank_q] & ~wr_pending_full_q;

    // 本拍是否会发生「收尾 + 立即交换」
    wire swap_on_last   = wr_last_beat & other_free;
    wire pending_on_last = wr_last_beat & ~other_free;

    // 交换条件（针对上一拍已 pending 的情况）
    wire swap_now = wr_pending_full_q & other_free;

    // ★ 下一拍是否仍可接收 —— out_ready 必须寄存「下一拍」的可用性，
    //   否则在条带收尾那一拍之后会多放行一次写，造成越界/丢像素。
    wire will_block = (bank_full_q[wr_bank_q] | pending_on_last) & ~swap_on_last & ~swap_now;
    assign wr_ready_nxt = ~will_block;

    //=========================================================================
    // 3. 写侧 / 交换 主控 —— **bank_full_q / bank_len_q / wr_* 的唯一驱动块**
    //    ⚠️ 第一版把 `bank_full_q[rd_bank_q] <= 0` 写在下方读侧的 always 块里，
    //       造成同一寄存器被两个 always 块驱动 →
    //       CRITICAL WARNING [Synth 8-6859] multi-driven net
    //       （仿真因"后写胜出"侥幸通过，综合结果不确定）。
    //       本版改为：读侧只产生 `rd_done_q` / `rd_done_bank_q` 释放脉冲，
    //       由本块统一施加，**保证每个 reg 只有一个驱动 source**。
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_bank_q         <= 1'b0;
            wr_cnt_q          <= {ADDR_W{1'b0}};
            wr_pending_full_q <= 1'b0;
            bank_full_q[0]    <= 1'b0;
            bank_full_q[1]    <= 1'b0;
            bank_len_q[0]     <= {ADDR_W{1'b0}};
            bank_len_q[1]     <= {ADDR_W{1'b0}};
            overflow_err      <= 1'b0;
        end else begin
            if (wr_push & ~wr_ready) begin
                overflow_err <= 1'b1;      // 协议违例：写侧被反压却仍在写
            end

            // ---- 回读完成 → 释放该 bank（本块唯一施加点） ----
            if (rd_done_q) begin
                bank_full_q[rd_done_bank_q] <= 1'b0;
            end

            if (wr_push) begin
                if (wr_last_beat) begin
                    // ---- 条带收尾：与交换同沿完成，不留覆盖窗口 ----
                    bank_full_q[wr_bank_q] <= 1'b1;
                    bank_len_q [wr_bank_q] <= wr_stripe_len;
                    if (other_free) begin
                        wr_bank_q         <= other;
                        wr_cnt_q          <= {ADDR_W{1'b0}};
                        wr_pending_full_q <= 1'b0;
                    end else begin
                        wr_pending_full_q <= 1'b1;   // 写侧反压，等另一 bank 释放
                    end
                end else begin
                    wr_cnt_q <= wr_cnt_q + 1'b1;
                end
            end else if (swap_now) begin
                // ---- 另一 bank 已释放：补做交换，从原状态继续（无损） ----
                wr_bank_q         <= other;
                wr_cnt_q          <= {ADDR_W{1'b0}};
                wr_pending_full_q <= 1'b0;
            end
        end
    end

    //=========================================================================
    // 4. 读侧（UART 回读）：一次只回读一个 bank
    //    ★ 本块**不直接修改 bank_full_q**，只产生释放脉冲 rd_done_q /
    //      rd_done_bank_q，由上方写侧块统一施加（避免多驱动，见其注释）。
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_busy_q      <= 1'b0;
            rd_bank_q      <= 1'b0;
            rd_ptr_q       <= {ADDR_W{1'b0}};
            rd_len_q       <= {ADDR_W{1'b0}};
            rd_v_q         <= 1'b0;
            rd_first_q     <= 1'b0;
            rd_last_q      <= 1'b0;
            rd_done_q      <= 1'b0;
            rd_done_bank_q <= 1'b0;
        end else begin
            // 脉冲类信号与 rd_data（比 rd_en 晚 1 拍）对齐
            rd_v_q     <= (rd_req & rd_busy_q);
            rd_first_q <= (rd_req & rd_busy_q & (rd_ptr_q == {ADDR_W{1'b0}}));
            rd_last_q  <= (rd_req & rd_busy_q & (rd_ptr_q == (rd_len_q - 1'b1)));
            rd_done_q  <= 1'b0;   // 单拍脉冲

            if (!rd_busy_q && !rd_done_q) begin
                // 启动一次回读：优先选「非写 bank」，保证写侧能立即换到空闲 bank
                //   `!rd_done_q` 是必需的：bank_full 由写侧块在**下一拍**才清除，
                //   若不在释放脉冲期间抑制，会立刻把刚读完的 bank 再读一遍（重复数据）。
                if (bank_full_q[0] | bank_full_q[1]) begin
                    if (bank_full_q[other]) begin
                        rd_bank_q <= other;
                        rd_len_q  <= bank_len_q[other];
                    end else begin
                        rd_bank_q <= wr_bank_q;
                        rd_len_q  <= bank_len_q[wr_bank_q];
                    end
                    rd_ptr_q  <= {ADDR_W{1'b0}};
                    rd_busy_q <= 1'b1;
                end
            end else if (rd_req) begin
                rd_ptr_q <= rd_ptr_q + 1'b1;
                if (rd_ptr_q == (rd_len_q - 1'b1)) begin
                    rd_busy_q      <= 1'b0;                 // 本条带回读完毕
                    rd_done_q      <= 1'b1;                 // ★ 释放脉冲（交给写侧块施加）
                    rd_done_bank_q <= rd_bank_q;
                end
            end
        end
    end

    //=========================================================================
    // 5. 输出
    //=========================================================================
    assign rd_valid = rd_v_q;
    assign rd_data  = rd_data_mux;
    assign rd_start = rd_first_q;
    assign rd_last  = rd_last_q;
    assign rd_len   = rd_len_q;
    assign rd_busy  = rd_busy_q;
    assign rd_avail = rd_busy_q | bank_full_q[0] | bank_full_q[1];

    // §五.10 规则 3：用状态编码取代布尔 buffer_free（只读状态，不影响数据通路）
    assign buf_state = (wr_pending_full_q & ~other_free) ? 2'b10 :   // SWAPPING（写侧被反压）
                       (rd_busy_q)                       ? 2'b11 :   // DRAINING
                       (wr_cnt_q != {ADDR_W{1'b0}})      ? 2'b01 :   // WRITING
                                                            2'b00 ;   // IDLE

endmodule

`default_nettype wire
