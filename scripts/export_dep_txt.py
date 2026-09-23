#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_dep_txt.py —— 把 docs/DEPENDENCIES_A_B.md 导出为纯文本清单

为什么要脚本而不是手工另存：
  · Markdown 表格在纯文本里会因为**中日韩宽字符**（全角）而完全错位，
    必须按 east_asian_width 计算显示宽度再对齐；
  · 部分单元格很长，需要按列宽**折行**，否则一行 300+ 字符没法读；
  · 需要把 Markdown 记号（** / ` / 链接 / emoji 图例）转成纯文本记号，
    并保证可重复生成（内容更新后重跑即可）。

用法：
    python scripts/export_dep_txt.py
    python scripts/export_dep_txt.py --width 120 --in docs/DEPENDENCIES_A_B.md \
                                            --out docs/DEPENDENCIES_A_B.txt

输出：UTF-8、LF、无 BOM（Windows 记事本 / VS Code / 邮件均可正常显示）
"""

import argparse
import os
import re
import sys
import unicodedata

# --------------------------------------------------------------------------
# 显示宽度（CJK 全角算 2 列）
# --------------------------------------------------------------------------
def cw(ch: str) -> int:
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def dw(s: str) -> int:
    return sum(cw(c) for c in s)


def pad(s: str, width: int) -> str:
    d = dw(s)
    return s + " " * max(0, width - d)


# --------------------------------------------------------------------------
# 折行：按显示宽度换行；英文单词尽量不切断
# --------------------------------------------------------------------------
WORDCH = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./\\:")
# 这些字符不能出现在折行后的行首（否则中文排版很难看）
NO_START = set("，。；：、）」』】》！？%")


def wrap(s: str, width: int) -> list:
    if width <= 0:
        return [s]
    if s == "":
        return [""]
    lines, cur, curw = [], "", 0
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        c = cw(ch)
        if curw + c > width and cur:
            # 标点不允许落到行首：让它跟着上一行（允许轻微超宽）
            if ch in NO_START:
                lines.append((cur + ch).rstrip())
                cur, curw = "", 0
                i += 1
                continue
            # 尝试回退到最近的分隔符，避免把英文单词/路径切开
            cut = len(cur)
            if ch in WORDCH and cur and cur[-1] in WORDCH:
                j = cut
                while j > 0 and cur[j - 1] not in " \t/":
                    j -= 1
                if j > 0:
                    lines.append(cur[:j].rstrip())
                    cur = cur[j:]
                    curw = dw(cur)
                    continue
            lines.append(cur.rstrip())
            cur, curw = "", 0
            continue
        cur += ch
        curw += c
        i += 1
    lines.append(cur.rstrip())
    return lines if lines else [""]


# --------------------------------------------------------------------------
# Markdown 记号 → 纯文本
# --------------------------------------------------------------------------
EMOJI_MAP = {
    "🟥": "[阻塞]",
    "🟨": "[影响结论]",
    "🟩": "[可自推进]",
    "📋": "",
    "✅": "[x]",
    "⬜": "[ ]",
}
# 说明：只替换 emoji 与 U+2212。≈ ≤ ≥ ± × → ⇒ 与制表符一律保留原字符 ——
# 本文件本身就是 UTF-8 中文文本，表格框线也用 Unicode，强行 ASCII 化只会更难读。


def demark(s: str, light: bool = False) -> str:
    """light=True：保留空白（用于代码块/流程块，缩进有意义）"""
    for k, v in EMOJI_MAP.items():
        s = s.replace(k, v)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)   # 链接
    s = s.replace("**", "").replace("__", "")
    s = s.replace("`", "")
    s = s.replace("~~", "")
    s = s.replace("\\|", "|")
    s = s.replace("\u2212", "-")      # U+2212 MINUS -> 普通减号
    if light:
        return s.rstrip()
    s = re.sub(r"  +", " ", s)        # 去掉去反引号后残留的双空格
    # 中文标点前不应有空格（`code`； → code；）
    s = re.sub(r"\s+([，。；：、）」』】》])", r"\1", s)
    return s.strip()


# --------------------------------------------------------------------------
# 表格渲染
# --------------------------------------------------------------------------
def alloc_widths(ncol: int, natural: list, budget: int, minimum: int = 10) -> list:
    w = [min(x, budget) for x in natural]
    while sum(w) + 3 * ncol + 1 > budget:
        k = max(range(ncol), key=lambda i: w[i])
        if w[k] <= minimum:
            break
        w[k] -= 1
    return w


