//=============================================================================
// b_real_bench_top.v —— B 真实 RTL 的**目标器件**综合基准顶层
//-----------------------------------------------------------------------------
// 存在理由（用户指令 §三「综合/实现取证」+ §二「真实 B 模块接入」）：
//
//   · 成员 B 的本地 Vivado 2025.2 **缺少 xc7a200tfbg484-2 器件数据**，
//     B 自己的 `docs/synthesis_status.md` 明确记录 `No parts matched`，
//     所以 B 只能给 xc7z020 的 fallback 数据，**从未在目标器件上综合过**。
//   · C 侧本机装的是 Vivado 2022.2，**有**该器件数据。
//   · 因此本文件在 C 侧把 B 已交付的 17 个原语**全部实例化**并真实综合一次，
//     目的是给 B 补上「目标器件上的结构推断/资源/时序」证据。
//
// ⚠️ 严格边界（不得越界解读）：
//   1. 这是 **B 原语集合**的综合，**不是**五层网络，**不是**系统级结论；
//      不得据此宣称系统 BRAM/B 的 271 块预算已被证实或推翻。
//   2. 只做 synthesis；**不做** place/route，**不生成** bitstream。
//   3. 输入全部来自顶层端口（真实综合时端口不可被常量折叠），
//      输出经约简后引出，避免综合器把整块逻辑裁掉导致资源虚低。
//   4. window 原语按真实 IMG_W=960 实例化（行缓冲真实规模）。
//
// B 来源：CalmDown789/a_dui_dui_dui @ acx750-rtl @ 658c82e2
//=============================================================================

