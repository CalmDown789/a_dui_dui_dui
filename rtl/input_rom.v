//=============================================================================
// input_rom.v —— 输入图 ROM（960×540 uint8 → 2^19 深、8 bit 宽）
//-----------------------------------------------------------------------------
// 依据：v3.2.2 §五.9（2）「输入 ROM 读接口与地址语义」
//   · 存储体      ：单端口 BRAM-ROM，$readmemh 初始化的 .mem
//   · 深度        ：518400 像素；按 2 的幂填充到 524288（差额 5888 B ≈ 5.75 KiB）
//   · 地址位宽    ：19 bit（rom_addr[18:0]）
//   · 地址语义    ：rom_addr = y*960 + x（行主序）；地址 0 = 左上角 (0,0)
//   · 未用地址    ：518400 ~ 524287 定义为 0x00（便于自检比对）
//   · 读时序      ：同步读，rom_en 有效后 1 拍输出 rom_dout
//   · 端口        ：rom_en / rom_addr[18:0] / rom_dout[7:0]
//
// 本模块是「单端口同步读」BRAM 的标准可推断写法：
//   · 读地址进、读数据出，**中间不插组合逻辑**（Vivado RAMB 推断的关键条件）；
//   · 无复位（BRAM 不做复位），符合 UG901 的推断模板；
//   · (* ram_style = "block" *) 明确要求用 BRAM 而不是 LUTRAM。
//
// 初始化两路（互斥，INIT_MODE 选择）：
//   INIT_MODE = 0：全零填充 + 可选 $readmemh(INIT_FILE)   ← **综合/上板默认**
//   INIT_MODE = 1：确定性公式填充（SIM ONLY）              ← 供无数据文件的仿真
//
// TODO(A_CONFIRM): 全尺寸 960×540 真实图像 .mem 属 A 侧交付物；
//                  本工程仅生成 tiny .mem（小规模 TB 用），见 scripts/gen_input_mem.py。
//=============================================================================

`timescale 1ns / 1ps
`default_nettype none

`include "c_config.vh"

module input_rom #(
    parameter integer ADDR_W     = `C_ROM_ADDR_W,        // 19
    parameter integer DATA_W     = `C_PIXEL_W,           // 8
    parameter integer MEM_DEPTH  = `C_ROM_DEPTH_POW2,    // 524288
    //--- 初始化控制 ---------------------------------------------------------
    parameter integer INIT_MODE  = 0,     // 0=零填充(+readmemh) 1=公式填充(SIM ONLY)
    parameter integer INIT_EN    = 0,     // INIT_MODE=0 时是否执行 $readmemh
    parameter         INIT_FILE  = ""     // $readmemh 的文件路径
) (
    input  wire              clk,
    input  wire              en,          // 读使能
    input  wire [ADDR_W-1:0] addr,        // = y*IMG_W + x
    output reg  [DATA_W-1:0] dout         // en 有效后 1 拍有效
);

    //-------------------------------------------------------------------------
    // 存储体：单端口同步读。写法刻意保持「无复位、无组合旁路」以利 BRAM 推断。
    //-------------------------------------------------------------------------
    (* ram_style = "block" *) reg [DATA_W-1:0] mem [0:MEM_DEPTH-1];

    //-------------------------------------------------------------------------
    // 初始化
    //
    // ★ 关键（第一版踩过）：**绝不要用无界 for 循环写整片 ROM 的初值**。
    //   综合器对 initial 块内的循环有 **65536 次迭代上限**，超限时整块
    //   initial 被**忽略**（实测 WARNING [Synth 8-6896]），于是
    //   ① 综合出来的 ROM 无初值；② BRAM 统计不可信（实测只报了 16 块 RAMB36，
    //   而 524288×8 实际需要约 114 块）。
    //
    //   正确做法（本版）：
    //     · 综合 / 上板：`INIT_MODE=0, INIT_EN=1` → `$readmemh(INIT_FILE, mem)`，
    //       Vivado 原生支持用 $readmemh 初始化 BRAM（不受循环上限影响）；
    //     · 仿真：`INIT_MODE=1` → 公式 pattern，**且整段包在 `ifdef C_SIM 内**，
    //       保证永远不会进入综合路径。
    //-------------------------------------------------------------------------
    integer i;

`ifdef C_SIM
    // ============ SIM ONLY：确定性 pattern 初值 ============
    //   pattern(addr) = (addr*7 + (addr>>8) + 13) & 0xFF
    //   供 TB 独立复算期望值；**仅供仿真**（综合时不编译本段）。
    initial begin
        if (INIT_MODE == 1) begin
            for (i = 0; i < MEM_DEPTH; i = i + 1) begin
                mem[i] = ((i * 7) + (i >> 8) + 13) & 8'hFF;
            end
        end
    end
`endif

    // ============ 真实数据装载（综合 / 上板路径） ============
    //   未覆盖的地址由 BRAM 默认初值 = 0x00 填充
    //   （§五.9（2）：518400 ~ 524287 定义为 0x00）
    initial begin
        if ((INIT_MODE == 0) && (INIT_EN != 0)) begin
            $readmemh(INIT_FILE, mem);
        end
    end

    //-------------------------------------------------------------------------
    // 读通路（同步读，1 拍延迟）—— §五.9（2）「读时序」
    //-------------------------------------------------------------------------
    always @(posedge clk) begin
        if (en) begin
            dout <= mem[addr];
        end
    end

endmodule

`default_nettype wire
