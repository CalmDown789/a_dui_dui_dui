//=============================================================================
// tb_c_top.v —— 参数一致性测试（全尺寸 960×540 → 1920×1080，STRIPE_H=64）
//              + 板级顶层 c_top 冒烟
//-----------------------------------------------------------------------------
// 依据：用户指令 §十二
//   「参数一致性测试：再使用 IMG_W=960 / IMG_H=540 / STRIPE_H=64；
//     但**只验证控制/边界**，不要求完整跑大量数据。」
//
// 本 TB 分两部分：
//
//   Part A（全尺寸控制/边界）：
//     直接例化 `output_stream` + `pingpong_buffer`（**绕过 UART**，否则
//     2,073,600 Byte × 10 bit × DIV 拍会拖到上亿拍），由 TB 当 B 侧数据源，
//     以 1 beat/cycle 驱动，并同样以 1 Byte/cycle 从条带缓冲回读核对。
//     验证：
//       A1 输出像素总数 = 2,073,600（1920×1080）
//       A2 `stripe_last` 脉冲数 = **17**（1080/64 = 16 条整 + 末条 56 行）
//       A3 末条带长度 = **107,520 Byte**（56 × 1920），即前 16 条各 122,880
//       A4 `frame_last` 脉冲数 = 1，且 `frame_last ⇒ stripe_last`（同拍）
//       A5 `proto_err` = 0（C 侧独立复算的边界与 B 侧 sideband 完全一致）
//       A6 `overflow_err` = 0（245,760 Byte 双 bank 内不会覆盖）
//       A7 回读 2,073,600 Byte **逐字节**与写入一致，且条带顺序 FIFO
//       A8 记录最长输出背压拍数（受 T2 的 1 B/cycle 回读节流）
//
//   Part B（c_top 板级冒烟）：
//     例化 `c_top`（`USE_MMCM=0` 旁路 MMCM，小规模参数），复位后确认
//     无 X 传播、`busy` 能被自动 start 拉起。**不做整帧**。
//
// 磁盘安全：**不 dump 波形**；无落盘数据；两个部分都有硬 timeout。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module tb_c_top;

    //=========================================================================
    // Part A：全尺寸 1920×1080 / STRIPE_H=64
    //=========================================================================
    localparam integer OUT_W    = 1920;
    localparam integer OUT_H    = 1080;
    localparam integer STRIPE_H = 64;
    localparam integer N_STRIPES = (OUT_H + STRIPE_H - 1) / STRIPE_H;               // 17
    localparam integer LAST_H    = OUT_H - (N_STRIPES-1)*STRIPE_H;                  // 56
    localparam integer TOT_OUT   = OUT_W * OUT_H;                                   // 2073600
    localparam integer LEN_FULL  = OUT_W * STRIPE_H;                                // 122880
    localparam integer LEN_LAST  = OUT_W * LAST_H;                                  // 107520

    localparam integer ADDR_W = (OUT_W*STRIPE_H + 1 <= 1) ? 1 : $clog2(OUT_W*STRIPE_H + 1);

    localparam integer MAX_CYC = 8000000;      // 硬 timeout（约 2.1M 拍需求 + 4 倍余量）

    reg  clk = 0, rst_n = 0, run = 0, frame_start = 0;

    //--- C 侧（被测） ---------------------------------------------------------
    wire               out_ready;
    wire               wr_push, wr_ready, wr_ready_nxt;
    wire [7:0]         wr_data;
    wire [ADDR_W-1:0]  wr_stripe_len;
    wire [15:0]        dbg_x, dbg_y, stripe_cnt;
    wire [4:0]         stripe_idx;
    wire               frame_last_accept, frame_last_fire, proto_err;

    reg                rd_req = 0;
    wire               rd_valid, rd_start, rd_last, rd_avail, rd_busy;
    wire [7:0]         rd_data;
    wire [ADDR_W-1:0]  rd_len;
    wire [1:0]         buf_state;
    wire               overflow_err;

    //--- TB 扮演的「B 侧输出源」 ---------------------------------------------
    reg  [31:0] beat = 0;          // 已握手输出的像素序号（只在 accept 时推进）
    wire [31:0] beat_x = beat % OUT_W;
    wire [31:0] beat_y = beat / OUT_W;

    wire src_sl = (beat_x == (OUT_W-1)) && (((beat_y + 1) % STRIPE_H == 0) || (beat_y == (OUT_H-1)));
    wire src_fl = (beat_x == (OUT_W-1)) && (beat_y == (OUT_H-1));

    wire src_valid = 1'b1;         // 恒定有效，由 out_ready 节流
    wire src_accept = src_valid & out_ready;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) beat <= 32'd0;
        else if (src_accept) beat <= beat + 32'd1;
    end

    output_stream #(
        .OUT_W (OUT_W), .OUT_H (OUT_H), .STRIPE_H (STRIPE_H), .DATA_W (8), .ADDR_W (ADDR_W)
    ) u_out (
        .clk (clk), .rst_n (rst_n), .run (run), .frame_start (frame_start),
        .out_valid       (src_valid),
        .out_data        (beat[7:0]),          // 数据只随 beat 变化 ⇒ stall 期间天然稳定
        .out_stripe_last (src_sl),
        .out_frame_last  (src_fl),
        .out_ready       (out_ready),
        .wr_push (wr_push), .wr_data (wr_data), .wr_stripe_len (wr_stripe_len),
        .wr_ready (wr_ready), .wr_ready_nxt (wr_ready_nxt),
        .dbg_x (dbg_x), .dbg_y (dbg_y), .stripe_idx (stripe_idx), .stripe_cnt (stripe_cnt),
        .frame_last_accept (frame_last_accept), .frame_last_fire (frame_last_fire),
        .proto_err (proto_err)
    );

    pingpong_buffer #(
        .WIDTH (OUT_W), .ROWS (STRIPE_H), .DATA_W (8), .ADDR_W (ADDR_W)
    ) u_pp (
        .clk (clk), .rst_n (rst_n),
        .wr_push (wr_push), .wr_data (wr_data), .wr_stripe_len (wr_stripe_len),
        .wr_ready (wr_ready), .wr_ready_nxt (wr_ready_nxt),
        .rd_req (rd_req), .rd_avail (rd_avail), .rd_valid (rd_valid), .rd_data (rd_data),
        .rd_start (rd_start), .rd_last (rd_last), .rd_len (rd_len), .rd_busy (rd_busy),
        .buf_state (buf_state), .overflow_err (overflow_err)
    );

    always #5 clk = ~clk;

    //--- 统计 ---------------------------------------------------------------
    integer err_cnt;
    integer out_accepts;        // Part A 已握手输出像素数
    integer sl_cnt, fl_cnt;     // stripe_last / frame_last 脉冲数（TB 独立统计）
    integer sl_cnt_prev;        // 用于量出末条带长度
    integer last_stripe_bytes;
    integer rd_bytes;
    integer stall_cur, stall_max;
    integer cyc;

    reg     partA_done;

    task fail(input [8*80-1:0] msg);
        begin
            err_cnt = err_cnt + 1;
            $display("[FAIL] %0t : %0s", $time, msg);
        end
    endtask

    initial begin
        err_cnt = 0; out_accepts = 0; sl_cnt = 0; fl_cnt = 0; sl_cnt_prev = 0;
        last_stripe_bytes = 0; rd_bytes = 0; stall_cur = 0; stall_max = 0;
        partA_done = 0;
    end

    //--- 输出侧计数 / 边界 / 稳定性检查 -------------------------------------
    reg        ov_prev;
    reg [7:0]  od_prev;
    reg        osl_prev, ofl_prev;

    always @(posedge clk) begin
        if (rst_n && run && !partA_done) begin
            // 背压期间数据与 sideband 必须保持稳定
            if (src_valid && !out_ready) begin
                if (ov_prev) begin
                    if (beat[7:0] !== od_prev)   fail("A: out_data drifted during stall");
                    if (src_sl   !== osl_prev)   fail("A: stripe_last drifted during stall");
                    if (src_fl   !== ofl_prev)   fail("A: frame_last drifted during stall");
                end
                ov_prev <= 1'b1; od_prev <= beat[7:0];
                osl_prev <= src_sl; ofl_prev <= src_fl;
                stall_cur = stall_cur + 1;
                if (stall_cur > stall_max) stall_max = stall_cur;
            end else begin
                ov_prev <= 1'b0;
                stall_cur = 0;
            end

            if (src_accept) begin
                out_accepts = out_accepts + 1;
                if (src_sl) begin
                    sl_cnt = sl_cnt + 1;
                    if (sl_cnt == (N_STRIPES-1)) sl_cnt_prev = out_accepts;   // 第 16 条结束时
                end
                if (src_fl) fl_cnt = fl_cnt + 1;
                if (src_fl && !src_sl) fail("A4: frame_last without stripe_last");
            end
        end
    end

    //--- 回读（1 Byte/cycle，逐字节核对，条带顺序 FIFO） ---------------------
    always @(posedge clk) begin
        if (rst_n && !partA_done) begin
            rd_req <= rd_busy;      // 只要 pingpong 在回读就一直取
        end else begin
            rd_req <= 1'b0;
        end
    end

    always @(posedge clk) begin
        if (rst_n && rd_valid && !partA_done) begin
            if (rd_data !== (rd_bytes & 8'hFF)) begin
                if (err_cnt < 12) $display("  rd[%0d] got=%02x exp=%02x", rd_bytes, rd_data, rd_bytes & 8'hFF);
                fail("A7: readback byte mismatch");
            end
            if ((rd_bytes == 0) && !rd_start) fail("A7: rd_start missing at first byte");
            rd_bytes = rd_bytes + 1;
        end
    end

    //=========================================================================
    // 主流程
    //=========================================================================
    initial begin
        $display("=====================================================");
        $display(" tb_c_top Part A : 960x540 -> %0dx%0d, STRIPE_H=%0d", OUT_W, OUT_H, STRIPE_H);
        $display("   N_STRIPES=%0d  LAST_H=%0d  TOT_OUT=%0d  LEN_FULL=%0d  LEN_LAST=%0d",
                 N_STRIPES, LAST_H, TOT_OUT, LEN_FULL, LEN_LAST);
        $display("=====================================================");

        rst_n = 0; run = 0; frame_start = 0;
        repeat (10) @(negedge clk);
        rst_n = 1;
        repeat (3) @(negedge clk);

        // 帧起始（等效 c_ctrl 的 input_load 脉冲）
        @(negedge clk); frame_start = 1'b1; run = 1'b1;
        @(negedge clk); frame_start = 1'b0;

        //---------------------------------------------------------------------
        // 等 frame_last 握手（或超时）
        //---------------------------------------------------------------------
        cyc = 0;
        while ((fl_cnt < 1) && (cyc < MAX_CYC)) begin
            @(negedge clk);
            cyc = cyc + 1;
        end
        if (fl_cnt < 1) begin
            fail("TIMEOUT: frame_last never accepted");
            $display("RESULT: FAIL (timeout) out_accepts=%0d rd_bytes=%0d sl=%0d",
                     out_accepts, rd_bytes, sl_cnt);
            $finish;
        end
        // 帧内最后一拍后停止推进
        repeat (5) @(negedge clk);
        run = 1'b0;

        last_stripe_bytes = out_accepts - sl_cnt_prev;

        //---------------------------------------------------------------------
        // 把剩余条带回读完
        //---------------------------------------------------------------------
        cyc = 0;
        while ((rd_bytes < TOT_OUT) && (cyc < MAX_CYC)) begin
            @(negedge clk);
            cyc = cyc + 1;
        end
        repeat (50) @(negedge clk);
        partA_done = 1;

        //---------------------------------------------------------------------
        // Part A 判定
        //---------------------------------------------------------------------
        if (out_accepts !== TOT_OUT) begin
            $display("  out_accepts = %0d (exp %0d)", out_accepts, TOT_OUT);
            fail("A1: output pixel count mismatch");
        end
        if (sl_cnt !== N_STRIPES) begin
            $display("  stripe_last count = %0d (exp %0d)", sl_cnt, N_STRIPES);
            fail("A2: stripe_last pulse count mismatch");
        end
        if (last_stripe_bytes !== LEN_LAST) begin
            $display("  last stripe bytes = %0d (exp %0d)", last_stripe_bytes, LEN_LAST);
            fail("A3: last stripe length mismatch (expect 56 rows)");
        end
        if (fl_cnt !== 1) begin
            $display("  frame_last count = %0d (exp 1)", fl_cnt);
            fail("A4: frame_last pulse count mismatch");
        end
        if (proto_err !== 1'b0)  fail("A5: proto_err asserted (C 侧复算边界与 B 侧不一致)");
        if (overflow_err !== 1'b0) fail("A6: overflow_err asserted");
        if (rd_bytes !== TOT_OUT) begin
            $display("  rd_bytes = %0d (exp %0d)", rd_bytes, TOT_OUT);
            fail("A7: readback byte count mismatch");
        end

        $display("-----------------------------------------------------");
        $display(" out_accepts=%0d / %0d", out_accepts, TOT_OUT);
        $display(" stripe_last=%0d / %0d ; frame_last=%0d / 1", sl_cnt, N_STRIPES, fl_cnt);
        $display(" last stripe bytes=%0d (exp %0d = %0d rows x %0d)", last_stripe_bytes, LEN_LAST, LAST_H, OUT_W);
        $display(" rd_bytes=%0d / %0d ; longest out-stall=%0d cyc", rd_bytes, TOT_OUT, stall_max);
        $display(" proto_err=%b overflow_err=%b", proto_err, overflow_err);
        $display("-----------------------------------------------------");
        if (err_cnt == 0) $display("Part A: PASS");
        else              $display("Part A: FAIL (err_cnt=%0d)", err_cnt);

        // 统一汇总行（供 scripts/run_sim.tcl 判定）
        //   注：Part B 并发运行，早在 Part A 结束前就已完成，
        //   因此此处 err_cnt 已包含 Part A/B 两侧的全部错误。
        if (err_cnt == 0) $display("RESULT: PASS  (Part A 全尺寸边界 + Part B c_top 冒烟, 0 error)");
        else              $display("RESULT: FAIL  (err_cnt=%0d)", err_cnt);
        $finish;
    end

    //=========================================================================
    // Part B：c_top 板级冒烟（USE_MMCM=0 旁路；小规模）
    //   仅验证：可例化/可仿真、复位后无 X、busy 能被自动 start 拉起。
    //   **不跑整帧**，不产生任何结论性数据。
    //=========================================================================
    localparam integer B_IMG_W = 32, B_IMG_H = 16, B_STRIPE = 5;

    reg  b_clk = 0, b_rst_n = 0;
    wire [7:0] b_led;
    wire b_uart_tx;

    c_top #(
        .IMG_W (B_IMG_W), .IMG_H (B_IMG_H),
        .OUT_W (2*B_IMG_W), .OUT_H (2*B_IMG_H),
        .STRIPE_H (B_STRIPE),
        .ROM_ADDR_W (10), .ROM_DEPTH (1024),
        .ROM_INIT_MODE (1), .ROM_INIT_EN (0), .ROM_INIT_FILE (""),
        .USE_MMCM (0),
        .CLK_HZ (1000), .UART_BAUD (100), .RB_ENABLE (1),
        .AUTO_START_EN (1), .AUTO_START_CYCLES (50)
    ) u_top (
        .sys_clk (b_clk), .rst_n (b_rst_n), .led (b_led), .uart_tx (b_uart_tx)
    );

    always #5 b_clk = ~b_clk;

    integer b_cyc;
    initial begin
        b_rst_n = 1'b0;
        repeat (20) @(negedge b_clk);
        b_rst_n = 1'b1;

        // 复位后：led / uart_tx 不应为 X
        repeat (5) @(negedge b_clk);
        if (^b_led === 1'bx) begin
            err_cnt = err_cnt + 1;
            $display("[FAIL] Part B: led contains X after reset");
        end
        if (b_uart_tx !== 1'b1) begin
            err_cnt = err_cnt + 1;
            $display("[FAIL] Part B: uart_tx not idle-high after reset (got %b)", b_uart_tx);
        end

        // 等自动 start 生效 → busy 拉起（led[0] = busy）
        b_cyc = 0;
        while ((b_led[0] !== 1'b1) && (b_cyc < 500)) begin
            @(negedge b_clk);
            b_cyc = b_cyc + 1;
        end
        if (b_cyc >= 500) begin
            err_cnt = err_cnt + 1;
            $display("[FAIL] Part B: busy (led[0]) not asserted within 500 cycles");
        end else begin
            $display("Part B: c_top 冒烟 OK — busy 于 %0d 拍后拉起, led=%b", b_cyc, b_led);
        end

        // a couple more cycles to let the frame begin without X propagation
        repeat (100) @(negedge b_clk);
        if (^u_top.led === 1'bx) begin
            err_cnt = err_cnt + 1;
            $display("[FAIL] Part B: led became X after frame start");
        end else begin
            $display("Part B: PASS (无 X 传播；未跑整帧，无结论性指标)");
        end
    end

    //=========================================================================
    // 全局硬 timeout
    //=========================================================================
    initial begin
        #(MAX_CYC * 10 * 2);
        $display("RESULT: FAIL (global hard timeout)");
        $finish;
    end

endmodule

`default_nettype wire
