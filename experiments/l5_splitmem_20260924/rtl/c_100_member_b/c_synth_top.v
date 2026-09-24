// 成员B工作：100 MHz fallback clock and 100 ms auto-start; copied from c-side-latest@6b87af3.
//=============================================================================
// c_synth_top.v —— 综合（synthesis）专用顶层
//-----------------------------------------------------------------------------
// 用途：把「综合意图参数」从板级顶层 `c_top.v` 里分离出来，使
//       · `c_top.v` 保持「上板默认值」（ROM_INIT_MODE=0，等待真实 .mem）；
//       · 综合 / 资源报告使用本文件作为 `-top`（C17 / C9 的证据包入口）。
//
// ★ 为什么要单独一个顶层：
//   `input_rom` 在 `ROM_INIT_MODE=0 / INIT_EN=0` 时是**全零常量**，
//   综合器会把它常量折叠掉 → BRAM 不被推断 → utilization 报告会**低报**。
//   本顶层改用 `ROM_INIT_MODE=1`（确定性 pattern 初值，仅用于让 ROM 成为
//   真实存储体），从而得到**有意义的 BRAM block 数**。
//
//   ⚠️ 这不是「造数据」：真实上板时 ROM 由 `$readmemh` 装载真实图像
//   （`ROM_INIT_MODE=0, INIT_EN=1`），其**深度与位宽完全相同**
//   （2^19 深 × 8 bit），因此 BRAM block 数不会改变。
//
//   此顶层也可供实现取证；是否 place/route 由调用脚本决定，均不生成 bitstream。
//
// 依据：v3.2.2 §8.3 C9/C11/C17、§九 门槛 5、§五.2 分层表（A 层 KiB 预算 / B 层 block utilization）
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module c_synth_top (
    input  wire       sys_clk,      // 板载 50MHz → W19（见 constr/c_top.xdc）
    input  wire       rst_n,        // 按键 S0 → D21，按下为低
    output wire [7:0] led,
    output wire       uart_tx
);

    c_top #(
        //--- 几何（v3.2.2 §五.9 / §五.8） ------------------------------------
        .IMG_W          (`C_IMG_W),        // 960
        .IMG_H          (`C_IMG_H),        // 540
        .OUT_W          (`C_OUT_W),        // 1920
        .OUT_H          (`C_OUT_H),        // 1080
        .STRIPE_H       (`C_STRIPE_H),     // 64（当前基线，非冻结项）
        .PIXEL_W        (`C_PIXEL_W),      // 8
        //--- 输入 ROM：用真实 $readmemh 装载（综合路径） --------------------
        //   ⚠️ 不要用 `ROM_INIT_MODE=1` 的公式 pattern 走综合：
        //      · 综合器忽略 >65536 次迭代的 initial 循环（Synth 8-6896），
        //        公式初值根本不会生效；
        //      · 结果是无初值的 ROM，BRAM 推断/统计失真（实测只报 16 块 RAMB36）。
        //   ⇒ 生成 .mem 后再综合：
        //        python scripts/gen_input_mem.py pattern-full
        //      （该文件约 1.6 MB，已被 .gitignore 忽略）
        //   A 的真实 960×540 输入 ROM 已在 ref/a_full_integer_golden/ 留档。
        //   本取证顶层仍用同深度/位宽的 pattern；上板前须换为 A 的已校验 .mem。
        .ROM_ADDR_W     (`C_ROM_ADDR_W),    // 19
        .ROM_DEPTH      (`C_ROM_DEPTH_POW2),// 524288
        .ROM_INIT_MODE  (0),                // 0 = 零填充 + $readmemh
        .ROM_INIT_EN    (1),                // ★ 打开 $readmemh
        .ROM_INIT_FILE  ("rtl/input_image_pattern.mem"),
        //--- 时钟（v3.2.2 §五.4，已上板实测配置） ---------------------------
        .USE_MMCM       (1),
        .CLK_HZ         (100000000),       // 100 MHz
        //--- UART（v3.2.2 §五.7） -------------------------------------------
        .UART_BAUD      (`C_UART_BAUD),    // 921600
        .RB_ENABLE      (1),
        //--- 板级冒烟自动启动（真实 start 触发源尚未冻结） ------------------
        .AUTO_START_EN  (1),
        .AUTO_START_CYCLES (10_000_000)    // @100MHz ≈ 100 ms
    ) u_top (
        .sys_clk (sys_clk),
        .rst_n   (rst_n),
        .led     (led),
        .uart_tx (uart_tx)
    );

endmodule

`default_nettype wire
