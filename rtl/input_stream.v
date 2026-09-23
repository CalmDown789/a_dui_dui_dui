//=============================================================================
// input_stream.v —— 输入像素流发生器（C → B 的 in_valid/in_ready/in_data）
//-----------------------------------------------------------------------------
// 依据：
//   · v3.2.2 §五.9（1）输入像素流契约（C→B）
//   · v3.2.2 §五.9（4）ROM 读接口必须验证的七项边界条件
//   · 成员B对C架构接口与资源预算确认_v1.1 B-ARCH-3：每帧恰好 518400 个像素
//   · 用户指令 §五：in_ready=0 时 in_data / 当前地址 / x / y 必须保持
//   · 用户指令 §六：start 在 N 拍被接受，N+1 进入输入阶段
//
// ★ 地址写法声明（§五.9（4）第 7 项「必须二者择一并在实现说明中写明」）：
//   ROM 地址由 req_addr_q 寄存器驱动；每个被发出的请求对应下一拍的
//   rom_dout/resp_valid。地址递增不再位于 BRAM 地址/银行使能组合路径上。
//
// 时序（start 在 cycle N 被 c_ctrl 接受）：
//   N+1 : start_load=1 → 输入阶段开始；rom_en=1，rom_addr = 0（首个请求）
//   N+2 : in_valid=1，in_data = mem[0]  ← 第 1 个像素 (0,0)
//         （§五.9：start 后【不早于 1 拍】给出第 1 个像素；此处 = start 后 1 拍，合规）
//
// 背压保持：resp_valid=1 && in_ready=0 时不发新请求，ROM 输出和响应坐标
// 保持稳定。C 核心前的弹性 FIFO 也保证 B 侧 stall 时当前 data/x/y 不变。
//
// 位宽说明：所有内部计数器均为**无符号**；比较常量均为参数表达式，无符号扩展一致。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module input_stream #(
    parameter integer IMG_W   = `C_IMG_W,       // 960
    parameter integer IMG_H   = `C_IMG_H,       // 540
    parameter integer PIXEL_W = `C_PIXEL_W,     // 8
    parameter integer ADDR_W  = `C_ROM_ADDR_W,  // 19
    parameter integer TOT_PIX = `C_IN_PIXELS    // 518400
) (
    input  wire                clk,
    input  wire                rst_n,       // 低有效（已含 MMCM locked 门控）
    //--- 控制 -----------------------------------------------------------------
    input  wire                start_load,  // 1 拍脉冲：进入输入阶段（cycle N+1）
    //--- 到 B 的输入流 --------------------------------------------------------
    output wire                in_valid,
    output wire [PIXEL_W-1:0]  in_data,
    input  wire                in_ready,    // B 侧反压；0 期间上式必须保持
    //--- 输入 ROM 读端口 ------------------------------------------------------
    output wire                rom_en,
    output wire [ADDR_W-1:0]   rom_addr,
    input  wire [PIXEL_W-1:0]  rom_dout,
    //--- 状态与调试 -----------------------------------------------------------
    output wire                input_active, // 输入阶段进行中
    output wire                input_done,   // 整帧输入像素已全部交付（黏滞，直到下次 start）
    output wire [15:0]         dbg_x,        // in_data 对应像素的列坐标（行主序 x）
    output wire [15:0]         dbg_y         // in_data 对应像素的行坐标（行主序 y）
);

    //-------------------------------------------------------------------------
    // 派生位宽
    //-------------------------------------------------------------------------
    localparam integer XW = (IMG_W <= 1) ? 1 : $clog2(IMG_W);
    localparam integer YW = (IMG_H <= 1) ? 1 : $clog2(IMG_H);

    //-------------------------------------------------------------------------
    // 状态寄存器
    //-------------------------------------------------------------------------
    reg  [ADDR_W-1:0] req_addr_q;  // 下一请求地址；直接驱动 ROM，0..TOT_PIX
    reg  [XW-1:0]     req_x_q;
    reg  [YW-1:0]     req_y_q;
    reg  [XW-1:0]     resp_x_q;    // 与 rom_dout/resp_valid 对齐的响应坐标
    reg  [YW-1:0]     resp_y_q;
    reg               run_q;
    reg               resp_valid_q;
    reg               done_q;

    //-------------------------------------------------------------------------
    // 响应弹性保持 + 独立请求地址寄存器
    //-------------------------------------------------------------------------
    wire in_fire  = in_valid & in_ready;
    wire req_fire = run_q & (req_addr_q < TOT_PIX) & (~resp_valid_q | in_ready);

    assign in_valid = resp_valid_q;
    assign rom_addr = req_addr_q;
    assign rom_en   = req_fire;
    assign in_data  = rom_dout;

    //-------------------------------------------------------------------------
    // 请求地址/坐标只在实际读 ROM 时推进；响应元数据跟随同步读延迟
    //-------------------------------------------------------------------------
    wire          last_col = (req_x_q == IMG_W - 1);
    wire          last_row = (req_y_q == IMG_H - 1);
    wire [XW-1:0] req_x_nx = last_col ? {XW{1'b0}} : (req_x_q + 1'b1);
    wire [YW-1:0] req_y_nx = last_col ? (last_row ? req_y_q : (req_y_q + 1'b1)) : req_y_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            run_q    <= 1'b0;
            resp_valid_q <= 1'b0;
            done_q   <= 1'b0;
            req_addr_q <= {ADDR_W{1'b0}};
            req_x_q <= {XW{1'b0}};
            req_y_q <= {YW{1'b0}};
            resp_x_q <= {XW{1'b0}};
            resp_y_q <= {YW{1'b0}};
        end else if (start_load) begin
            run_q    <= 1'b1;
            resp_valid_q <= 1'b0;
            done_q   <= 1'b0;
            req_addr_q <= {ADDR_W{1'b0}};
            req_x_q <= {XW{1'b0}};
            req_y_q <= {YW{1'b0}};
            resp_x_q <= {XW{1'b0}};
            resp_y_q <= {YW{1'b0}};
        end else begin
            if (req_fire) begin
                req_addr_q <= req_addr_q + 1'b1;
                resp_x_q <= req_x_q;
                resp_y_q <= req_y_q;
                if (!(last_col && last_row)) begin
                    req_x_q <= req_x_nx;
                    req_y_q <= req_y_nx;
                end
            end

            if (req_fire) resp_valid_q <= 1'b1;
            else if (in_fire) resp_valid_q <= 1'b0;

            if (in_fire && (req_addr_q == TOT_PIX)) begin
                run_q  <= 1'b0;
                done_q <= 1'b1;
            end
        end
    end

    //-------------------------------------------------------------------------
    // 状态输出
    //-------------------------------------------------------------------------
    assign input_active = run_q;
    assign input_done   = done_q;
    assign dbg_x        = {{(16-XW){1'b0}}, resp_x_q};
    assign dbg_y        = {{(16-YW){1'b0}}, resp_y_q};

endmodule

`default_nettype wire
