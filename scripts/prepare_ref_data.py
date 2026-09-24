#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_ref_data.py —— 把「验收用的只读参考数据」整理成 TB 可直接 $readmemh 的形式

职责（只做搬运 + 校验 + 格式转换，**不产生任何数值**）：
  1. 从 A 仓库本地副本取 `artifacts/test_vectors/<case>/` 的
       input_y_u8.bin        (5184 B  = 96x54x1 uint8)   —— 96x54 输入
       output_hwc_uint8.bin  (20736 B = 108x192x1 uint8) —— PixelShuffle **之后**的最终输出
       manifest.json                                      —— 逐文件 SHA-256（权威校验源）
     逐文件校验 SHA-256 与 manifest 一致后，落到 c_side/ref/a_test_vectors/<case>/。
  2. 校验 c_side/ref/a_full_integer_golden/ 的两个关键文件对 SHA256SUMS.txt 一致。
  3. 生成 c_side/ref/_staged_mem/（**供 run_sim.tcl 逐 TB 复制到仿真工作目录**）：
       tv_<case>_in.mem   / tv_<case>_out.mem     (4 组 96x54 用例)
       full_in.mem        (960x540 = 518400 行，取自 input_rom_2p19_u8.mem 的前 N 行)
       full_out.mem       (1920x1080 = 2073600 行，由 output_1920x1080_y_u8.bin 转)
     .mem 格式 = 每行一个两位十六进制字节（小写），与 B 的参数 ROM 同格式。

为什么要有 _staged_mem 这一步：真实核用**裸文件名** $readmemh，相对路径按**进程 CWD**
解析；本工程 xsim 的 CWD = 各 TB 的工作目录。run_sim.tcl 的 stage_ref_data 负责复制。

用法：
  <python> scripts/prepare_ref_data.py [--a-repo <A仓库路径>]