`timescale 1ns / 1ps

module b_real_bench_top #(
    parameter integer IMG_W      = 960,
    parameter integer ROM_DEPTH  = 4096,
    parameter        ROM_MEM_FILE = "rtl/b_real_bench_param.mem"
)(
    input  wire                clk,
    input  wire                rst,
    input  wire                dvalid_in,
    input  wire [199:0]        x_in,        // 5x5 展平激活（也供 3x3 前 72 位使用）
    input  wire [199:0]        k_in,        // 5x5 展平权重（也供 3x3 前 72 位使用）
    input  wire [15:0]         pix16_in,    // 16-bit 行缓冲像素
    input  wire [7:0]          pix8_in,     // 8-bit 流式像素
    input  wire signed [31:0]  bias_in,
    input  wire signed [15:0]  prelu_in,
    input  wire signed [31:0]  mult_in,
    output reg  [63:0]         dout,
    output reg                 dvalid_out
);

    //=========================================================================
    // 1. 乘法器原语
    //=========================================================================
    wire signed [15:0] sm_p;
    dsp_signed_mult #(.A_W(8), .B_W(8)) u_sm (
        .clk(clk), .rst(rst), .enable(dvalid_in),
        .a(x_in[7:0]), .b(k_in[7:0]), .product(sm_p)
    );

    wire signed [15:0] u8_p;
    dsp_u8s8_mult #(.ACT_W(8), .WGT_W(8)) u_u8 (
        .clk(clk), .rst(rst), .enable(dvalid_in),
        .activation(x_in[7:0]), .weight(k_in[7:0]), .product(u8_p)
    );

    //=========================================================================
    // 2. 点积流水线
    //=========================================================================
    wire signed [19:0] d9;
    wire               d9_v;
    dot9_pipeline #(.ACT_W(8), .WGT_W(8)) u_d9 (
        .clk(clk), .rst(rst), .in_valid(dvalid_in),
        .x00(x_in[7:0]),   .x01(x_in[15:8]),  .x02(x_in[23:16]),
        .x10(x_in[31:24]), .x11(x_in[39:32]), .x12(x_in[47:40]),
        .x20(x_in[55:48]), .x21(x_in[63:56]), .x22(x_in[71:64]),
        .k00(k_in[7:0]),   .k01(k_in[15:8]),  .k02(k_in[23:16]),
        .k10(k_in[31:24]), .k11(k_in[39:32]), .k12(k_in[47:40]),
        .k20(k_in[55:48]), .k21(k_in[63:56]), .k22(k_in[71:64]),
        .dot9(d9), .dot9_valid(d9_v)
    );

    wire signed [20:0] d25;
    wire               d25_v;
    dot25_pipeline #(.ACT_W(8), .WGT_W(8)) u_d25 (
        .clk(clk), .rst(rst), .in_valid(dvalid_in),
        .x_flat(x_in), .k_flat(k_in),
        .dot25(d25), .dot25_valid(d25_v)
    );

    wire signed [20:0] d25u;
    wire               d25u_v;
    dot25_u8s8_pipeline #(.ACT_W(8), .WGT_W(8)) u_d25u (
        .clk(clk), .rst(rst), .in_valid(dvalid_in),
        .x_flat(x_in), .k_flat(k_in),
        .dot25(d25u), .dot25_valid(d25u_v)
    );

    //=========================================================================
    // 3. 累加器 / 各阶卷积 backend
    //=========================================================================
    wire signed [31:0] ca_res;
    wire               ca_rv;
    channel_accumulator #(.DOT_W(20), .ACC_W(32), .CHANNELS(1)) u_ca (
        .clk(clk), .rst(rst), .dot_valid(dvalid_in), .dot_value(x_in[19:0]),
        .bias(bias_in), .result(ca_res), .result_valid(ca_rv)
    );

    wire signed [31:0] c1_res;
    wire               c1_rv;
    conv1x1_backend #(.ACT_W(8), .WGT_W(8), .ACC_W(32), .CHANNELS(1)) u_c1 (
        .clk(clk), .rst(rst), .in_valid(dvalid_in),
        .x(x_in[7:0]), .k(k_in[7:0]), .bias(bias_in),
        .result(c1_res), .result_valid(c1_rv)
    );

    wire signed [31:0] c3_res;
    wire               c3_rv;
    conv3x3_backend #(.ACT_W(8), .WGT_W(8), .ACC_W(32), .CHANNELS(1)) u_c3 (
        .clk(clk), .rst(rst), .in_valid(dvalid_in),
        .x00(x_in[7:0]),   .x01(x_in[15:8]),  .x02(x_in[23:16]),
        .x10(x_in[31:24]), .x11(x_in[39:32]), .x12(x_in[47:40]),
        .x20(x_in[55:48]), .x21(x_in[63:56]), .x22(x_in[71:64]),
        .k00(k_in[7:0]),   .k01(k_in[15:8]),  .k02(k_in[23:16]),
        .k10(k_in[31:24]), .k11(k_in[39:32]), .k12(k_in[47:40]),
        .k20(k_in[55:48]), .k21(k_in[63:56]), .k22(k_in[71:64]),
        .bias(bias_in), .result(c3_res), .result_valid(c3_rv)
    );

    wire signed [31:0] c5_res;
    wire               c5_rv;
    conv5x5_backend #(.ACT_W(8), .WGT_W(8), .ACC_W(32), .CHANNELS(1)) u_c5 (
        .clk(clk), .rst(rst), .in_valid(dvalid_in),
        .x_flat(x_in), .k_flat(k_in), .bias(bias_in),
        .result(c5_res), .result_valid(c5_rv)
    );

    wire signed [31:0] c5u_res;
    wire               c5u_rv;
    conv5x5_u8s8_backend #(.ACT_W(8), .WGT_W(8), .ACC_W(32), .CHANNELS(1)) u_c5u (
        .clk(clk), .rst(rst), .in_valid(dvalid_in),
        .x_flat(x_in), .k_flat(k_in), .bias(bias_in),
        .result(c5u_res), .result_valid(c5u_rv)
    );

    //=========================================================================
    // 4. 窗口原语（真实 IMG_W=960）
    //=========================================================================
    wire [7:0] w3s00, w3s01, w3s02, w3s10, w3s11, w3s12, w3s20, w3s21, w3s22;
    wire       w3s_v;
    window3x3_stream #(.DATA_W(8), .IMG_W(IMG_W)) u_w3s (
        .clk(clk), .rst(rst), .pixel_in(pix8_in), .pixel_valid(dvalid_in),
        .w00(w3s00), .w01(w3s01), .w02(w3s02),
        .w10(w3s10), .w11(w3s11), .w12(w3s12),
        .w20(w3s20), .w21(w3s21), .w22(w3s22),
        .window_valid(w3s_v)
    );

    wire [15:0] w3b00, w3b01, w3b02, w3b10, w3b11, w3b12, w3b20, w3b21, w3b22;
    wire        w3b_v;
    window3x3_bram #(.DATA_W(16), .IMG_W(IMG_W)) u_w3b (
        .clk(clk), .rst(rst), .pixel_in(pix16_in), .pixel_valid(dvalid_in),
        .w00(w3b00), .w01(w3b01), .w02(w3b02),
        .w10(w3b10), .w11(w3b11), .w12(w3b12),
        .w20(w3b20), .w21(w3b21), .w22(w3b22),
        .window_valid(w3b_v)
    );

    wire [199:0] w5s_flat;
    wire         w5s_v;
    window5x5_stream #(.DATA_W(8), .IMG_W(IMG_W)) u_w5s (
        .clk(clk), .rst(rst), .pixel_in(pix8_in), .pixel_valid(dvalid_in),
        .window_flat(w5s_flat), .window_valid(w5s_v)
    );

    wire [399:0] w5b_flat;
    wire         w5b_v;
    window5x5_bram #(.DATA_W(16), .IMG_W(IMG_W)) u_w5b (
        .clk(clk), .rst(rst), .pixel_in(pix16_in), .pixel_valid(dvalid_in),
        .window_flat(w5b_flat), .window_valid(w5b_v)
    );

    //=========================================================================
    // 5. 参数 ROM + 后处理
    //=========================================================================
    wire [7:0] rom_d;
    sync_parameter_rom #(
        .DATA_W(8), .DEPTH(ROM_DEPTH), .MEM_FILE(ROM_MEM_FILE)
    ) u_rom (
        .clk(clk), .enable(dvalid_in), .address(x_in[11:0]), .data(rom_d)
    );

    wire [10:0] ps_ox, ps_oy;
    wire [7:0]  ps_od;
    pixel_shuffle2x_coord_map #(.X_W(10), .Y_W(10), .DATA_W(8)) u_ps (
        .in_x(x_in[9:0]), .in_y(x_in[19:10]), .phase(k_in[1:0]),
        .in_data(x_in[7:0]), .out_x(ps_ox), .out_y(ps_oy), .out_data(ps_od)
    );

    wire [15:0] pr_out;
    wire        pr_ov;
    prelu_requantize #(.OUT_W(16), .OUT_SIGNED(1), .APPLY_PRELU(1)) u_pr (
        .clk(clk), .rst(rst), .in_valid(dvalid_in),
        .accumulator_int32(bias_in), .prelu_q15(prelu_in),
        .multiplier_q31(mult_in), .out_data(pr_out), .out_valid(pr_ov)
    );

    //=========================================================================
    // 6. 输出约简 —— 保证上面每一块都不会被综合器裁掉
    //    （端口输入不可常量折叠；约简把全部输出位都吃掉）
    //=========================================================================
    integer gi;
    reg [7:0]  w3s_red;
    reg [7:0]  w3b_red;
    reg [7:0]  w5s_red;
    reg [15:0] w5b_red;

    always @* begin
        w3s_red = 8'd0;
        w3s_red = w3s_red ^ w3s00 ^ w3s01 ^ w3s02;
        w3s_red = w3s_red ^ w3s10 ^ w3s11 ^ w3s12;
        w3s_red = w3s_red ^ w3s20 ^ w3s21 ^ w3s22;

        w3b_red = 8'd0;
        w3b_red = w3b_red ^ w3b00[7:0] ^ w3b00[15:8] ^ w3b01[7:0] ^ w3b01[15:8];
        w3b_red = w3b_red ^ w3b02[7:0] ^ w3b02[15:8] ^ w3b10[7:0] ^ w3b10[15:8];
        w3b_red = w3b_red ^ w3b11[7:0] ^ w3b11[15:8] ^ w3b12[7:0] ^ w3b12[15:8];
        w3b_red = w3b_red ^ w3b20[7:0] ^ w3b20[15:8] ^ w3b21[7:0] ^ w3b21[15:8];
        w3b_red = w3b_red ^ w3b22[7:0] ^ w3b22[15:8];
    end

    always @* begin
        w5s_red = 8'd0;
        for (gi = 0; gi < 25; gi = gi + 1)
            w5s_red = w5s_red ^ w5s_flat[gi*8 +: 8];

        w5b_red = 16'd0;
        for (gi = 0; gi < 25; gi = gi + 1)
            w5b_red = w5b_red ^ w5b_flat[gi*16 +: 16];
    end

    wire [63:0] contrib;
    assign contrib =
          {{48{sm_p[15]}},  sm_p}
        + {{48{u8_p[15]}},  u8_p}
        + {{44{d9[19]}},    d9}
        + {{43{d25[20]}},   d25}
        + {{43{d25u[20]}},  d25u}
        + {{32{ca_res[31]}},  ca_res}
        + {{32{c1_res[31]}},  c1_res}
        + {{32{c3_res[31]}},  c3_res}
        + {{32{c5_res[31]}},  c5_res}
        + {{32{c5u_res[31]}}, c5u_res}
        + {{56{1'b0}}, rom_d}
        + {{53{1'b0}}, ps_ox}
        + {{53{1'b0}}, ps_oy}
        + {{56{1'b0}}, ps_od}
        + {{48{1'b0}}, pr_out}
        + {{56{1'b0}}, w3s_red}
        + {{56{1'b0}}, w3b_red}
        + {{56{1'b0}}, w5s_red}
        + {{48{1'b0}}, w5b_red};

    always @(posedge clk) begin
        if (rst) begin
            dout       <= 64'd0;
            dvalid_out <= 1'b0;
        end else begin
            dout       <= contrib;
            dvalid_out <= d9_v ^ d25_v ^ d25u_v ^ ca_rv ^ c1_rv ^ c3_rv
                          ^ c5_rv ^ c5u_rv ^ w3s_v ^ w3b_v ^ w5s_v ^ w5b_v ^ pr_ov;
        end
    end

endmodule
