#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_input_mem.py —— 生成输入 ROM 的 $readmemh 初始化文件

用途（两种，互不冲突）：

  1) pattern-full  **仅用于综合取证**：
       524288 行 = 2^19，值与 `input_rom.v` 的仿真 pattern 一致：
           v(i) = (i*7 + (i>>8) + 13) & 0xFF   , i <  518400
           v(i) = 0x00                          , i >= 518400   (§五.9(2) 填充区)
       为什么综合也要给初值：若 ROM 无任何初值，Vivado 的 BRAM 推断与
       utilization 统计会失真（实测只报 16 块 RAMB36，而 524288×8 实际
       需要约 114 块）。**这不是"造数据"**——真实上板时换成 A 交付的真实
       图像 .mem，深度与位宽完全相同，BRAM block 数不变。

  2) zeros  **等价于"上电全 0"**，仅用于对照。

⚠️ 生成的 pattern-full 文件约 1.6 MB，**不入库**（见 .gitignore 的
   `rtl/input_image_*.mem`）。真实图像 .mem 属 **A 侧交付物**
   （TODO(A_CONFIRM)），到位后直接替换即可。

用法：
    python scripts/gen_input_mem.py pattern-full
    python scripts/gen_input_mem.py zeros
    python scripts/gen_input_mem.py pattern-full --out rtl/input_image_pattern.mem
"""

import argparse
import os
import sys

IMG_W, IMG_H = 960, 540
ROM_DEPTH = 1 << 19          # 524288（2^19，§五.9(2)）
VALID = IMG_W * IMG_H        # 518400


def value(i: int) -> int:
    return (i * 7 + (i >> 8) + 13) & 0xFF


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["pattern-full", "zeros"])
    ap.add_argument("--out", default=None, help="输出路径")
    ap.add_argument("--depth", type=int, default=ROM_DEPTH)
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = args.out or os.path.join(
        root, "rtl",
        "input_image_pattern.mem" if args.mode == "pattern-full" else "input_image_zeros.mem")
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    n = args.depth
    with open(out, "w", newline="\n") as f:
        if args.mode == "pattern-full":
            for i in range(n):
                f.write("%02X\n" % (value(i) if i < VALID else 0))
        else:
            for _ in range(n):
                f.write("00\n")

    size = os.path.getsize(out)
    print("wrote %s : %d lines, %d bytes (%.2f MB)" % (out, n, size, size / 1048576.0))
    if args.mode == "pattern-full":
        print("  NOTE: 这是**测试 pattern**，不是真实图像；"
              "真实 960x540 图像 .mem 属 A 侧交付物（TODO(A_CONFIRM)）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