def render_table(rows: list, budget: int, out: list) -> None:
    if not rows:
        return
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    natural = [max(dw(r[i]) for r in rows) for i in range(ncol)]
    widths = alloc_widths(ncol, natural, budget)

    def sep(ch="-"):
        return "+" + "+".join(ch * (widths[i] + 2) for i in range(ncol)) + "+"

    def emit(r):
        cells = [wrap(r[i], widths[i]) for i in range(ncol)]
        h = max(len(c) for c in cells)
        for k in range(h):
            parts = []
            for i in range(ncol):
                v = cells[i][k] if k < len(cells[i]) else ""
                parts.append(" " + pad(v, widths[i]) + " ")
            out.append("|" + "|".join(parts) + "|")

    out.append(sep("="))
    emit(rows[0])
    out.append(sep("="))
    for r in rows[1:]:
        emit(r)
        out.append(sep("-"))
    out.append("")


# --------------------------------------------------------------------------
# 主转换
# --------------------------------------------------------------------------
def convert(md: str, budget: int) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out = []
    i = 0
    in_code = False
    while i < len(lines):
        ln = lines[i]

        # 代码块
        if ln.strip().startswith("```"):
            in_code = not in_code
            out.append("  " + "-" * 66 if in_code else "  " + "-" * 66)
            i += 1
            continue
        if in_code:
            # 代码块：保留缩进（light=True 不折叠空白），仅去掉 Markdown 反引号
            out.append("  " + demark(ln, light=True))
            i += 1
            continue

        # 表格
        if ln.strip().startswith("|") and i + 1 < len(lines) and re.match(
                r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i]):
                    i += 1
                    continue
                cells = [demark(c.strip()) for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            render_table(rows, budget, out)
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lvl, text = len(m.group(1)), demark(m.group(2).strip())
            if out and out[-1] != "":
                out.append("")
            if lvl == 1:
                out.append(text)
                out.append("=" * dw(text))
            elif lvl == 2:
                out.append(text)
                out.append("-" * dw(text))
            else:
                out.append(" " * (lvl - 3) * 2 + ">> " + text)
            out.append("")
            i += 1
            continue

        # 分隔线
        if re.match(r"^\s*---+\s*$", ln):
            out.append("-" * 78)
            out.append("")
            i += 1
            continue

        # 引用
        if ln.strip().startswith(">"):
            body = demark(ln.strip().lstrip(">").strip())
            for w in wrap(body, budget - 4):
                out.append("  | " + w)
            i += 1
            continue

        # 列表
        m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", ln)
        if m:
            indent, bullet, body = m.group(1), m.group(2), demark(m.group(3))
            b = "  " * (len(indent) // 2) + (
                "* " if bullet in "-*+" else bullet + " ")
            avail = budget - dw(b)
            wl = wrap(body, avail)
            for k, w in enumerate(wl):
                out.append((b if k == 0 else " " * dw(b)) + w)
            i += 1
            continue

        # 普通段落
        if ln.strip():
            for w in wrap(demark(ln.strip()), budget):
                out.append(w)
        else:
            if out and out[-1] != "":
                out.append("")
        i += 1

    # 压缩多余空行
    res = []
    for l in out:
        if l == "" and res and res[-1] == "":
            continue
        res.append(l.rstrip())
    return "\n".join(res).rstrip() + "\n"


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src",
                    default=os.path.join(root, "docs", "DEPENDENCIES_A_B.md"))
    ap.add_argument("--out", dest="dst",
                    default=os.path.join(root, "docs", "DEPENDENCIES_A_B.txt"))
    ap.add_argument("--width", type=int, default=118,
                    help="每行最大显示列数（按 CJK 双宽计算，默认 118）")
    args = ap.parse_args()

    md = open(args.src, "r", encoding="utf-8").read()
    txt = convert(md, args.width)

    banner = (
        "==============================================================================\n"
        " 本文件由 scripts/export_dep_txt.py 从 docs/DEPENDENCIES_A_B.md 自动生成\n"
        "   · 请勿手工修改本文件；要改内容请改 .md，然后重跑：\n"
        "       python scripts/export_dep_txt.py\n"
        "   · 表格已按中日韩宽字符（全角算 2 列）对齐，长单元格自动折行；\n"
        "     纯文本宽度预算 %d 显示列。\n"
        "==============================================================================\n\n"
    ) % args.width
    txt = banner + txt

    with open(args.dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)

    size = os.path.getsize(args.dst)
    print("wrote %s" % args.dst)
    print("  lines=%d  bytes=%d  max_width_budget=%d" %
          (txt.count("\n"), size, args.width))
    return 0


if __name__ == "__main__":
    sys.exit(main())
