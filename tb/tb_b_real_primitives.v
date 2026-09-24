//=============================================================================
// tb_b_real_primitives.v —— C 侧环境下对**真实 B RTL** 的编译+展开+功能验证
//-----------------------------------------------------------------------------
// 目的（用户指令 §二「真实 B 模块接入」）：
//   证明 C 侧仿真文件列表里接入的是 B 的**真实交付 RTL**，而不是 C 自己的
//   stub / mock。本 TB 分两部分：
//
//   (A) 功能自检：对 3 个算式原语 + 2 个流水原语 + 1 个 ROM 给出**逐值期望**并比对。
//       · dsp_signed_mult      signed INT8 × signed INT8
//       · dsp_u8s8_mult        uint8 × signed INT8（首层无符号激活路径）
//       · pixel_shuffle2x_coord_map  四相位坐标映射（C0 TL / C1 TR / C2 BL / C3 BR）
//       · prelu_requantize     Q1.15 PReLU + Q31 requant（负半轴「中点远离零」舍入）
//       · channel_accumulator  加偏置 + 末级 INT32 饱和
//       · sync_parameter_rom   同步 ROM + $readmemh 装载（TB 内独立复算 LCG 期望值）
//       共 30 项逐值断言（pass=30 / fail=0 为通过）。
//
//   (B) 展开覆盖：把 B 交付的其余原语全部实例化，保证它们在 C 侧 xsim 下
//       **编译并展开通过**（不驱动，仅验证端口/依赖完整）。
//
// ⚠️ 本 TB **不**验证五层网络、调度、padding 边界或 30fps。
//    B 尚未交付五层集成 top（依据 B v1.1 §十.5），任何「已接入真实 B 五层」
//    的说法都是错的。
//
// B 来源：CalmDown789/a_dui_dui_dui @ acx750-rtl @ 658c82e2
//         见 rtl/b_real/PROVENANCE.md
//
// ★ 采样纪律（踩过坑，勿改）：
//   1. **只在 negedge 驱动输入、也只在负沿采样输出**。
//      `@(posedge clk); x = dut_out;` 会读到**上一拍**的值——DUT 的
//      非阻塞赋值在 NBA 区生效，晚于 TB 的 active 区，产生竞态。
//      若在正沿直接读，会出现「结果整体错位一拍」，看起来像 RTL 算错。
//   2. **valid 必须保持整整一个时钟周期**。写成
//      `v=1; @(negedge clk); v=0;` 时 v 只高了 0 ns，正沿根本采不到，
//      表现为「等 valid 超时」。
//
// 通过标志：ACX750_C_SIDE_B_REAL_PRIMITIVES_PASS
// 失败标志：ACX750_C_SIDE_B_REAL_PRIMITIVES_FAIL
//=============================================================================