输出：全部写入 stdout（供先 Out-File 再读），非零退出码表示校验失败。
"""

import argparse
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
C_SIDE = os.path.normpath(os.path.join(HERE, ".."))
REF = os.path.join(C_SIDE, "ref")
TV_DIR = os.path.join(REF, "a_test_vectors")
GOLD_DIR = os.path.join(REF, "a_full_integer_golden")
STAGE = os.path.join(REF, "_staged_mem")

CASES = ["impulse", "ramp", "random", "zero"]

FULL_IN_PIX = 960 * 540          # 518400
FULL_OUT_PIX = 1920 * 1080       # 2073600
TV_IN_PIX = 96 * 54              # 5184
TV_OUT_PIX = 192 * 108           # 20736

problems = []


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log(*a):
    print(*a)


def check(cond, msg):
    if not cond:
        problems.append(msg)
        log("  !! FAIL  " + msg)
    return cond


def bin_to_mem(bin_path, mem_path, nbytes, label):
    """裸二进制 -> 每行一个两位十六进制字节的 .mem"""
    data = open(bin_path, "rb").read()
    check(len(data) == nbytes,
          "%s size %d != expected %d" % (bin_path, len(data), nbytes))
    if len(data) > nbytes:
        data = data[:nbytes]
    with open(mem_path, "w", newline="\n") as f:
        f.write("\n".join("%02x" % b for b in data))
        f.write("\n")
    log("  wrote %-46s %8d lines  (%s)" % (os.path.relpath(mem_path, C_SIDE),
                                           len(data), label))
    return len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-repo", default=C_SIDE,
                    help="A 仓库本地工作副本路径")
    args = ap.parse_args()

    a_tv = os.path.join(args.a_repo, "artifacts", "test_vectors")
    log("=" * 78)
    log("prepare_ref_data.py   A repo test_vectors = " + a_tv)
    log("=" * 78)

    if not os.path.isdir(a_tv):
        log("!! A test_vectors not found: " + a_tv)
        return 2

    os.makedirs(STAGE, exist_ok=True)

    # ------------------------------------------------------------------ 1
    log("\n[1] 96x54 用例：校验 manifest SHA-256 后落地 ref/a_test_vectors/<case>/")
    sums_lines = []
    for case in CASES:
        src = os.path.join(a_tv, case)
        mf = os.path.join(src, "manifest.json")
        if not check(os.path.isfile(mf), "missing manifest: " + mf):
            continue
        man = json.load(open(mf, encoding="utf-8"))
        dst = os.path.join(TV_DIR, case)
        os.makedirs(dst, exist_ok=True)
        shutil.copy2(mf, os.path.join(dst, "manifest.json"))
        log("  case %s  (layout=%s)" % (case, man.get("layout")))
        for fn, want_bytes in (("input_y_u8.bin", TV_IN_PIX),
                               ("output_hwc_uint8.bin", TV_OUT_PIX)):
            s = os.path.join(src, fn)
            if not check(os.path.isfile(s), "missing %s" % s):
                continue
            # 与 manifest 对账
            ent = man.get("files", {}).get(fn)
            if ent is None:
                check(False, "%s not listed in manifest" % fn)
            else:
                if ent.get("bytes") is not None:
                    check(os.path.getsize(s) == ent["bytes"],
                          "%s/%s size %d != manifest %d" % (
                              case, fn, os.path.getsize(s), ent["bytes"]))
            got = sha256(s)
            if ent and ent.get("sha256"):
                check(got == ent["sha256"],
                      "%s/%s sha256 %s != manifest %s" % (case, fn, got, ent["sha256"]))
            shutil.copy2(s, os.path.join(dst, fn))
            sums_lines.append("%s  %8d  a_test_vectors/%s/%s"
                              % (got, os.path.getsize(s), case, fn))
            log("      %-26s len=%7d  sha256=%s  OK" % (fn, os.path.getsize(s), got[:16]))

        # 生成 .mem
        bin_to_mem(os.path.join(dst, "input_y_u8.bin"),
                   os.path.join(STAGE, "tv_%s_in.mem" % case), TV_IN_PIX,
                   "96x54 u8 input raster")
        bin_to_mem(os.path.join(dst, "output_hwc_uint8.bin"),
                   os.path.join(STAGE, "tv_%s_out.mem" % case), TV_OUT_PIX,
                   "192x108 u8 final output")

    with open(os.path.join(TV_DIR, "SHA256SUMS.txt"), "w", newline="\n",
              encoding="utf-8") as f:
        f.write("# A 96x54 整数用例 (artifacts/test_vectors/) —— 逐文件 SHA-256\n")
        f.write("# 来源: CalmDown789/a_dui_dui_dui  artifacts/test_vectors/\n")
        f.write("# 校验源: 各 case 的 manifest.json (files.*.sha256)\n")
        f.write("\n".join(sums_lines) + "\n")
    log("  -> ref/a_test_vectors/SHA256SUMS.txt (%d 项)" % len(sums_lines))

    # ------------------------------------------------------------------ 2
    log("\n[2] 全尺寸 Golden：对 c_side/ref/a_full_integer_golden/SHA256SUMS.txt 对账")
    gold_sums = {}
    sp = os.path.join(GOLD_DIR, "SHA256SUMS.txt")
    if check(os.path.isfile(sp), "missing " + sp):
        for line in open(sp, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                gold_sums[parts[2]] = (parts[0], int(parts[1]))
    for fn in ("input_rom_2p19_u8.mem", "output_1920x1080_y_u8.bin", "input_rom_2p19_u8.bin"):
        p = os.path.join(GOLD_DIR, fn)
        if not check(os.path.isfile(p), "missing " + p):
            continue
        got = sha256(p)
        if fn in gold_sums:
            exp, expsz = gold_sums[fn]
            check(got == exp, "%s sha256 %s != %s" % (fn, got, exp))
            check(os.path.getsize(p) == expsz,
                  "%s size %d != %d" % (fn, os.path.getsize(p), expsz))
        log("      %-30s len=%9d  sha256=%s" % (fn, os.path.getsize(p), got[:16]))

    # ------------------------------------------------------------------ 3
    log("\n[3] 生成 ref/_staged_mem/full_in.mem 与 full_out.mem")
    mem_in = os.path.join(GOLD_DIR, "input_rom_2p19_u8.mem")
    if os.path.isfile(mem_in):
        lines = open(mem_in, encoding="utf-8").read().splitlines()
        check(len(lines) >= FULL_IN_PIX,
              "full input rom has %d lines < %d needed" % (len(lines), FULL_IN_PIX))
        with open(os.path.join(STAGE, "full_in.mem"), "w", newline="\n") as f:
            f.write("\n".join(lines[:FULL_IN_PIX]))
            f.write("\n")
        log("  wrote %-46s %8d lines  (960x540 u8, zero-padded rom truncated)"
            % ("ref/_staged_mem/full_in.mem", FULL_IN_PIX))

    bin_out = os.path.join(GOLD_DIR, "output_1920x1080_y_u8.bin")
    if os.path.isfile(bin_out):
        bin_to_mem(bin_out, os.path.join(STAGE, "full_out.mem"), FULL_OUT_PIX,
                   "1920x1080 u8 integer Golden (final)")

    # ------------------------------------------------------------------ 4
    log("\n[4] 目录清单")
    tot = 0
    for fn in sorted(os.listdir(STAGE)):
        p = os.path.join(STAGE, fn)
        sz = os.path.getsize(p)
        tot += sz
        log("      %-28s %10d B" % (fn, sz))
    log("      %-28s %10d B" % ("TOTAL", tot))

    log("\n" + "=" * 78)
    if problems:
        log("RESULT: FAIL  (%d problems)" % len(problems))
        for p in problems:
            log("  - " + p)
        return 1
    log("RESULT: PASS  (ref data verified + staged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
