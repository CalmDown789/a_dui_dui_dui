//=============================================================================
// tb_stripe_buffer.v —— 条带缓冲模块级定向测试（ping-pong + 反压 + 不覆盖）
//-----------------------------------------------------------------------------
// 目的：在**不依赖 B、不依赖 UART、不依赖 c_core** 的前提下，把
//       `pingpong_buffer.v` + `stripe_buffer.v` 的边界行为钉死。
//
// 被测契约（任务书 v3.2.2 §五.3 / §五.10；成员B确认_v1.0 §八）：
//   1. 一侧写（B 输出流）、一侧读（UART 回读），互不冲突；
//   2. 一个条带写满 → bank 满 → 另一 bank 空闲则**立即交换**（不留覆盖窗口）；
//   3. 另一 bank 未释放 → 写侧**硬反压**（wr_ready=0），**绝不覆盖**；
//   4. 满状态后不丢弃 / 不覆盖 / 不回绕；允许无限期停顿；
//   5. 回读必须**逐字节**与写入一致，且**条带顺序为 FIFO**；
//   6. 末条带为**部分条带**（长度 < WIDTH*ROWS）也要能正确收尾与回读。
//
// 定向用例（全部确定性，无 fork）：
//   T1 单条带写入 + 立即回读
//   T2 两条带连写 + 顺序回读
//   T3 两条带连写后不释放 → wr_ready 必须掉 0（反压且不覆盖）；
//      回读释放 1 条 → wr_ready 恢复 → 写第 3 条 → 顺序回读
//   T4 部分条带（len=12 < 32）收尾 + 回读
//   T5 overflow_err 恒为 0；写入/回读字节数一致（不丢数据）
//   T6 buf_state 观察到 WRITING / SWAPPING / DRAINING
//
// 磁盘安全：无波形 dump；参数极小（8×4 = 32 B/条带）；有硬 timeout。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module tb_stripe_buffer;

    localparam integer WIDTH    = 8;
    localparam integer ROWS     = 4;
    localparam integer DATA_W   = 8;
    localparam integer ADDR_W   = (WIDTH*ROWS + 1 <= 1) ? 1 : $clog2(WIDTH*ROWS + 1); // 6
    localparam integer LEN_FULL = WIDTH * ROWS;                                       // 32
    localparam integer LEN_PART = 12;                                                 // 部分条带

    localparam integer MAX_CYC  = 20000;

    //-------------------------------------------------------------------------
    // DUT
    //-------------------------------------------------------------------------
    reg  clk = 0, rst_n = 0;
    reg               wr_push = 0;
    reg  [DATA_W-1:0] wr_data = 0;
    reg  [ADDR_W-1:0] wr_stripe_len = LEN_FULL;
    wire              wr_ready, wr_ready_nxt;
    reg               rd_req = 0;
    wire              rd_valid, rd_start, rd_last, rd_avail, rd_busy;
    wire [DATA_W-1:0] rd_data;
    wire [ADDR_W-1:0] rd_len;
    wire [1:0]        buf_state;
    wire              overflow_err;

    pingpong_buffer #(
        .WIDTH (WIDTH), .ROWS (ROWS), .DATA_W (DATA_W), .ADDR_W (ADDR_W)
    ) dut (
        .clk           (clk),
        .rst_n         (rst_n),
        .wr_push       (wr_push),
        .wr_data       (wr_data),
        .wr_stripe_len (wr_stripe_len),
        .wr_ready      (wr_ready),
        .wr_ready_nxt  (wr_ready_nxt),
        .rd_req        (rd_req),
        .rd_avail      (rd_avail),
        .rd_valid      (rd_valid),
        .rd_data       (rd_data),
        .rd_start      (rd_start),
        .rd_last       (rd_last),
        .rd_len        (rd_len),
        .rd_busy       (rd_busy),
        .buf_state     (buf_state),
        .overflow_err  (overflow_err)
    );

    always #5 clk = ~clk;

    //-------------------------------------------------------------------------
    // 统计与错误
    //-------------------------------------------------------------------------
    integer err_cnt, exp_val, wr_base, wr_total, rd_total;
    reg     st_writing_seen, st_swapping_seen, st_draining_seen, wr_ready_dropped;

    initial begin
        err_cnt = 0; exp_val = 0; wr_base = 0; wr_total = 0; rd_total = 0;
        st_writing_seen = 0; st_swapping_seen = 0; st_draining_seen = 0;
        wr_ready_dropped = 0;
    end

    task fail(input [8*80-1:0] msg);
        begin
            err_cnt = err_cnt + 1;
            $display("[FAIL] %0t : %0s", $time, msg);
        end
    endtask

    // 状态观测（含 overflow_err 持续监测）
    always @(posedge clk) begin
        if (rst_n) begin
            if (!wr_ready) wr_ready_dropped = 1;
            case (buf_state)
                2'b01: st_writing_seen  = 1;
                2'b10: st_swapping_seen = 1;
                2'b11: st_draining_seen = 1;
            endcase
            if (overflow_err) fail("overflow_err asserted (buffer overwritten!)");
        end
    end

    //-------------------------------------------------------------------------
    // 写一个条带：len 字节，值 = 从 wr_base 起的连续计数
    //   严格按 wr_ready 握手（wr_ready=0 时等待，**绝不强行写**）
    //-------------------------------------------------------------------------
    task push_stripe(input integer len);
        integer i;
        begin
            wr_stripe_len = len;
            for (i = 0; i < len; i = i + 1) begin
                @(negedge clk);
                while (!wr_ready) @(negedge clk);   // 反压等待
                wr_data = (wr_base + i) & 8'hFF;
                wr_push = 1'b1;
                @(negedge clk);
                wr_push = 1'b0;
                wr_total = wr_total + 1;
            end
            wr_base = wr_base + len;
        end
    endtask

    //-------------------------------------------------------------------------
    // 回读 n 字节：必须与写入顺序逐字节一致
    //-------------------------------------------------------------------------
    task drain_bytes(input integer n);
        integer i;
        begin
            for (i = 0; i < n; i = i + 1) begin
                wait (rd_avail);
                @(negedge clk);
                while (!rd_busy) @(negedge clk);    // 等 pingpong 起一次回读
                rd_req = 1'b1;
                @(negedge clk);
                rd_req = 1'b0;
                while (!rd_valid) @(negedge clk);   // 1 拍后数据有效
                if (rd_data !== (exp_val & 8'hFF)) begin
                    $display("  rd[%0d] got=%02x exp=%02x", rd_total, rd_data, exp_val & 8'hFF);
                    fail("readback byte mismatch");
                end
                if ((i == 0)        && !rd_start) fail("rd_start not asserted on stripe first byte");
                if ((i == (n-1))    && !rd_last ) fail("rd_last not asserted on stripe last byte");
                exp_val  = exp_val + 1;
                rd_total = rd_total + 1;
            end
        end
    endtask

    //-------------------------------------------------------------------------
    // 主流程
    //-------------------------------------------------------------------------
    integer k;
    initial begin
        $display("=====================================================");
        $display(" tb_stripe_buffer : WIDTH=%0d ROWS=%0d 满条带=%0d B  部分条带=%0d B  ADDR_W=%0d",
                 WIDTH, ROWS, LEN_FULL, LEN_PART, ADDR_W);
        $display("=====================================================");

        rst_n = 1'b0;
        repeat (10) @(negedge clk);
        rst_n = 1'b1;
        repeat (3) @(negedge clk);

        //---------------------------------------------------------------------
        // T1 单条带：写满 → 立即回读
        //---------------------------------------------------------------------
        $display("[T1] 写 1 个满条带 + 回读");
        push_stripe(LEN_FULL);
        drain_bytes(LEN_FULL);

        //---------------------------------------------------------------------
        // T2 两条带连写（触发一次交换）+ 顺序回读
        //---------------------------------------------------------------------
        $display("[T2] 连写 2 个满条带 + 顺序回读");
        push_stripe(LEN_FULL);
        push_stripe(LEN_FULL);
        drain_bytes(LEN_FULL);
        drain_bytes(LEN_FULL);

        //---------------------------------------------------------------------
        // T3 反压：连写 2 条后**不释放** → wr_ready 必须掉 0 且不覆盖
        //---------------------------------------------------------------------
        $display("[T3] 连写 2 条后不释放（考察反压 + 不覆盖）");
        push_stripe(LEN_FULL);
        push_stripe(LEN_FULL);
        repeat (100) @(negedge clk);            // 让状态稳定在「满 + 等交换」
        if (wr_ready !== 1'b0) begin
            $display("  wr_ready=%b buf_state=%b", wr_ready, buf_state);
            fail("T3: 两 bank 皆满时 wr_ready 未拉低（反压失效 → 会覆盖）");
        end
        if (buf_state !== 2'b10) begin
            $display("  buf_state=%b (期望 2'b10 SWAPPING)", buf_state);
            fail("T3: 反压时 buf_state 不是 SWAPPING");
        end
        // 反压期间持续观察 wr_ready 必须一直为 0（不允许「偷偷放行」）
        for (k = 0; k < 200; k = k + 1) begin
            @(negedge clk);
            if (wr_ready !== 1'b0) fail("T3: 反压期间 wr_ready 意外拉高");
        end
        // 回读 1 条 → 释放一个 bank
        drain_bytes(LEN_FULL);
        // wr_ready 恢复后写第 3 条
        @(negedge clk);
        while (!wr_ready) @(negedge clk);
        push_stripe(LEN_FULL);
        drain_bytes(LEN_FULL);
        drain_bytes(LEN_FULL);

        //---------------------------------------------------------------------
        // T4 部分条带（模拟末条带）
        //---------------------------------------------------------------------
        $display("[T4] 部分条带（len=%0d）收尾 + 回读", LEN_PART);
        push_stripe(LEN_PART);
        drain_bytes(LEN_PART);

        //---------------------------------------------------------------------
        // T5 / T6 汇总
        //---------------------------------------------------------------------
        repeat (20) @(negedge clk);

        if (overflow_err !== 1'b0) fail("T5: overflow_err 非 0");
        if (wr_total !== rd_total) begin
            $display("  wr_total=%0d rd_total=%0d", wr_total, rd_total);
            fail("T5: 写入/回读字节数不一致（丢数据）");
        end
        if (!st_writing_seen)  fail("T6: 未观察到 WRITING 状态");
        if (!st_swapping_seen) fail("T6: 未观察到 SWAPPING 状态");
        if (!st_draining_seen) fail("T6: 未观察到 DRAINING 状态");

        $display("-----------------------------------------------------");
        $display(" wr_total=%0d  rd_total=%0d  exp_val=%0d", wr_total, rd_total, exp_val);
        $display(" states: WRITING=%b SWAPPING=%b DRAINING=%b",
                 st_writing_seen, st_swapping_seen, st_draining_seen);
        $display(" overflow_err=%b  wr_ready_dropped=%b", overflow_err, wr_ready_dropped);
        $display("-----------------------------------------------------");
        if (err_cnt == 0) $display("RESULT: PASS  (T1~T6, 0 error)");
        else              $display("RESULT: FAIL  (err_cnt=%0d)", err_cnt);
        $finish;
    end

    //-------------------------------------------------------------------------
    // 硬 timeout
    //-------------------------------------------------------------------------
    initial begin
        #(MAX_CYC * 10);
        $display("RESULT: FAIL (hard timeout)");
        $finish;
    end

endmodule

`default_nettype wire
