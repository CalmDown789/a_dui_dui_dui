//=============================================================================
// tb_backpressure_rand.v —— 随机 / 「恶意」背压压力测试（C18 可独立完成的部分）
//-----------------------------------------------------------------------------
// 依据：
//   · 任务书 v3.2.2 §五.8（5）C18：六种背压场景「缺一不可」；
//     判据是**输出字节序列逐字节一致 + 边界位置一致**。
//   · §五.10 规则 4：必须包含 `out_ready` 随机拉低的背压用例。
//   · 用户指令 §十三 D/E/I：stall 期间 data/sideband 保持、buffer 满反压。
//
// 与 tb_ready_valid.v 的分工：
//   tb_ready_valid  **定向**覆盖 A~K（确定性激励，好定位）；
//   本 TB           **随机化**施压（好找边界外的漏网 bug）：
//     · B 侧 out_valid 随机出现空档（5~20 拍），并按 **hold-until-accept** 保持；
//     · 读侧 rd_req 随机出现 3~18 拍停顿；
//     · 三个不同 LFSR 种子各跑一帧，逐字节比对回读结果。
//
// 断言：例化 `c_protocol_assertions`（A1~A6，见该文件），最后判 err_cnt == 0。
//
// 磁盘安全：**无波形 dump**；小规模（OUT 16×12，直接读条带缓冲，不经 UART）；
//           每帧有硬 timeout；总共 3 帧。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module tb_backpressure_rand;

    localparam integer OUT_W     = 16;
    localparam integer OUT_H     = 12;
    localparam integer STRIPE_H  = 5;
    localparam integer N_STRIPES = (OUT_H + STRIPE_H - 1) / STRIPE_H;   // 3（5/5/2）
    localparam integer TOT_OUT   = OUT_W * OUT_H;                       // 192
    localparam integer ADDR_W    = (OUT_W*STRIPE_H + 1 <= 1) ? 1 : $clog2(OUT_W*STRIPE_H + 1); // 7
    localparam integer MAX_CYC   = 200000;
    localparam integer N_SEED    = 3;

    //=========================================================================
    // 0. 全部内部信号**先声明**（避免隐式网声明 / 重复声明）
    //=========================================================================
    reg  clk = 0, rst_n = 0, run = 0, frame_start = 0;

    //--- TB 扮演的 B 侧输出源 ------------------------------------------------
    reg  [15:0] lfsr;
    reg  [7:0]  gap_q;
    reg         src_valid_q;
    reg  [31:0] beat;
    wire        want;
    wire        src_valid;
    wire        src_accept;
    wire [31:0] beat_x, beat_y;
    wire        src_sl, src_fl;

    //--- C 侧 DUT 输出 -------------------------------------------------------
    wire              out_ready;
    wire              wr_push, wr_ready, wr_ready_nxt;
    wire [7:0]        wr_data;
    wire [ADDR_W-1:0] wr_stripe_len;
    wire [15:0]       dbg_x, dbg_y, stripe_cnt;
    wire [4:0]        stripe_idx;
    wire              frame_last_accept, frame_last_fire, proto_err;

    //--- 读侧 ---------------------------------------------------------------
    reg  [7:0]  rd_gap_q;
    wire        rd_req;
    wire        rd_valid, rd_start, rd_last, rd_avail, rd_busy;
    wire [7:0]  rd_data;
    wire [ADDR_W-1:0] rd_len;
    wire [1:0]  buf_state;
    wire        overflow_err;

    //--- 断言层 -------------------------------------------------------------
    wire [31:0] asrt_cnt;
    wire [3:0]  asrt_first;

    //=========================================================================
    // 1. DUT
    //=========================================================================
    output_stream #(
        .OUT_W (OUT_W), .OUT_H (OUT_H), .STRIPE_H (STRIPE_H), .DATA_W (8), .ADDR_W (ADDR_W)
    ) u_out (
        .clk (clk), .rst_n (rst_n), .run (run), .frame_start (frame_start),
        .out_valid       (src_valid),
        .out_data        (beat[7:0]),
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

    //--- 协议断言层（A1~A6） --------------------------------------------------
    c_protocol_assertions u_assert (
        .clk (clk), .rst_n (rst_n),
        .out_valid (src_valid), .out_ready (out_ready), .out_data (beat[7:0]),
        .stripe_last (src_sl), .frame_last (src_fl),
        .wr_push (wr_push), .wr_ready (wr_ready),
        .rd_req (rd_req), .rd_busy (rd_busy),
        .out_x (dbg_x), .out_y (dbg_y),
        .err_cnt (asrt_cnt), .first_err (asrt_first)
    );

    always #5 clk = ~clk;

    //=========================================================================
    // 2. 「恶意」B 侧输出源：随机空档 + hold-until-accept
    //    LFSR: x^16 + x^14 + x^13 + x^11 + 1
    //=========================================================================
    assign src_valid     = src_valid_q;
    assign src_accept    = src_valid & out_ready;
    assign beat_x        = beat % OUT_W;
    assign beat_y        = beat / OUT_W;
    assign src_sl        = (beat_x == (OUT_W-1)) && ((((beat_y + 1) % STRIPE_H) == 0) || (beat_y == (OUT_H-1)));
    assign src_fl        = (beat_x == (OUT_W-1)) && (beat_y == (OUT_H-1));
    // 生成器「意愿」：仅在帧运行期间、且无空档、随机位允许时才发
    //   （run 为门 ⇒ 复位后与帧外 out_valid 恒 0，符合真实 B 的 start 语义）
    assign want          = run && (gap_q == 8'd0) && (lfsr[1] | lfsr[2]);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr        <= 16'hACE1;
            gap_q       <= 8'd0;
            src_valid_q <= 1'b0;
            beat        <= 32'd0;
        end else begin
            lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};

            // 空档倒计时；空闲时按随机条件装载 5~20 拍空档
            if (gap_q != 8'd0) begin
                gap_q <= gap_q - 8'd1;
            end else if (lfsr[11:8] == 4'h0) begin
                gap_q <= {4'd0, lfsr[7:4]} + 8'd5;
            end

            // ★ hold-until-accept：一旦拉高，未被接受前不得撤销
            //   ★ 帧末尾立即退休：最后一拍被接受后**不再展示新 beat**，
            //     保证整帧恰好 TOT_OUT 拍（否则可能多算 1 拍）
            if (src_accept && src_fl) begin
                src_valid_q <= 1'b0;
            end else if (!src_valid_q) begin
                src_valid_q <= want;
            end else if (src_accept) begin
                src_valid_q <= want;
            end
            // else: 保持 1

            if (src_accept) beat <= beat + 32'd1;
        end
    end

    //=========================================================================
    // 3. 「恶意」读侧：随机 rd_req（本拍组合，以 rd_busy 为门 ⇒ 永不产生非法请求）
    //=========================================================================
    assign rd_req = rd_busy && (rd_gap_q == 8'd0) && (lfsr[7] | lfsr[9]);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_gap_q <= 8'd0;
        end else begin
            if (rd_gap_q != 8'd0) begin
                rd_gap_q <= rd_gap_q - 8'd1;
            end else if (lfsr[15:12] == 4'h0) begin
                rd_gap_q <= {4'd0, lfsr[6:3]} + 8'd3;    // 3~18 拍不回读
            end
        end
    end

    //=========================================================================
    // 4. 统计与判定
    //=========================================================================
    integer err_cnt;
    integer out_accepts, rd_bytes, sl_cnt, fl_cnt;
    integer stall_cur, stall_max;
    integer cyc;
    integer seed_i;
    reg     mon_en;

    task fail(input [8*80-1:0] msg);
        begin
            err_cnt = err_cnt + 1;
            if (err_cnt <= 20) $display("[FAIL] seed#%0d %0t : %0s", seed_i, $time, msg);
        end
    endtask

    initial begin
        err_cnt = 0; out_accepts = 0; rd_bytes = 0; sl_cnt = 0; fl_cnt = 0;
        stall_cur = 0; stall_max = 0; mon_en = 0; seed_i = 0;
    end

    always @(posedge clk) begin
        if (rst_n && mon_en) begin
            if (src_valid && !out_ready) begin
                stall_cur = stall_cur + 1;
                if (stall_cur > stall_max) stall_max = stall_cur;
            end else begin
                stall_cur = 0;
            end
            if (src_accept) begin
                out_accepts = out_accepts + 1;
                if (src_sl) sl_cnt = sl_cnt + 1;
                if (src_fl) fl_cnt = fl_cnt + 1;
            end
            if (rd_valid) begin
                if (rd_data !== (rd_bytes & 8'hFF)) begin
                    $display("  rd[%0d] got=%02x exp=%02x", rd_bytes, rd_data, rd_bytes & 8'hFF);
                    fail("readback byte mismatch");
                end
                rd_bytes = rd_bytes + 1;
            end
            if (proto_err)     fail("proto_err asserted");
            if (overflow_err)  fail("overflow_err asserted");
            if (asrt_cnt != 0) fail("protocol assertion fired");
        end
    end

    //=========================================================================
    // 5. 主流程：3 个种子各跑一帧
    //=========================================================================
    integer s;
    initial begin
        $display("=====================================================");
        $display(" tb_backpressure_rand : OUT %0dx%0d STRIPE_H=%0d -> %0d stripes, TOT_OUT=%0d",
                 OUT_W, OUT_H, STRIPE_H, N_STRIPES, TOT_OUT);
        $display(" random out_valid gaps + random rd_req stalls ; assertions A1~A6");
        $display("=====================================================");

        for (s = 0; s < N_SEED; s = s + 1) begin
            seed_i = s;

            rst_n = 1'b0; run = 1'b0; frame_start = 1'b0;
            repeat (6) @(negedge clk);
            lfsr  = 16'hACE1 + s * 16'h1357;      // 三个不同种子
            rst_n = 1'b1;
            repeat (3) @(negedge clk);

            out_accepts = 0; rd_bytes = 0; sl_cnt = 0; fl_cnt = 0;
            stall_cur = 0; stall_max = 0;
            mon_en = 1;

            $display("--- seed #%0d (lfsr init = %04h) ---", s, lfsr);

            @(negedge clk); frame_start = 1'b1; run = 1'b1;
            @(negedge clk); frame_start = 1'b0;

            cyc = 0;
            while ((fl_cnt < 1) && (cyc < MAX_CYC)) begin
                @(negedge clk);
                cyc = cyc + 1;
            end
            if (fl_cnt < 1) begin
                fail("TIMEOUT: frame_last never accepted");
                $display("RESULT: FAIL (timeout at seed %0d)", s);
                $finish;
            end
            repeat (3) @(negedge clk);
            run = 1'b0;

            cyc = 0;
            while ((rd_bytes < TOT_OUT) && (cyc < MAX_CYC)) begin
                @(negedge clk);
                cyc = cyc + 1;
            end
            repeat (5) @(negedge clk);
            mon_en = 0;

            if (out_accepts !== TOT_OUT) begin
                $display("  out_accepts=%0d (exp %0d)", out_accepts, TOT_OUT);
                fail("output pixel count mismatch");
            end
            if (sl_cnt !== N_STRIPES) begin
                $display("  stripe_last=%0d (exp %0d)", sl_cnt, N_STRIPES);
                fail("stripe_last count mismatch");
            end
            if (fl_cnt !== 1) begin
                $display("  frame_last=%0d (exp 1)", fl_cnt);
                fail("frame_last count mismatch");
            end
            if (rd_bytes !== TOT_OUT) begin
                $display("  rd_bytes=%0d (exp %0d)", rd_bytes, TOT_OUT);
                fail("readback byte count mismatch");
            end
            if (stall_max < 5) fail("no meaningful back-pressure observed (stall_max < 5)");

            $display("[seed #%0d] out=%0d rd=%0d stripes=%0d frame=%0d longest_stall=%0d asrt=%0d",
                     s, out_accepts, rd_bytes, sl_cnt, fl_cnt, stall_max, asrt_cnt);
            if (asrt_first != 4'd0) $display("  first assertion violation code = A%0d", asrt_first);
        end

        $display("-----------------------------------------------------");
        $display(" 3 seeds x 1 frame done; err_cnt=%0d", err_cnt);
        if (err_cnt == 0) $display("RESULT: PASS  (randomized back-pressure stress, 0 error)");
        else              $display("RESULT: FAIL  (err_cnt=%0d)", err_cnt);
        $finish;
    end

    //-------------------------------------------------------------------------
    // 硬 timeout
    //-------------------------------------------------------------------------
    initial begin
        #(MAX_CYC * 10 * (N_SEED + 2));
        $display("RESULT: FAIL (hard timeout)");
        $finish;
    end

endmodule

`default_nettype wire
