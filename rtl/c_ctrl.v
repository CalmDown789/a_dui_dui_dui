//=============================================================================
// c_ctrl.v —— start / busy / done 控制框架
//-----------------------------------------------------------------------------
// 依据：
//   · 用户指令 §六「start 语义」：
//       cycle N   : start 被接受（且**只允许在 busy=0 时**接受）
//       cycle N+1 : 进入输入阶段；从 N+1 起允许第一像素握手
//   · v3.2.2 §五.8（1）：start = 单脉冲，与 clk_200 同步；busy 在 start 后 ≥1 拍拉高；
//     done 与 frame_last 同拍或其后 1 拍，**语义 ≠ frame_last**
//   · 成员B对C架构接口与资源预算确认_v1.0 §六：
//       done = 「最终像素 out_valid && out_ready && frame_last」的**下一拍脉冲**
//
// 输出语义（本模块同时产出两套命名，避免混淆）：
//   start_b     : 给 B 的 start（1 拍脉冲，在 cycle N+1 发出）
//   input_load  : 给 input_stream 的「进入输入阶段」脉冲（也在 cycle N+1）
//   run         : 帧运行期间为 1；供 output_stream 使能 out_ready
//   busy        : 帧进行中（cycle N+1 起为 1，done 拍起为 0）
//   done        : 1 拍脉冲，位于「最终像素握手」的**后 1 拍**（= F+1）
//
// 时序对照（start 在 cycle N 被接受，最终像素在 cycle F 握手成功）：
//   N   : st=IDLE, start=1 → 接受
//   N+1 : busy=1, run=1, start_b=1, input_load=1        （进入输入阶段）
//   N+2 : input_stream 首个 in_valid（像素 (0,0)）      （= start 后 1 拍，合规）
//   F   : 最终像素 out_valid&&out_ready&&frame_last 握手
//   F+1 : done=1（单拍），busy=0                        （= 最终像素的下一拍）
//   F+2 : st=IDLE，可再次接受 start（支持连续第二帧）
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

module c_ctrl (
    input  wire clk,
    input  wire rst_n,
    //--- 主机控制 -------------------------------------------------------------
    input  wire start,              // 1 拍脉冲（或电平，仅在 busy=0 时被接受）
    output reg  busy,
    output reg  done,
    //--- 给 B / 输入通路 ------------------------------------------------------
    output reg  start_b,            // C → B：启动一帧
    output reg  input_load,         // C 内部：进入输入阶段
    output reg  run,                // C 内部：帧运行中（使能 out_ready）
    //--- 来自 output_stream（B 侧的 done 可由 b_done 交叉核对） ---------------
    input  wire frame_last_accept,  // 组合：最终像素本拍握手成功
    //--- 交叉核对（仅状态记录，不改变数据通路） ------------------------------
    input  wire b_busy,
    input  wire b_done,
    output reg  b_done_seen
);

    localparam [1:0] S_IDLE  = 2'd0,
                     S_RUN   = 2'd1,
                     S_DONE  = 2'd2;

    reg [1:0] st;
    reg       entered_q;    // RUN 状态内「已发出 start_b/input_load」标记

    // 默认赋值（脉冲信号每拍自动清零，避免多驱动记忆）
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st           <= S_IDLE;
            busy         <= 1'b0;
            done         <= 1'b0;
            start_b      <= 1'b0;
            input_load   <= 1'b0;
            run          <= 1'b0;
            entered_q    <= 1'b0;
            b_done_seen  <= 1'b0;
        end else begin
            start_b    <= 1'b0;     // 单拍脉冲，默认清零
            input_load <= 1'b0;
            done       <= 1'b0;

            // B 的 done 记录（独立于 C 自己的 done；用于集成期交叉核对）
            if (b_done) begin
                b_done_seen <= 1'b1;
            end

            case (st)
                //-------------------------------------------------------------
                S_IDLE: begin
                    busy <= 1'b0;
                    run  <= 1'b0;
                    // ★ start 只允许在 busy=0 时接受
                    if (start) begin
                        st        <= S_RUN;
                        busy      <= 1'b1;
                        run       <= 1'b1;
                        entered_q <= 1'b0;
                    end
                end
                //-------------------------------------------------------------
                S_RUN: begin
                    run  <= 1'b1;
                    busy <= 1'b1;

                    // cycle N+1：进入输入阶段 + 给 B 的 start
                    if (!entered_q) begin
                        start_b    <= 1'b1;
                        input_load <= 1'b1;
                        entered_q  <= 1'b1;
                    end

                    // 最终像素握手（cycle F）→ 下一拍 done（F+1）
                    if (frame_last_accept) begin
                        st        <= S_DONE;
                        run       <= 1'b0;
                        busy      <= 1'b0;
                        done      <= 1'b1;
                        entered_q <= 1'b0;
                    end
                end
                //-------------------------------------------------------------
                S_DONE: begin
                    // done 已在上一拍置起；本状态仅作 1 拍收尾，回到 IDLE
                    done      <= 1'b0;
                    busy      <= 1'b0;
                    st        <= S_IDLE;
                    entered_q <= 1'b0;
                end
                //-------------------------------------------------------------
                default: st <= S_IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
