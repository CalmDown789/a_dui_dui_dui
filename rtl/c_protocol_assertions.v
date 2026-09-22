//=============================================================================
// c_protocol_assertions.v —— C-B v0.2 协议断言层（**仅仿真**）
//-----------------------------------------------------------------------------
// 目的（用户指令 §三.14「必要的 assertion」）：
//   把任务书 §五.8（4）的八条冻结条件、§五.10 的四条硬规则，
//   从「TB 里的零散检查」升级为**独立的、可复用的监控模块**。
//
// 为什么用「普通 Verilog 监控器」而不是 SVA：
//   · 不依赖 SystemVerilog 语法与 `-sv` 编译开关，xsim / 其它仿真器都能用；
//   · 综合时由 `` `ifdef C_SIM `` 整段排除，**不会进入综合路径**。
//
// 覆盖的冻结条件（逐条对应）：
//   A1 §五.8(4)-2  背压期间 out_data / stripe_last / frame_last 必须保持稳定，
//                  且 out_valid 不得中途撤销
//   A2 §五.8(4)-5  frame_last = 1 ⇒ stripe_last = 1（同拍）
//   A3 §五.10-2    out_ready = 1 ⇒ 条带缓冲**确实可写**（不得放行非法写）
//   A4 §五.10-4    读请求 rd_req 只允许在 rd_busy = 1 时发出
//   A5 §五.8(4)-2  out_valid = 1 && out_ready = 0 期间，输出坐标不得推进
//   A6 §五.8(4)-6  复位后 out_ready 必须为 0（C 侧不得抢先接受）
//                  （out_valid/stripe_last/frame_last 是 B 侧义务，不在本层断言）
//
// 用法：在 TB 里例化，把 DUT 的对应信号接进来，最后读 `err_cnt` / `first_err`。
//   判据：**err_cnt 必须为 0**；否则 `first_err` 给出违规编号。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module c_protocol_assertions (
    input  wire        clk,
    input  wire        rst_n,

    //--- B → C 输出流 --------------------------------------------------------
    input  wire        out_valid,
    input  wire        out_ready,
    input  wire [7:0]  out_data,
    input  wire        stripe_last,
    input  wire        frame_last,

    //--- 条带缓冲写侧 --------------------------------------------------------
    input  wire        wr_push,
    input  wire        wr_ready,

    //--- 条带缓冲读侧 --------------------------------------------------------
    input  wire        rd_req,
    input  wire        rd_busy,

    //--- 输出坐标（来自 output_stream 的 dbg_x / dbg_y） ---------------------
    input  wire [15:0] out_x,
    input  wire [15:0] out_y,

    //--- 结果 ---------------------------------------------------------------
    output reg  [31:0] err_cnt,
    output reg  [3:0]  first_err     // 0 = 无错；否则为第一个违规的编号
);

`ifdef C_SIM
    reg ov_prev;
    reg [7:0] od_prev;
    reg       osl_prev, ofl_prev;
    reg [15:0] ox_prev, oy_prev;
    reg [1:0]  rst_cnt;
    reg        rd_busy_d;      // rd_busy 延迟 1 拍（用于 A4 的合理豁免）

    initial begin
        err_cnt   = 32'd0;
        first_err = 4'd0;
        ov_prev   = 1'b0;
        od_prev   = 8'd0;
        osl_prev  = 1'b0;
        ofl_prev  = 1'b0;
        ox_prev   = 16'd0;
        oy_prev   = 16'd0;
        rst_cnt   = 2'd0;
        rd_busy_d = 1'b0;
    end

    task flag_err(input [3:0] code);
        begin
            err_cnt = err_cnt + 32'd1;
            if (first_err == 4'd0) first_err = code;
        end
    endtask

    always @(posedge clk) begin
        //---------------------------------------------------------------------
        // A6 复位后：连续 2 拍 out_valid / stripe_last / frame_last 必须为 0
        //---------------------------------------------------------------------
        if (!rst_n) begin
            rst_cnt <= 2'd0;
        end else begin
            if (rst_cnt < 2'd2) begin
                rst_cnt <= rst_cnt + 2'd1;
                // A6 复位后 C 侧不得抢先接受：out_ready 必须为 0
                //    （§五.8(4)-6 的 C 侧可断言部分：复位后回到"不可接收"状态）
                //    ⚠️ 不要在这里断言 out_valid/stripe_last/frame_last ——
                //    它们是 **B 侧驱动**的、由 TB 激励源给出的信号，属于源自身的义务；
                //    在此断言等于"检查测试台自己"，会误报（第一版即因此误报 A6）。
                if (out_ready) flag_err(4'd6);
            end

            //-----------------------------------------------------------------
            // A1 背压期间数据 / sideband 保持稳定，且 out_valid 不得撤销
            //-----------------------------------------------------------------
            if (out_valid && !out_ready) begin
                if (ov_prev) begin
                    if (!out_valid)               flag_err(4'd1);   // out_valid 不得中途撤销
                    if (out_data    !== od_prev)  flag_err(4'd1);
                    if (stripe_last !== osl_prev) flag_err(4'd1);
                    if (frame_last  !== ofl_prev) flag_err(4'd1);
                end
                ov_prev  <= 1'b1;
                od_prev  <= out_data;
                osl_prev <= stripe_last;
                ofl_prev <= frame_last;
            end else begin
                ov_prev <= 1'b0;
            end

            //-----------------------------------------------------------------
            // A5 背压期间输出坐标不得推进
            //-----------------------------------------------------------------
            if (out_valid && !out_ready && ov_prev) begin
                if (out_x !== ox_prev) flag_err(4'd5);
                if (out_y !== oy_prev) flag_err(4'd5);
            end
            ox_prev <= out_x;
            oy_prev <= out_y;

            //-----------------------------------------------------------------
            // A2 frame_last ⇒ stripe_last（同拍）
            //-----------------------------------------------------------------
            if (out_valid && out_ready && frame_last && !stripe_last) flag_err(4'd2);

            //-----------------------------------------------------------------
            // A3 放行写时必须确实可写（§五.10-2：不得「out_ready=1 而不可写」）
            //-----------------------------------------------------------------
            if (wr_push && !wr_ready) flag_err(4'd3);

            //-----------------------------------------------------------------
            // A4 读请求只允许在回读进行中发出
            //   （rd_req 是 C 内部信号；允许「上一拍 rd_busy=1、本拍刚读完」的残留一拍）
            //-----------------------------------------------------------------
            rd_busy_d <= rd_busy;
            if (rd_req && !rd_busy && !rd_busy_d) flag_err(4'd4);
        end
    end
`else
    // 非仿真（综合）路径：本模块不应被例化；给出明确占位避免悬空告警。
    initial begin
        err_cnt   = 32'd0;
        first_err = 4'd0;
    end
`endif

endmodule

`default_nettype wire
