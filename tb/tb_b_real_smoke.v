//=============================================================================
// tb_b_real_smoke.v —— B 五层真实网络（ae29515）小尺寸冒烟 + 协议回归
//-----------------------------------------------------------------------------
// 走的是 **b_core_if 的正式分支**（`-d C_USE_B_REAL`），即
//   b_core_if → b_core_real → fsrcnn_network_mem_top → fsrcnn_network_core
// 参数**显式传**：IMG_W=6 / IMG_H=5 / STRIPE_H=4（B 交接单第 1 条要求）。
// 若 b_core_if 不传参，`b_core_real` 会静默按 960×540 展开 —— 本 TB 会直接超时。
//
// 几何（全部由参数推导，不写死）：
//   输入像素数  N_IN   = IMG_W*IMG_H            = 30
//   输出像素数  N_OUT  = 2*IMG_W * 2*IMG_H      = 120   （每 LR 行出 2 行，每行 2*IMG_W）
//   输出行数    N_ROW  = 2*IMG_H                = 10
//   条带数      ceil(N_ROW/STRIPE_H)            = 3     （输出行 4/8 为条带界，第 10 行 = frame_last）
//
// 检查项（对应任务书 §二「仿真回归」+ §八 验收项 F/G/H/I）：
//   T1 start/busy/done 时序：start 只在 busy=0 时发一次；done 每帧恰好 1 拍
//   T2 输入握手：只按 in_valid&&in_ready 消费；恰好 N_IN 拍
//   T3 输出握手：只在 out_valid&&out_ready 同拍推进；恰好 N_OUT 拍；数据无 X
//   T4 stripe_last 次数 == ceil(N_ROW/STRIPE_H)；frame_last 恰好 1 次且落在最后一拍
//   T5 保持规则：out_valid=1&&out_ready=0 期间 out_data/stripe_last/frame_last 必须稳定
//   T6 换一组输入，输出必须发生变化（查输入通路是否真的接上）
//
// 磁盘安全：无波形 dump；120 B/帧量级；有硬 timeout。
//
// ⚠️ 本 TB **不做**数值正确性判定（小尺寸无 Golden）——
//    数值逐字节验收在 tb_b_real_bit_exact.v（96×54）与 tb_b_real_full.v（全帧）。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module tb_b_real_smoke;

    //-------------------------------------------------------------------------
    // 几何参数（与 b_core_if 传参一致）
    //-------------------------------------------------------------------------
    localparam integer IMG_W  = 6;
    localparam integer IMG_H  = 5;
    localparam integer STRIPE = 4;
    localparam integer OUT_W  = 2 * IMG_W;                        // 12
    localparam integer OUT_H  = 2 * IMG_H;                        // 10
    localparam integer N_IN   = IMG_W * IMG_H;                    // 30
    localparam integer N_OUT  = 4 * IMG_W * IMG_H;                // 120
    localparam integer N_ROW  = 2 * IMG_H;                        // 10
    localparam integer N_STRP = (N_ROW + STRIPE - 1) / STRIPE;    // 3

    localparam integer N_FRAME = 2;
    localparam integer MAX_CYC = 200000;   // 硬 timeout（远大于预期 ~2k 拍）

    //-------------------------------------------------------------------------
    // DUT：走 b_core_if 正式分支
    //-------------------------------------------------------------------------
    reg  clk = 0, rst_n = 0;
    reg  start = 0;
    wire busy, done;
    reg  in_valid = 0;
    reg  [7:0] in_data = 0;
    wire in_ready;
    wire out_valid;
    wire [7:0] out_data;
    reg  out_ready = 0;
    wire stripe_last, frame_last;

    b_core_if #(
        .IMG_W    (IMG_W),
        .IMG_H    (IMG_H),
        .OUT_W    (OUT_W),
        .OUT_H    (OUT_H),
        .STRIPE_H (STRIPE),
        .DATA_W   (8)
    ) dut (
        .clk_200     (clk),
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

    always #2.5 clk = ~clk;   // 5 ns 周期 = 200 MHz

    //-------------------------------------------------------------------------
    // 输入图案（确定性，两帧不同）
    //-------------------------------------------------------------------------
    function [7:0] pat(input integer f, input integer i);
        begin
            if (f == 0) pat = (i * 37 + 11) & 8'hFF;
            else        pat = (i * 91 + 200) & 8'hFF;
        end
    endfunction

    //-------------------------------------------------------------------------
    // 统计与错误
    //-------------------------------------------------------------------------
    integer err_cnt;
    integer cyc;

    task fail(input [8*96-1:0] msg);
        begin
            err_cnt = err_cnt + 1;
            $display("[FAIL] %0t : %0s", $time, msg);
        end
    endtask

    // 每帧统计
    integer fed, got, n_stripe, n_flast, n_done;
    integer busy_seen, out_x_err, fed_overflow;

    // 采集缓存（两帧）
    reg [7:0] cap0 [0:N_OUT-1];
    reg [7:0] cap1 [0:N_OUT-1];

    // 保持规则检查用
    reg       held;              // 上一拍处于 out_valid&&!out_ready
    reg [7:0] h_d;
    reg       h_s, h_f;
    integer   held_events;       // 观察到的「停等」拍数

    initial begin
        err_cnt     = 0;
        cyc         = 0;
        held        = 0;
        held_events = 0;
        fed_overflow = 0;
    end

    // 硬 timeout
    initial begin
        repeat (MAX_CYC) @(negedge clk);
        $display("RESULT: FAIL (hard timeout after %0d cycles)", MAX_CYC);
        $display("  last: fed=%0d got=%0d cyc=%0d in_valid=%b in_ready=%b out_valid=%b busy=%b",
                 fed, got, cyc, in_valid, in_ready, out_valid, busy);
        $finish;
    end

    //-------------------------------------------------------------------------
    // 单帧执行：start 脉冲 → 边喂边收 → 等 done
    //   注意：**必须边喂边收**。内部 FIFO 只有 32 深，先喂完再收会反压死锁。
    //   驱动统一在 negedge，信号在 posedge 前已稳定 ⇒
    //     此刻读到的 in_ready / out_valid 就是**下一个 posedge** 的握手依据。
    //-------------------------------------------------------------------------
    task run_frame(input integer f);
        begin
            //--- start 脉冲（busy 必须为 0） ---------------------------------
            @(negedge clk);
            if (busy !== 1'b0) fail("busy high before start pulse");
            start = 1'b1;
            @(negedge clk);
            start = 1'b0;

            fed = 0; got = 0; n_stripe = 0; n_flast = 0;
            busy_seen = 0; out_x_err = 0;
            held = 1'b0;
            h_d = 8'h00; h_s = 1'b0; h_f = 1'b0;

            //--- 边喂边收，直到收满 N_OUT ------------------------------------
            while (got < N_OUT) begin
                @(negedge clk);

                // (a) 驱动本拍输入
                if (fed < N_IN) begin
                    in_valid = 1'b1;
                    in_data  = pat(f, fed);
                end else begin
                    in_valid = 1'b0;
                    in_data  = 8'h00;
                end

                // (b) 输出接收策略：帧 0 全速收；帧 1 周期性停等（顺带查保持规则）
                if (f == 0) begin
                    out_ready = 1'b1;
                end else begin
                    out_ready = ((cyc % 7) >= 3);   // 每 7 拍停 3 拍
                end

                // (c) 采样「下一个 posedge 将完成的握手」
                if (in_valid && in_ready) fed = fed + 1;

                // (d) 保持规则：上一拍停等时，本拍仍未就绪 ⇒ 数据/标志必须不变
                if (held) begin
                    if (!out_valid) begin
                        fail("out_valid dropped while out_ready=0 (hold rule)");
                    end else if (out_data !== h_d || stripe_last !== h_s || frame_last !== h_f) begin
                        fail("held beat changed while out_ready=0");
                        $display("        was d=%02x s=%b f=%b  now d=%02x s=%b f=%b",
                                 h_d, h_s, h_f, out_data, stripe_last, frame_last);
                    end
                end

                // (e) 输出握手采样 + 采集
                if (out_valid && out_ready) begin
                    if (got >= N_OUT) begin
                        fail("extra output beat beyond N_OUT");
                    end else begin
                        if (f == 0) cap0[got] = out_data; else cap1[got] = out_data;
                    end
                    if (^out_data === 1'bx) begin
                        out_x_err = out_x_err + 1;
                        if (out_x_err <= 5) fail("out_data contains X");
                    end
                    n_stripe = n_stripe + stripe_last;
                    n_flast  = n_flast  + frame_last;
                    if (frame_last && (got != N_OUT-1)) fail("frame_last not on the last beat");
                    if (!frame_last && (got == N_OUT-1)) fail("last beat lacks frame_last");
                    got = got + 1;
                end

                // (f) 记录停等状态供下一拍比较
                held = (out_valid && !out_ready);
                if (held) begin
                    h_d = out_data; h_s = stripe_last; h_f = frame_last;
                    held_events = held_events + 1;
                end

                if (busy) busy_seen = busy_seen + 1;
                cyc = cyc + 1;
            end

            //--- 最后一拍后 done 应在 1 拍内出现 ------------------------------
            @(negedge clk);
            if (done) n_done = n_done + 1;
            if (busy) fail("busy still high one cycle after the last output beat");
        end
    endtask

    // 收尾：确认 done 只来一次（多出来的都算错）
    task wait_settle;
        integer k;
        begin
            for (k = 0; k < 6; k = k + 1) begin
                @(negedge clk);
                if (done) n_done = n_done + 1;
            end
        end
    endtask

    //-------------------------------------------------------------------------
    // 主流程
    //-------------------------------------------------------------------------
    integer m;
    integer diff_cnt;

    initial begin
        rst_n = 1'b0;
        repeat (6) @(negedge clk);
        rst_n = 1'b1;
        repeat (2) @(negedge clk);

        // 复位后：busy/done/out_valid/in_ready 必须都为 0
        if (busy !== 1'b0)      fail("busy not 0 after reset");
        if (done !== 1'b0)      fail("done not 0 after reset");
        if (out_valid !== 1'b0) fail("out_valid not 0 after reset");
        if (in_ready !== 1'b0)  fail("in_ready should be 0 before start");

        //--- 帧 0（全速收） -----------------------------------------------
        n_done = 0;
        run_frame(0);
        wait_settle;
        if (fed > N_IN) fed_overflow = fed - N_IN;
        $display("  frame0: fed=%0d got=%0d stripe_last=%0d frame_last=%0d done=%0d busy_cyc=%0d",
                 fed, got, n_stripe, n_flast, n_done, busy_seen);
        if (fed      != N_IN)   fail("frame0 input beat count mismatch");
        if (got      != N_OUT)  fail("frame0 output beat count mismatch");
        if (n_stripe != N_STRP) fail("frame0 stripe_last count mismatch");
        if (n_flast  != 1)      fail("frame0 frame_last count mismatch");
        if (n_done   != 1)      fail("frame0 done pulse count mismatch");
        if (out_x_err != 0)     fail("frame0 output had X");

        //--- 帧 1（带停等） -----------------------------------------------
        n_done = 0;
        run_frame(1);
        wait_settle;
        $display("  frame1: fed=%0d got=%0d stripe_last=%0d frame_last=%0d done=%0d busy_cyc=%0d held=%0d",
                 fed, got, n_stripe, n_flast, n_done, busy_seen, held_events);
        if (fed      != N_IN)   fail("frame1 input beat count mismatch");
        if (got      != N_OUT)  fail("frame1 output beat count mismatch");
        if (n_stripe != N_STRP) fail("frame1 stripe_last count mismatch");
        if (n_flast  != 1)      fail("frame1 frame_last count mismatch");
        if (n_done   != 1)      fail("frame1 done pulse count mismatch");
        if (held_events == 0)   fail("frame1 produced no stall cycles -- backpressure not exercised");

        //--- T6 两帧输入不同 ⇒ 输出必须存在差异（否则输入通路是死的） ------
        diff_cnt = 0;
        for (m = 0; m < N_OUT; m = m + 1) begin
            if (cap0[m] !== cap1[m]) diff_cnt = diff_cnt + 1;
        end
        $display("  frame0 vs frame1 differing bytes: %0d / %0d", diff_cnt, N_OUT);
        if (diff_cnt == 0) fail("two different inputs produced identical output -- input path dead?");

        $display("  total cycles = %0d", cyc);
        if (err_cnt == 0) begin
            $display("RESULT: PASS  (B real five-layer smoke: protocol/flags/hold, %0d frames)", N_FRAME);
        end else begin
            $display("RESULT: FAIL  (err_cnt=%0d)", err_cnt);
        end
        $finish;
    end

endmodule

`default_nettype wire
