//=============================================================================
// tb_ready_valid.v —— 小规模全链路 ready/valid + 条带/帧边界 + 背压测试
//-----------------------------------------------------------------------------
// 覆盖（用户指令 §十三 A~K，一个都不少）：
//   A  ready 永远为 1        → 复位后前 ~700 拍（缓冲区未满，写侧畅通）
//   B  ready 周期性拉低      → UART 每字节忙 → 条带间周期性反压
//   C  ready 连续拉低几十拍  → rb_enable=0 期间缓冲区写满 → 长背压
//   D  out stall 时 data/stripe_last/frame_last 保持稳定（逐拍比对）
//   E  in_ready=0 时 in_data / rom_addr / x / y 保持稳定（逐拍比对）
//   F  stripe 边界（x=OUT_W-1 且 y 落在条带末行）
//   G  最后一条带为部分条带（OUT_H=32 / STRIPE_H=5 → 7 条，末条 2 行）
//   H  frame_last（仅 x=OUT_W-1 且 y=OUT_H-1）
//   I  buffer 满 → 反压（观察 out_ready 掉 0 且不覆盖）
//   J  start / busy / done 时序
//   K  连续启动第二帧
//
// 判据（§五.8（5））：
//   · UART 解出的**输出字节序列逐字节**等于期望序列（两帧都要一致）；
//   · stripe_last / frame_last 的位置一致（由 TB 独立复算）；
//   · 无 proto_err / overflow_err。
//
// 磁盘安全（用户指令 §十二）：
//   · **不打开 waveform dump**（无 $dumpfile/$dumpvars）；
//   · 只用小规模参数（32×16 → 64×32，共 2048 输出字节）；
//   · 有明确 timeout，绝不会无限跑。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module tb_ready_valid;

    //-------------------------------------------------------------------------
    // 小规模参数（用户指令 §十二：IMG_W=32 / IMG_H=16 / STRIPE_H 小）
    //   STRIPE_H 取 5（**奇数**）而不是 4，是为了额外覆盖两件事：
    //     1) OUT_H=32 不能被 5 整除 → **末条带为 2 行**（覆盖 §十三 G）
    //     2) 条带边界落在「同一输入行的前半输出行」上 → 覆盖条带几何在中途推进
    //-------------------------------------------------------------------------
    localparam integer IMG_W     = 32;
    localparam integer IMG_H     = 16;
    localparam integer OUT_W     = 64;          // = 2*IMG_W
    localparam integer OUT_H     = 32;          // = 2*IMG_H
    localparam integer STRIPE_H  = 5;
    localparam integer TOT_IN    = IMG_W * IMG_H;    // 512
    localparam integer TOT_OUT   = OUT_W * OUT_H;    // 2048
    localparam integer N_STRIPES = (OUT_H + STRIPE_H - 1) / STRIPE_H;  // 7

    localparam integer CLK_HZ    = 1000;
    localparam integer UART_BAUD = 100;
    localparam integer BAUD_DIV  = CLK_HZ / UART_BAUD;                 // 10 cycles/bit

    localparam integer MAX_CYC   = 900000;      // 硬 timeout（约 2 帧 UART 的 2 倍余量）

    //-------------------------------------------------------------------------
    // DUT
    //-------------------------------------------------------------------------
    reg  clk = 0, rst_n = 0, start = 0, rb_enable = 0;
    wire busy, done, uart_tx;
    wire [1:0]  dbg_buf_state;
    wire [15:0] dbg_stripe_cnt, dbg_stripes_sent, dbg_in_x, dbg_in_y, dbg_out_x, dbg_out_y;
    wire [31:0] dbg_uart_bytes;
    wire        dbg_proto_err, dbg_overflow_err, dbg_in_done, dbg_b_busy, dbg_b_done_seen;

    c_core #(
        .IMG_W         (IMG_W),
        .IMG_H         (IMG_H),
        .OUT_W         (OUT_W),
        .OUT_H         (OUT_H),
        .STRIPE_H      (STRIPE_H),
        .PIXEL_W       (8),
        .ROM_ADDR_W    (10),        // 覆盖 512 像素（2^9=512 → 用 10 位留 1 位余量）
        .ROM_DEPTH     (1024),
        .ROM_INIT_MODE (1),         // 公式填充（SIM ONLY）：TB 可独立复算期望值
        .ROM_INIT_EN   (0),
        .ROM_INIT_FILE (""),
        .CLK_HZ        (CLK_HZ),
        .UART_BAUD     (UART_BAUD)
    ) dut (
        .clk              (clk),
        .rst_n            (rst_n),
        .start            (start),
        .busy             (busy),
        .done             (done),
        .rb_enable        (rb_enable),
        .uart_tx          (uart_tx),
        .dbg_buf_state    (dbg_buf_state),
        .dbg_stripe_cnt   (dbg_stripe_cnt),
        .dbg_uart_bytes   (dbg_uart_bytes),
        .dbg_stripes_sent (dbg_stripes_sent),
        .dbg_proto_err    (dbg_proto_err),
        .dbg_overflow_err (dbg_overflow_err),
        .dbg_in_done      (dbg_in_done),
        .dbg_b_busy       (dbg_b_busy),
        .dbg_b_done_seen  (dbg_b_done_seen),
        .dbg_in_x        (dbg_in_x),
        .dbg_in_y        (dbg_in_y),
        .dbg_out_x       (dbg_out_x),
        .dbg_out_y       (dbg_out_y)
    );

    always #5 clk = ~clk;      // 周期 10 时间单位（与 timescale 无关，纯计数用）

    //-------------------------------------------------------------------------
    // 期望模型（与 input_rom.v 的 INIT_MODE=1 公式**完全一致**）
    //-------------------------------------------------------------------------
    function [7:0] pat(input integer a);
        begin
            pat = ((a * 7) + (a >> 8) + 13) & 32'h000000FF;
        end
    endfunction

    // 输出像素 n（行主序，跨帧循环）的期望字节 = 2×2 最近邻复制的对应输入像素
    function [7:0] exp_out(input integer n0);
        integer n, xx, yy, ix, iy, aa;
        begin
            n  = n0 % TOT_OUT;              // ★ 跨帧回绕（第 2 帧复用同一序列）
            xx = n % OUT_W;
            yy = n / OUT_W;
            ix = xx >> 1;
            iy = yy >> 1;
            aa = iy * IMG_W + ix;
            exp_out = pat(aa);
        end
    endfunction

    //-------------------------------------------------------------------------
    // 误差计数与统计
    //-------------------------------------------------------------------------
    integer err_cnt;
    integer in_accept_cnt;      // 输入像素握手次数（应为 TOT_IN × 帧数）
    integer out_accept_cnt;     // 输出像素握手次数（应为 TOT_OUT × 帧数）
    integer stall_long_cnt;     // out_valid=1 && out_ready=0 的连续最长拍数
    integer stall_cur;
    integer in_stall_long;
    integer in_stall_cur;
    integer done_cnt;
    integer max_addr_seen;
    integer tb_stripe_last_cnt;   // TB 自己统计的 stripe_last 脉冲数（跨帧累计）
    integer tb_frame_last_cnt;    // TB 自己统计的 frame_last 脉冲数
    reg     saw_first_pixel, saw_last_pixel;

    initial begin
        err_cnt = 0; in_accept_cnt = 0; out_accept_cnt = 0;
        stall_long_cnt = 0; stall_cur = 0;
        in_stall_long = 0; in_stall_cur = 0;
        done_cnt = 0; max_addr_seen = 0;
        tb_stripe_last_cnt = 0; tb_frame_last_cnt = 0;
        saw_first_pixel = 0; saw_last_pixel = 0;
    end

    task fail(input [8*80-1:0] msg);
        begin
            err_cnt = err_cnt + 1;
            if (err_cnt <= 20) $display("[FAIL] %0t : %0s", $time, msg);
        end
    endtask

    //-------------------------------------------------------------------------
    // 监控 D：out_valid=1 && out_ready=0 期间，数据与 sideband 必须保持稳定
    //-------------------------------------------------------------------------
    reg        ov_prev;
    reg [7:0]  od_prev;
    reg        osl_prev, ofl_prev;

    always @(posedge clk) begin
        if (rst_n) begin
            if (dut.b_out_valid && !dut.out_ready) begin
                if (ov_prev) begin
                    if (dut.b_out_data !== od_prev)     fail("D: out_data drifted during stall");
                    if (dut.b_stripe_last !== osl_prev) fail("D: stripe_last drifted during stall");
                    if (dut.b_frame_last  !== ofl_prev) fail("D: frame_last drifted during stall");
                end
                ov_prev <= 1'b1;
                od_prev <= dut.b_out_data;
                osl_prev <= dut.b_stripe_last;
                ofl_prev  <= dut.b_frame_last;
            end else begin
                ov_prev <= 1'b0;
            end
        end
    end

    //-------------------------------------------------------------------------
    // 监控 E：in_valid=1 && in_ready=0 期间，in_data / rom_addr / x / y 必须保持
    //-------------------------------------------------------------------------
    reg                 iv_prev;
    reg [7:0]           id_prev;
    reg [9:0]           ia_prev;
    reg [15:0]          ix_prev, iy_prev;

    always @(posedge clk) begin
        if (rst_n) begin
            if (dut.in_valid && !dut.in_ready) begin
                if (iv_prev) begin
                    if (dut.in_data         !== id_prev) fail("E: in_data drifted during in-stall");
                    if (dut.rom_addr        !== ia_prev) fail("E: rom_addr drifted during in-stall");
                    if (dut.dbg_in_x        !== ix_prev)  fail("E: x drifted during in-stall");
                    if (dut.dbg_in_y        !== iy_prev)  fail("E: y drifted during in-stall");
                end
                iv_prev <= 1'b1;
                id_prev <= dut.in_data;
                ia_prev <= dut.rom_addr;
                ix_prev <= dut.dbg_in_x;
                iy_prev <= dut.dbg_in_y;
            end else begin
                iv_prev <= 1'b0;
            end
        end
    end

    //-------------------------------------------------------------------------
    // 输入侧核对：数据 = pat(y*IMG_W+x)，坐标范围合法，端点覆盖
    //-------------------------------------------------------------------------
    integer ia_last;
    always @(posedge clk) begin
        if (rst_n) begin
            if (dut.rom_addr > TOT_IN) begin
                fail("rom_addr exceeded fill-region start (overflow)");
            end
            if (dut.rom_addr > max_addr_seen) max_addr_seen = dut.rom_addr;

            if (dut.in_valid && dut.in_ready) begin
                in_accept_cnt = in_accept_cnt + 1;
                if (dut.dbg_in_x >= IMG_W) fail("in x out of range");
                if (dut.dbg_in_y >= IMG_H) fail("in y out of range");
                ia_last = dut.dbg_in_y * IMG_W + dut.dbg_in_x;
                if (dut.in_data !== pat(ia_last)) fail("in_data != pat(addr)  (off-by-one?)");

                if (dut.dbg_in_x == 0 && dut.dbg_in_y == 0) begin
                    if (dut.in_data !== pat(0)) fail("E: first pixel (0,0) data wrong");
                    saw_first_pixel = 1;
                end
                if ((dut.dbg_in_x == IMG_W-1) && (dut.dbg_in_y == IMG_H-1)) begin
                    if (dut.in_data !== pat(TOT_IN-1)) fail("E: last pixel (W-1,H-1) data wrong");
                    saw_last_pixel = 1;
                end
            end

            // 输入长背压统计
            if (dut.in_valid && !dut.in_ready) begin
                in_stall_cur = in_stall_cur + 1;
                if (in_stall_cur > in_stall_long) in_stall_long = in_stall_cur;
            end else in_stall_cur = 0;
        end
    end

    //-------------------------------------------------------------------------
    // 输出侧核对：逐字节比对 + 边界位置独立复算（F/G/H）
    //-------------------------------------------------------------------------
    integer ck_n, ck_x, ck_y;
    reg     ck_esl, ck_efl;

    always @(posedge clk) begin
        if (rst_n && dut.b_out_valid && dut.out_ready) begin
            // ★ 必须按 TOT_OUT 回绕：DUT 的坐标每帧从 (0,0) 重新开始
            ck_n = out_accept_cnt % TOT_OUT;
            ck_x = ck_n % OUT_W;
            ck_y = ck_n / OUT_W;
            ck_esl = (ck_x == OUT_W-1) && ((((ck_y+1) % STRIPE_H) == 0) || (ck_y == OUT_H-1));
            ck_efl = (ck_x == OUT_W-1) && (ck_y == OUT_H-1);

            if (dut.b_out_data !== exp_out(out_accept_cnt)) begin
                $display("  out[%0d] got=%02x exp=%02x", out_accept_cnt, dut.b_out_data,
                         exp_out(out_accept_cnt));
                fail("F/H: output byte mismatch");
            end
            if (dut.b_stripe_last !== ck_esl) fail("F: stripe_last position mismatch");
            if (dut.b_frame_last  !== ck_efl) fail("H: frame_last position mismatch");
            if (dut.b_frame_last && !dut.b_stripe_last) fail("H: frame_last without stripe_last");

            out_accept_cnt = out_accept_cnt + 1;
            if (dut.b_stripe_last) tb_stripe_last_cnt = tb_stripe_last_cnt + 1;
            if (dut.b_frame_last)  tb_frame_last_cnt  = tb_frame_last_cnt + 1;
        end

        // 输出长背压统计（I）+ 死锁现场快照
        if (rst_n) begin
            if (dut.b_out_valid && !dut.out_ready) begin
                stall_cur = stall_cur + 1;
                if (stall_cur > stall_long_cnt) stall_long_cnt = stall_cur;
                if (stall_cur == 200) begin
                    $display("[SNAP] long out-stall @%0t : wr_bank=%b full0=%b full1=%b pending=%b wr_cnt=%0d len=%0d other_free=%b swap_now=%b | rd_busy=%b rd_bank=%b rd_ptr=%0d rd_len=%0d rd_avail=%b | rb:%b dbg_out=(%0d,%0d) stripe=%0d",
                        $time,
                        dut.u_pp.wr_bank_q, dut.u_pp.bank_full_q[0], dut.u_pp.bank_full_q[1],
                        dut.u_pp.wr_pending_full_q, dut.u_pp.wr_cnt_q, dut.u_pp.wr_stripe_len,
                        dut.u_pp.other_free, dut.u_pp.swap_now,
                        dut.u_pp.rd_busy_q, dut.u_pp.rd_bank_q, dut.u_pp.rd_ptr_q, dut.u_pp.rd_len_q,
                        dut.u_pp.rd_avail,
                        dut.u_rb.have_q, dut.dbg_out_x, dut.dbg_out_y, dut.u_out.stripe_idx_q);
                end
            end else stall_cur = 0;
        end
    end

    //-------------------------------------------------------------------------
    // UART 8N1 解码器（在每位中点采样）
    //-------------------------------------------------------------------------
    reg        rx_run;
    reg [7:0]  rx_cnt;
    reg [3:0]  rx_idx;
    reg [7:0]  rx_sh;
    reg        uart_byte_v;
    reg [7:0]  uart_byte;
    integer    uart_n;
    integer    uart_err;

    initial begin
        rx_run = 0; rx_cnt = 0; rx_idx = 0; rx_sh = 0;
        uart_byte_v = 0; uart_byte = 0; uart_n = 0; uart_err = 0;
    end

    always @(posedge clk) begin
        uart_byte_v <= 1'b0;

        if (rst_n && !uart_tx && !rx_run) begin
            rx_run <= 1'b1;      // 检测到起始位下降沿
            rx_cnt <= 8'd0;
            rx_idx <= 4'd0;
        end else if (rx_run) begin
            // ★ 采样周期必须 = BAUD_DIV：在 cnt==BAUD_DIV/2 采样（位中点），
            //   在 cnt==BAUD_DIV-1 才回零。早期版本在采样点直接回零 → 周期变成
            //   BAUD_DIV/2+1，导致位相位漂移、误判 stop bit。
            if (rx_cnt == (BAUD_DIV - 1)) rx_cnt <= 8'd0;
            else                           rx_cnt <= rx_cnt + 8'd1;

            if (rx_cnt == (BAUD_DIV/2)) begin
                if (rx_idx == 0) begin
                    if (uart_tx !== 1'b0) begin fail("UART: start bit not low"); uart_err=uart_err+1; end
                end else if (rx_idx <= 8) begin
                    rx_sh[rx_idx-1] <= uart_tx;
                end else begin
                    if (uart_tx !== 1'b1) begin fail("UART: stop bit not high"); uart_err=uart_err+1; end
                    uart_byte   <= rx_sh;
                    uart_byte_v <= 1'b1;
                    rx_run      <= 1'b0;
                end
                rx_idx <= rx_idx + 4'd1;
            end
        end
    end

    // UART 字节逐字节核对
    always @(posedge clk) begin
        if (rst_n && uart_byte_v) begin
            if (uart_byte !== exp_out(uart_n)) begin
                $display("  uart[%0d] got=%02x exp=%02x", uart_n, uart_byte, exp_out(uart_n));
                fail("UART: readback byte mismatch");
            end
            uart_n = uart_n + 1;
        end
    end

    //-------------------------------------------------------------------------
    // 主流程
    //-------------------------------------------------------------------------
    integer cyc;
    integer t_done1, t_done2;

    initial begin
        $display("=====================================================");
        $display(" tb_ready_valid : IMG %0dx%0d -> OUT %0dx%0d, STRIPE_H=%0d (%0d stripes, last %0d rows)",
                 IMG_W, IMG_H, OUT_W, OUT_H, STRIPE_H, N_STRIPES,
                 OUT_H - (N_STRIPES-1)*STRIPE_H);
        $display(" TOT_IN=%0d  TOT_OUT=%0d  BAUD_DIV=%0d", TOT_IN, TOT_OUT, BAUD_DIV);
        $display("=====================================================");

        rst_n = 0; start = 0; rb_enable = 0;
        repeat (10) @(posedge clk);
        rst_n <= 1;
        repeat (5) @(posedge clk);

        if (dut.b_out_valid !== 1'b0) fail("cond6: out_valid not 0 after reset");
        if (dut.out_ready  !== 1'b0) fail("cond6: out_ready not 0 after reset");
        if (busy !== 1'b0)           fail("cond6: busy not 0 after reset");
        if (done !== 1'b0)           fail("cond6: done not 0 after reset");

        //---------------------------------------------------------------------
        // 帧 1：start 单拍脉冲（J）
        //---------------------------------------------------------------------
        @(posedge clk);
        start <= 1'b1;
        @(posedge clk);
        start <= 1'b0;

        // 检查 §六：start 被接受的下一拍 busy=1（输入阶段从 N+1 开始）
        @(posedge clk);
        if (busy !== 1'b1) fail("J: busy not high at N+1 after start");

        //---------------------------------------------------------------------
        // 场景 A + C + I：rb_enable 保持 0 → 缓冲区写满 → 长背压
        //---------------------------------------------------------------------
        repeat (2000) @(posedge clk);
        $display("[info] after 2000 cycles (rb_enable=0): busy=%b out_accept=%0d out_ready=%b buf_state=%b",
                 busy, out_accept_cnt, dut.out_ready, dbg_buf_state);
        if (stall_long_cnt < 50) fail("C/I: expected a long out-stall (>=50 cyc) while rb_enable=0");

        // 打开回读 → 解压并继续
        rb_enable <= 1'b1;

        // 等第 1 帧完成
        t_done1 = 0;
        cyc = 0;                    // ★ 必须显式初始化（否则 X 比较恒假，误报 timeout）
        while ((done !== 1'b1) && (cyc < MAX_CYC)) begin
            @(posedge clk);
            cyc = cyc + 1;
            t_done1 = t_done1 + 1;
        end
        if (done !== 1'b1) begin
            fail("TIMEOUT: frame1 never reached done");
            $display("RESULT: FAIL (timeout)  err=%0d", err_cnt);
            $finish;
        end
        $display("[info] frame1 done @ %0d cycles after start-open; out_accept=%0d", t_done1, out_accept_cnt);

        //---------------------------------------------------------------------
        // 场景 K：连续启动第二帧（不等 UART 回读完）
        //---------------------------------------------------------------------
        repeat (5) @(posedge clk);
        start <= 1'b1;
        @(posedge clk);
        start <= 1'b0;

        //---------------------------------------------------------------------
        // 等两帧的 UART 字节全部解出（或超时）
        //---------------------------------------------------------------------
        cyc = 0;
        while ((uart_n < (2*TOT_OUT)) && (cyc < MAX_CYC)) begin
            @(posedge clk);
            cyc = cyc + 1;
        end
        t_done2 = cyc;

        repeat (200) @(posedge clk);   // 留出尾部收尾

        //---------------------------------------------------------------------
        // 汇总
        //---------------------------------------------------------------------
        if (uart_n < (2*TOT_OUT)) fail("TIMEOUT: UART readback incomplete");
        if (in_accept_cnt  !== (2*TOT_IN))  begin
            $display("  in_accept_cnt = %0d (exp %0d)", in_accept_cnt, 2*TOT_IN);
            fail("input pixel count mismatch (back-pressure dropped pixels?)");
        end
        if (out_accept_cnt !== (2*TOT_OUT)) begin
            $display("  out_accept_cnt = %0d (exp %0d)", out_accept_cnt, 2*TOT_OUT);
            fail("output pixel count mismatch");
        end
        if (tb_stripe_last_cnt !== (2*N_STRIPES)) begin
            $display("  tb_stripe_last_cnt = %0d (exp %0d)", tb_stripe_last_cnt, 2*N_STRIPES);
            fail("stripe_last pulse count mismatch");
        end
        if (tb_frame_last_cnt !== 2) begin
            $display("  tb_frame_last_cnt = %0d (exp 2)", tb_frame_last_cnt);
            fail("frame_last pulse count mismatch");
        end
        if (dbg_proto_err    !== 1'b0) fail("proto_err asserted");
        if (dbg_overflow_err !== 1'b0) fail("overflow_err asserted (buffer overwrite!)");
        if (saw_first_pixel  !== 1'b1) fail("never saw input pixel (0,0)");
        if (saw_last_pixel   !== 1'b1) fail("never saw input pixel (W-1,H-1)");
        if (done_cnt          < 2)     fail("done pulse count < 2 (consecutive frames?)");

        $display("-----------------------------------------------------");
        $display(" cycles(2nd frame wait) = %0d", t_done2);
        $display(" in_accept   = %0d / %0d", in_accept_cnt, 2*TOT_IN);
        $display(" out_accept  = %0d / %0d", out_accept_cnt, 2*TOT_OUT);
        $display(" uart_bytes  = %0d / %0d  (uart_err=%0d)", uart_n, 2*TOT_OUT, uart_err);
        $display(" stripe_last pulses = %0d / %0d  ; frame_last pulses = %0d / 2", tb_stripe_last_cnt, 2*N_STRIPES, tb_frame_last_cnt);
        $display(" (DUT 内部 stripe_cnt 已是「本帧」计数，每帧复位，故末值为 %0d)", dbg_stripe_cnt);
        $display(" longest OUT stall = %0d cyc ; longest IN stall = %0d cyc", stall_long_cnt, in_stall_long);
        $display(" max rom_addr = %0d (fill-region start = %0d)", max_addr_seen, TOT_IN);
        $display(" proto_err=%b overflow_err=%b done_cnt=%0d", dbg_proto_err, dbg_overflow_err, done_cnt);
        $display("-----------------------------------------------------");
        if (err_cnt == 0) $display("RESULT: PASS  (all A~K scenarios, 0 error)");
        else              $display("RESULT: FAIL  (err_cnt=%0d)", err_cnt);
        $finish;
    end

    // done 计数
    always @(posedge clk) begin
        if (rst_n && done) done_cnt = done_cnt + 1;
    end

    //-------------------------------------------------------------------------
    // 硬 timeout（用户指令 §十二：必须能自动结束）
    //-------------------------------------------------------------------------
    initial begin
        #(MAX_CYC * 10 * 3);
        $display("RESULT: FAIL (hard timeout %0d cycles)", MAX_CYC*3);
        $finish;
    end

endmodule

`default_nettype wire