`timescale 1ns / 1ps

module tb_b_real_primitives;

    integer fail_cnt = 0;
    integer pass_cnt = 0;

    task chk_i;
        input [511:0] tag;
        input signed [63:0] got;
        input signed [63:0] exp;
        begin
            if (got === exp) begin
                pass_cnt = pass_cnt + 1;
            end else begin
                fail_cnt = fail_cnt + 1;
                $display("[FAIL] %0s got=%0d exp=%0d (t=%0t)", tag, got, exp, $time);
            end
        end
    endtask

    //-------------------------------------------------------------------------
    // 时钟 / 复位
    //-------------------------------------------------------------------------
    reg clk = 1'b0;
    reg rst = 1'b1;
    always #5 clk = ~clk;          // 100 MHz（TB 级，与板级 200MHz 无关）

    //-------------------------------------------------------------------------
    // (A1) dsp_signed_mult —— 1 拍延迟
    //-------------------------------------------------------------------------
    reg  signed [7:0] sm_a = 8'sd0, sm_b = 8'sd0;
    reg               sm_en = 1'b0;
    wire signed [15:0] sm_p;

    dsp_signed_mult #(.A_W(8), .B_W(8)) u_sm (
        .clk(clk), .rst(rst), .enable(sm_en), .a(sm_a), .b(sm_b), .product(sm_p)
    );

    //-------------------------------------------------------------------------
    // (A2) dsp_u8s8_mult —— 1 拍延迟
    //-------------------------------------------------------------------------
    reg        [7:0]  u8_a = 8'd0;
    reg  signed [7:0] u8_b = 8'sd0;
    reg               u8_en = 1'b0;
    wire signed [15:0] u8_p;

    dsp_u8s8_mult #(.ACT_W(8), .WGT_W(8)) u_u8 (
        .clk(clk), .rst(rst), .enable(u8_en),
        .activation(u8_a), .weight(u8_b), .product(u8_p)
    );

    //-------------------------------------------------------------------------
    // (A3) pixel_shuffle2x_coord_map —— 组合逻辑
    //-------------------------------------------------------------------------
    reg  [9:0]  ps_x = 10'd0;
    reg  [9:0]  ps_y = 10'd0;
    reg  [1:0]  ps_ph = 2'd0;
    reg  [7:0]  ps_d = 8'd0;
    wire [10:0] ps_ox, ps_oy;
    wire [7:0]  ps_od;

    pixel_shuffle2x_coord_map #(.X_W(10), .Y_W(10), .DATA_W(8)) u_ps (
        .in_x(ps_x), .in_y(ps_y), .phase(ps_ph), .in_data(ps_d),
        .out_x(ps_ox), .out_y(ps_oy), .out_data(ps_od)
    );

    //-------------------------------------------------------------------------
    // (A4) prelu_requantize —— 4 级流水
    //-------------------------------------------------------------------------
    reg               pr_v = 1'b0;
    reg  signed [31:0] pr_acc = 32'sd0;
    reg  signed [15:0] pr_a15 = 16'sd0;
    reg  signed [31:0] pr_m31 = 32'sd0;
    wire [15:0]       pr_out;
    wire              pr_ov;

    prelu_requantize #(.OUT_W(16), .OUT_SIGNED(1), .APPLY_PRELU(1)) u_pr (
        .clk(clk), .rst(rst), .in_valid(pr_v),
        .accumulator_int32(pr_acc), .prelu_q15(pr_a15), .multiplier_q31(pr_m31),
        .out_data(pr_out), .out_valid(pr_ov)
    );

    //-------------------------------------------------------------------------
    // (A5) channel_accumulator —— 加偏置 + 末级饱和
    //-------------------------------------------------------------------------
    reg               ca_dv = 1'b0;
    reg  signed [19:0] ca_dot = 20'sd0;
    reg  signed [31:0] ca_bias = 32'sd0;
    wire signed [31:0] ca_res;
    wire               ca_rv;

    channel_accumulator #(
        .DOT_W(20), .ACC_W(32), .CHANNELS(1)
    ) u_ca (
        .clk(clk), .rst(rst), .dot_valid(ca_dv), .dot_value(ca_dot),
        .bias(ca_bias), .result(ca_res), .result_valid(ca_rv)
    );

    //-------------------------------------------------------------------------
    // (B) 展开覆盖：其余 B 原语只实例化，不驱动
    //-------------------------------------------------------------------------
    localparam w_nil = 1'b0;

    wire signed [31:0] e_c1x1_res;  wire e_c1x1_v;
    conv1x1_backend u_e_c1x1 (
        .clk(clk), .rst(rst), .in_valid(w_nil),
        .x(8'sd0), .k(8'sd0), .bias(32'sd0),
        .result(e_c1x1_res), .result_valid(e_c1x1_v)
    );

    wire signed [31:0] e_c3x3_res;  wire e_c3x3_v;
    conv3x3_backend u_e_c3x3 (
        .clk(clk), .rst(rst), .in_valid(w_nil),
        .x00(8'sd0), .x01(8'sd0), .x02(8'sd0),
        .x10(8'sd0), .x11(8'sd0), .x12(8'sd0),
        .x20(8'sd0), .x21(8'sd0), .x22(8'sd0),
        .k00(8'sd0), .k01(8'sd0), .k02(8'sd0),
        .k10(8'sd0), .k11(8'sd0), .k12(8'sd0),
        .k20(8'sd0), .k21(8'sd0), .k22(8'sd0),
        .bias(32'sd0), .result(e_c3x3_res), .result_valid(e_c3x3_v)
    );

    wire signed [31:0] e_c5x5_res;  wire e_c5x5_v;
    conv5x5_backend u_e_c5x5 (
        .clk(clk), .rst(rst), .in_valid(w_nil),
        .x_flat(200'sd0), .k_flat(200'sd0), .bias(32'sd0),
        .result(e_c5x5_res), .result_valid(e_c5x5_v)
    );

    wire signed [31:0] e_c5x5u_res; wire e_c5x5u_v;
    conv5x5_u8s8_backend u_e_c5x5u (
        .clk(clk), .rst(rst), .in_valid(w_nil),
        .x_flat(200'd0), .k_flat(200'sd0), .bias(32'sd0),
        .result(e_c5x5u_res), .result_valid(e_c5x5u_v)
    );

    wire signed [20:0] e_d25;  wire e_d25v;
    dot25_pipeline u_e_d25 (
        .clk(clk), .rst(rst), .in_valid(w_nil),
        .x_flat(200'sd0), .k_flat(200'sd0), .dot25(e_d25), .dot25_valid(e_d25v)
    );

    wire signed [20:0] e_d25u; wire e_d25uv;
    dot25_u8s8_pipeline u_e_d25u (
        .clk(clk), .rst(rst), .in_valid(w_nil),
        .x_flat(200'd0), .k_flat(200'sd0), .dot25(e_d25u), .dot25_valid(e_d25uv)
    );

    wire signed [19:0] e_d9;   wire e_d9v;
    dot9_pipeline u_e_d9 (
        .clk(clk), .rst(rst), .in_valid(w_nil),
        .x00(8'sd0), .x01(8'sd0), .x02(8'sd0),
        .x10(8'sd0), .x11(8'sd0), .x12(8'sd0),
        .x20(8'sd0), .x21(8'sd0), .x22(8'sd0),
        .k00(8'sd0), .k01(8'sd0), .k02(8'sd0),
        .k10(8'sd0), .k11(8'sd0), .k12(8'sd0),
        .k20(8'sd0), .k21(8'sd0), .k22(8'sd0),
        .dot9(e_d9), .dot9_valid(e_d9v)
    );

    // ★ 2026-09-23 修正：B 的 sync_parameter_rom 在 `MEM_FILE == ""` 时会
    //   `$error("MEM_FILE must name a reviewed parameter file")`（见该文件 L20-22）。
    //   不指定 MEM_FILE 会在仿真日志里留下一条**假警报**，让「本 TB 全绿」的
    //   证据自带噪声。故这里显式绑定参数文件：
    //     · 路径是**相对 xsim 工作目录**的（工作目录 = _sim/<tb>，由 run_sim.tcl 保证，
    //       见该脚本「必须 cd 到本 TB 的工作目录」一节）；
    //     · DEPTH 取 4096 = 文件实际行数（若取小于行数会触发 $readmemh 的
    //       "too many data words" 警告，同样是噪声）。
    //   文件由 `_genparam.py` 以确定性 LCG 生成（无随机源，可复现）。
    localparam ROM_DEPTH = 4096;
    localparam ROM_MEM   = "../../rtl/b_real_bench_param.mem";

    reg [11:0] rom_addr = 12'd0;
    reg        rom_en   = 1'b0;
    wire [7:0] e_rom_d;
    sync_parameter_rom #(.DATA_W(8), .DEPTH(ROM_DEPTH), .MEM_FILE(ROM_MEM)) u_e_rom (
        .clk(clk), .enable(rom_en), .address(rom_addr), .data(e_rom_d)
    );

    wire [15:0] e_w3b00, e_w3b01, e_w3b02, e_w3b10, e_w3b11, e_w3b12, e_w3b20, e_w3b21, e_w3b22;
    wire e_w3bv;
    window3x3_bram #(.DATA_W(16), .IMG_W(64)) u_e_w3b (
        .clk(clk), .rst(rst), .pixel_in(16'd0), .pixel_valid(1'b0),
        .w00(e_w3b00), .w01(e_w3b01), .w02(e_w3b02),
        .w10(e_w3b10), .w11(e_w3b11), .w12(e_w3b12),
        .w20(e_w3b20), .w21(e_w3b21), .w22(e_w3b22),
        .window_valid(e_w3bv)
    );

    wire [7:0] e_w3s00, e_w3s01, e_w3s02, e_w3s10, e_w3s11, e_w3s12, e_w3s20, e_w3s21, e_w3s22;
    wire e_w3sv;
    window3x3_stream #(.DATA_W(8), .IMG_W(16)) u_e_w3s (
        .clk(clk), .rst(rst), .pixel_in(8'd0), .pixel_valid(1'b0),
        .w00(e_w3s00), .w01(e_w3s01), .w02(e_w3s02),
        .w10(e_w3s10), .w11(e_w3s11), .w12(e_w3s12),
        .w20(e_w3s20), .w21(e_w3s21), .w22(e_w3s22),
        .window_valid(e_w3sv)
    );

    wire [399:0] e_w5b;  wire e_w5bv;
    window5x5_bram #(.DATA_W(16), .IMG_W(64)) u_e_w5b (
        .clk(clk), .rst(rst), .pixel_in(16'd0), .pixel_valid(1'b0),
        .window_flat(e_w5b), .window_valid(e_w5bv)
    );

    wire [199:0] e_w5s;  wire e_w5sv;
    window5x5_stream #(.DATA_W(8), .IMG_W(16)) u_e_w5s (
        .clk(clk), .rst(rst), .pixel_in(8'd0), .pixel_valid(1'b0),
        .window_flat(e_w5s), .window_valid(e_w5sv)
    );

    //-------------------------------------------------------------------------
    // 轮询等待 valid。返回时已停在 negedge（NBA 已落定，可安全取值）。
    // ⚠️ 不能用「把 valid 当 task 入参」的写法：Verilog task 入参在进入时按值
    //    拷贝，会永远看到调用瞬间的电平。故每个信号各写一个专用 task。
    //-------------------------------------------------------------------------
    task wait_pr;
        input integer maxw;
        integer k;
        reg seen;
        begin
            seen = 1'b0;
            for (k = 0; k < maxw; k = k + 1) begin
                @(posedge clk);
                if (pr_ov === 1'b1) begin seen = 1'b1; k = maxw; end
            end
            if (!seen) begin
                fail_cnt = fail_cnt + 1;
                $display("[FAIL] timeout waiting pr_ov (t=%0t)", $time);
            end
            @(negedge clk);
        end
    endtask

    task wait_ca;
        input integer maxw;
        integer k;
        reg seen;
        begin
            seen = 1'b0;
            for (k = 0; k < maxw; k = k + 1) begin
                @(posedge clk);
                if (ca_rv === 1'b1) begin seen = 1'b1; k = maxw; end
            end
            if (!seen) begin
                fail_cnt = fail_cnt + 1;
                $display("[FAIL] timeout waiting ca_rv (t=%0t)", $time);
            end
            @(negedge clk);
        end
    endtask

    //-------------------------------------------------------------------------
    // 主流程
    //-------------------------------------------------------------------------
    reg signed [63:0] cap;

    // A6 sync_parameter_rom 的独立复算用
    integer i;
    reg [31:0] lx;
    reg [7:0]  exp_rom [0:7];

    initial begin
        $display("================================================================");
        $display(" C-side xsim :: REAL member-B primitives (not the C stub)");
        $display(" source = acx750-rtl @ 658c82e2  (see rtl/b_real/PROVENANCE.md)");
        $display("================================================================");

        rst = 1'b1;
        repeat (4) @(posedge clk);
        rst = 1'b0;
        @(negedge clk);

        //--------------------------------------------------------- A1 dsp_signed_mult
        // 驱动在负沿，下一负沿采样 → 恰好 1 拍延迟，且无竞态
        sm_en = 1'b1;
        @(negedge clk); sm_a = -8'sd128; sm_b = -8'sd128;
        @(negedge clk); cap = sm_p; chk_i("dsp_signed_mult (-128)*(-128)", cap, 64'sd16384);
        sm_a = 8'sd127; sm_b = 8'sd127;
        @(negedge clk); cap = sm_p; chk_i("dsp_signed_mult 127*127", cap, 64'sd16129);
        sm_a = -8'sd128; sm_b = 8'sd127;
        @(negedge clk); cap = sm_p; chk_i("dsp_signed_mult (-128)*127", cap, -64'sd16256);
        sm_a = -8'sd1; sm_b = 8'sd1;
        @(negedge clk); cap = sm_p; chk_i("dsp_signed_mult (-1)*1", cap, -64'sd1);
        sm_en = 1'b0;

        //--------------------------------------------------------- A2 dsp_u8s8_mult
        u8_en = 1'b1;
        @(negedge clk); u8_a = 8'd255; u8_b = -8'sd128;
        @(negedge clk); cap = u8_p; chk_i("dsp_u8s8_mult 255*(-128)", cap, -64'sd32640);
        u8_a = 8'd128; u8_b = -8'sd128;
        @(negedge clk); cap = u8_p; chk_i("dsp_u8s8_mult 128*(-128)", cap, -64'sd16384);
        u8_a = 8'd200; u8_b = 8'sd100;
        @(negedge clk); cap = u8_p; chk_i("dsp_u8s8_mult 200*100", cap, 64'sd20000);
        u8_a = 8'd0; u8_b = -8'sd128;
        @(negedge clk); cap = u8_p; chk_i("dsp_u8s8_mult 0*(-128)", cap, 64'sd0);
        u8_en = 1'b0;

        //--------------------------------------------------------- A3 pixel_shuffle（组合）
        ps_x = 10'd5; ps_y = 10'd7; ps_d = 8'hA5;
        ps_ph = 2'd0; #1;
        cap = ps_ox; chk_i("pixelshuffle phase0(TL) out_x", cap, 64'sd10);
        cap = ps_oy; chk_i("pixelshuffle phase0(TL) out_y", cap, 64'sd14);
        cap = ps_od; chk_i("pixelshuffle out_data passthru", cap, 64'shA5);
        ps_ph = 2'd1; #1;
        cap = ps_ox; chk_i("pixelshuffle phase1(TR) out_x", cap, 64'sd11);
        cap = ps_oy; chk_i("pixelshuffle phase1(TR) out_y", cap, 64'sd14);
        ps_ph = 2'd2; #1;
        cap = ps_ox; chk_i("pixelshuffle phase2(BL) out_x", cap, 64'sd10);
        cap = ps_oy; chk_i("pixelshuffle phase2(BL) out_y", cap, 64'sd15);
        ps_ph = 2'd3; #1;
        cap = ps_ox; chk_i("pixelshuffle phase3(BR) out_x", cap, 64'sd11);
        cap = ps_oy; chk_i("pixelshuffle phase3(BR) out_y", cap, 64'sd15);

        //--------------------------------------------------------- A4 prelu_requantize
        // (1) 负累加走 PReLU：acc=-100, alpha_q15=-16384(-0.5) -> 50 ; *0.5(2^30) -> 25
        @(negedge clk);
        pr_acc = -32'sd100; pr_a15 = -16'sd16384; pr_m31 = 32'sd1073741824; pr_v = 1'b1;
        @(negedge clk); pr_v = 1'b0;         // 保持整拍，正沿已采到
        wait_pr(10);
        cap = {{48{pr_out[15]}}, pr_out};
        chk_i("prelu_requantize neg acc=-100 a=-0.5 m=0.5", cap, 64'sd25);

        // (2) acc=-3, alpha=-32768(-1.0) -> 3 ; multiplier ~1.0 -> 3
        @(negedge clk);
        pr_acc = -32'sd3; pr_a15 = -16'sd32768; pr_m31 = 32'sd2147483647; pr_v = 1'b1;
        @(negedge clk); pr_v = 1'b0;
        wait_pr(10);
        cap = {{48{pr_out[15]}}, pr_out};
        chk_i("prelu_requantize neg acc=-3 a=-1.0 m=~1.0", cap, 64'sd3);

        // (3) 正累加不经过 PReLU：acc=1000 * 0.5 = 500
        @(negedge clk);
        pr_acc = 32'sd1000; pr_a15 = -16'sd16384; pr_m31 = 32'sd1073741824; pr_v = 1'b1;
        @(negedge clk); pr_v = 1'b0;
        wait_pr(10);
        cap = {{48{pr_out[15]}}, pr_out};
        chk_i("prelu_requantize pos acc=1000 m=0.5", cap, 64'sd500);

        //--------------------------------------------------------- A5 channel_accumulator
        @(negedge clk);
        ca_dot = 20'sd5; ca_bias = 32'sd10; ca_dv = 1'b1;
        @(negedge clk); ca_dv = 1'b0;
        wait_ca(10);
        cap = {{32{ca_res[31]}}, ca_res};
        chk_i("channel_accumulator 5+10", cap, 64'sd15);

        @(negedge clk);
        ca_dot = -20'sd5; ca_bias = 32'sd0; ca_dv = 1'b1;
        @(negedge clk); ca_dv = 1'b0;
        wait_ca(10);
        cap = {{32{ca_res[31]}}, ca_res};
        chk_i("channel_accumulator -5+0", cap, -64'sd5);

        //--------------------------------------------------------- A6 sync_parameter_rom
        // 独立复算：TB 内以**同一确定性 LCG**重算前 8 个地址的期望值，
        // 再与 DUT 的同步读输出逐值比对。
        //   x_{n+1} = (1103515245 * x_n + 12345) mod 2^32 ,  x_0 = 0x12345678
        //   mem[n]  = x_{n+1}[23:16]      （与 _genparam.py 的 (x>>16)&0xFF 一致）
        // 同步读延迟 1 拍：负沿给地址 → 中间正沿锁存 → 下一负沿取值。
        lx = 32'h12345678;
        for (i = 0; i < 8; i = i + 1) begin
            lx = (32'd1103515245 * lx) + 32'd12345;
            exp_rom[i] = lx[23:16];
        end
        rom_en = 1'b1;
        for (i = 0; i < 8; i = i + 1) begin
            @(negedge clk); rom_addr = i[11:0];
            @(negedge clk); cap = {56'd0, e_rom_d};
            chk_i("sync_parameter_rom mem[0..7] LCG", cap, {56'd0, exp_rom[i]});
        end
        rom_en = 1'b0;

        //--------------------------------------------------------- 汇总
        $display("----------------------------------------------------------------");
        $display(" checks: pass=%0d fail=%0d", pass_cnt, fail_cnt);
        $display(" elaborated B primitives: 17/17 instantiated");
        $display(" NOTE: five-layer network / scheduler / padding / 30fps NOT covered");
        $display("----------------------------------------------------------------");
        if (fail_cnt == 0) begin
            $display("RESULT: PASS");
            $display("ACX750_C_SIDE_B_REAL_PRIMITIVES_PASS");
        end else begin
            $display("RESULT: FAIL");
            $display("ACX750_C_SIDE_B_REAL_PRIMITIVES_FAIL");
        end
        $display("================================================================");
        $finish;
    end

    // 硬超时：绝不无界运行
    initial begin
        #200000;
        $display("[FAIL] HARD TIMEOUT");
        $display("ACX750_C_SIDE_B_REAL_PRIMITIVES_FAIL");
        $finish;
    end

endmodule
