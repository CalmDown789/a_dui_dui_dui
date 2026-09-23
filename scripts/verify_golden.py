#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_golden.py -- A 侧全尺寸整数 Golden 复核（可复现，任何人可跑）

用途
----
对 c_side/ref/a_full_integer_golden/ 的留档做**独立复核**，三件事：
  1) 逐文件对同目录 SHA256SUMS.txt 校验（哈希 + 字节数）
  2) 把 A 自己的 manifest.json -> files{} 段与 SHA256SUMS.txt 交叉核对
  3) 校验文本类产物 quant_params.json 的「LF 归一」口径
     （★ 行尾不归一会误判 —— 见 docs/ACCEPTANCE_DATA_DEPENDENCY.md §3.2）

用法
----
  python scripts/verify_golden.py
  python scripts/verify_golden.py --ref <golden_dir> --quant <quant_params.json>

退出码
------
  0 = 全部通过
  1 = 存在不一致（会逐条打印）
  2 = 前置条件缺失（目录/文件找不到）

依据
----
  docs/ACCEPTANCE_DATA_DEPENDENCY.md  §二 / §3.2 / §5
"""

import argparse
import hashlib
import json
import os
import sys
import zlib

# ★ 本脚本会打印中文。Windows 下若 stdout 走本地码页（cp936/GBK），
#   重定向到文件时中文会变乱码。这里强制 UTF-8，保证 `> out.txt` 也可读。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

DEFAULT_REF = os.path.join(REPO, "ref", "a_full_integer_golden")
DEFAULT_QUANT = os.path.join(REPO, "ref", "a_full_integer_golden", "quant_params.json")

# A 的 manifest.json 对 quant_params.json 的声明（LF 口径）
EXPECT_QUANT = {
    "bytes": 13029,
    "sha256": "f2a9f20ca6d51f4f2902e6e1b5e6bdb7632f62981930101b0aaeb0994351b77a",
    "crc32": "0a1303ff",
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_sums(path):
    """SHA256SUMS.txt -> {name: (sha256, bytes)}"""
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = ln.split()
            if len(parts) < 3:
                continue
            out[parts[2].lstrip("*")] = (parts[0].lower(), int(parts[1]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=DEFAULT_REF, help="Golden 留档目录")
    ap.add_argument("--quant", default=None,
                    help="quant_params.json 路径（默认在留档目录内；若留档目录不含，"
                         "可用 --quant 指向 A 仓库副本）")
    args = ap.parse_args()

    ref = args.ref
    if not os.path.isdir(ref):
        print("ERROR: ref dir not found: %s" % ref)
        return 2

    print("=" * 78)
    print(" 1) SHA256SUMS.txt 逐文件复核")
    print("=" * 78)
    sumfile = os.path.join(ref, "SHA256SUMS.txt")
    if not os.path.isfile(sumfile):
        print("ERROR: SHA256SUMS.txt not found in %s" % ref)
        return 2

    sums = read_sums(sumfile)
    ok = bad = 0
    fails = []
    for name in sorted(sums):
        exp_hash, exp_bytes = sums[name]
        p = os.path.join(ref, name)
        if not os.path.isfile(p):
            print("  MISSING  %-42s (期望 %d B)" % (name, exp_bytes))
            bad += 1
            fails.append(name)
            continue
        got_bytes = os.path.getsize(p)
        got_hash = sha256_of(p)
        if got_hash == exp_hash and got_bytes == exp_bytes:
            print("  OK       %-42s %9d" % (name, got_bytes))
            ok += 1
        else:
            print("  MISMATCH %-42s" % name)
            print("           期望 %s / %d" % (exp_hash, exp_bytes))
            print("           实得 %s / %d" % (got_hash, got_bytes))
            bad += 1
            fails.append(name)
    print("  -> OK=%d  BAD=%d  (清单共 %d 项)" % (ok, bad, len(sums)))
    print()

    print("=" * 78)
    print(" 2) manifest.json files{} 交叉核对")
    print("=" * 78)
    mf_path = os.path.join(ref, "manifest.json")
    if os.path.isfile(mf_path):
        mf = json.load(open(mf_path, "r", encoding="utf-8"))
        print("  status       : %s" % mf.get("status"))
        print("  golden_class : %s" % mf.get("golden_class"))
        print("  auth output  : %s" % mf.get("authoritative_output"))
        mfiles = mf.get("files", {})
        for name in sorted(mfiles):
            e = mfiles[name]
            if name in sums:
                same = (sums[name][0] == e["sha256"] and sums[name][1] == e["bytes"])
                print("  %-42s manifest==sums : %s" % (name, "YES" if same else "NO"))
                if not same:
                    fails.append("manifest:" + name)
            else:
                print("  %-42s (not in SHA256SUMS)" % name)
        extra = sorted(set(sums) - set(mfiles))
        print("  SHA256SUMS 有而 manifest.files 无 : %s" % (extra if extra else "(none)"))
    else:
        print("  (manifest.json 不在留档目录内，跳过)")
    print()

    print("=" * 78)
    print(" 3) quant_params.json 行尾口径复核")
    print("=" * 78)
    q = args.quant or DEFAULT_QUANT
    if not os.path.isfile(q):
        print("  SKIP: 未找到 %s" % q)
        print("        （留档目录通常不含该文件；可 --quant 指向 A 仓库副本）")
        print("        期望口径 : bytes=%d sha256=%s" % (EXPECT_QUANT["bytes"], EXPECT_QUANT["sha256"]))
    else:
        raw = open(q, "rb").read()
        lf = raw.replace(b"\r\n", b"\n")
        print("  文件            : %s" % q)
        print("  原始形态        : bytes=%d sha256=%s" % (len(raw), hashlib.sha256(raw).hexdigest()))
        print("  LF 归一后       : bytes=%d sha256=%s" % (len(lf), hashlib.sha256(lf).hexdigest()))
        print("  LF 归一后 crc32 : %08x" % (zlib.crc32(lf) & 0xFFFFFFFF))
        hit_bytes = (len(lf) == EXPECT_QUANT["bytes"])
        hit_sha = (hashlib.sha256(lf).hexdigest() == EXPECT_QUANT["sha256"])
        hit_crc = ("%08x" % (zlib.crc32(lf) & 0xFFFFFFFF)) == EXPECT_QUANT["crc32"]
        print("  >>> LF 口径三项 : bytes=%s sha256=%s crc32=%s" % (hit_bytes, hit_sha, hit_crc))
        if not (hit_bytes and hit_sha and hit_crc):
            fails.append("quant_params.json")
    print()

    print("=" * 78)
    if fails:
        print(" 结果: FAIL  不一致项 = %s" % sorted(set(fails)))
        print(" ！立即停用该留档，按 docs/ACCEPTANCE_DATA_DEPENDENCY.md §六 上报。")
        print("=" * 78)
        return 1
    print(" 结果: PASS  Golden 留档与 A 的清单/manifest 完全一致。")
    print(" 注意: 这不等于「C 类 Golden 已定版」—— 权威性待 A 书面确认（A-G-1）。")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
