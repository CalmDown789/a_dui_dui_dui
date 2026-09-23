#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint_tcl.py -- hard gate against the Tcl bracket trap (audit-doc defect #2).

A `[` inside a double-quoted string IS command substitution in Tcl, even inside the
argument of `puts`.  Getting this wrong killed a script 8 minutes into place-and-route
(it died while writing the summary .txt, leaving it truncated) and, in another home,
silently wrote the wrong text (`create_clock -period 5.000 clk` instead of
`... [get_ports clk]`).  This gate makes a recurrence fail fast, in seconds.

Usage
-----
    python scripts/lint_tcl.py scripts/run_sim.tcl scripts/synth_check.tcl
    python scripts/lint_tcl.py --selftest          # verify the gate itself

Exit 0 = clean, 1 = offender(s) or a failing self-test.

Design notes (each one is a mistake that was actually made)
-----------------------------------------------------------
* **Never count `"` to decide balance.**  `set m "DIRTY: [string map [list "\\n" " "] $x]"`
  contains 5 double quotes.  Counting gives a false "unbalanced"; a whole file may
  accidentally total an even number and *appear* to work.  Tcl's real rule is that a
  `[` inside `"..."` opens a nested script with its OWN independent quotes, so the
  scanner below is a small state machine, not a regex.
* **A whitelisted head is not enough** when the command has destructive subcommands:
  `[file size $f]` is fine, `[file delete $f]` is not.  Subcommands are checked for
  heads in REQUIRE_SUB.
* **A too-narrow whitelist kills the gate.**  An early version omitted `list` and
  flagged a perfectly legal `[string map [list ...] $x]`; a linter that cries wolf gets
  deleted.  Never widen the whitelist to silence a hit -- confirm it is read-only first.
"""
import io
import os
import re
import sys

BAD_MARK = "<unterminated>"

# Read-only queries / pure helpers.  Deliberately EXCLUDES the mutating + shelling-out
# commands this gate exists to surface: exec, open, glob, cd, source, file delete, ...
OK_HEAD = {"version", "clock", "file", "info", "string", "expr", "format",
           "llength", "lsearch", "lindex", "lrange", "lsort", "list", "join",
           "split", "concat", "env", "set", "array", "scan", "regexp", "regsub",
           "get_ports", "get_cells", "get_pins", "get_nets", "get_property",
           "get_files", "get_ips", "pid", "auto_execok"}

# heads that MUST carry a whitelisted second word
REQUIRE_SUB = {"file"}
OK_SUB = {
    "file": {"exists", "size", "dirname", "tail", "join", "normalize", "split",
             "extension", "rootname", "nativename", "isdirectory", "isfile",
             "readable", "writable", "executable", "type", "mtime", "atime",
             "pathtype", "separator", "volumes"},
}


def match_bracket(s, i):
    """s[i] == '['.  Return (index after the matching ']', head word, second word).

    Handles nested brackets AND nested quoted strings (quotes inside the nested
    script are independent of any outer quoting)."""
    depth, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':                       # a quoted string inside the nested script
            j += 1
            while j < n:
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == '"':
                    j += 1
                    break
                j += 1
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                body = s[i + 1:j]
                m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_:]*)(?:\s+(\S+))?", body)
                if not m:
                    return j + 1, BAD_MARK, ""
                return j + 1, m.group(1), (m.group(2) or "")
        j += 1
    return n, BAD_MARK, ""


def head_is_ok(head, second):
    h = head.split("::")[-1]
    if h not in OK_HEAD:
        return False
    if h in REQUIRE_SUB:
        return second in OK_SUB[h]
    return True


def in_quote_substs(line):
    """(head, second word) of every substitution occurring INSIDE a "..." region of one
    line.  Walking quoted regions (instead of line-matching `[`) is what keeps ordinary
    Tcl like `set fh [open ...]` out of the report."""
    res, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c != '"':
            i += 1
            continue
        i += 1                              # enter the quoted region
        while i < n:
            c = line[i]
            if c == "\\":
                i += 2
                continue
            if c == "[":
                i, head, second = match_bracket(line, i)
                res.append((head, second))
                continue
            if c == '"':
                i += 1
                break                       # region closed
            i += 1
        else:
            res.append(("<unterminated-quote>", ""))    # region ran to end of line
    return res


def lint_text(src):
    bad = []
    for i, line in enumerate(src.split("\n"), 1):
        # Tcl strips comments before substitution, so a whole-line comment is harmless
        # (a *trailing* `#` is NOT a comment in Tcl, so it stays code here).
        if line.lstrip().startswith("#"):
            continue
        for head, second in in_quote_substs(line):
            if not head_is_ok(head, second):
                shown = head if not second else "%s %s" % (head, second)
                bad.append((i, shown, line.strip()[:100]))
    return bad


# ------------------------------------------------------------------ self-test
SELFTEST = [
    # name,             tcl body,                                                     want
    ("bad_exec",        'puts " rc=[exec echo hi]"',                                    1),
    ("bad_open_w",      'puts " w [open x.txt w]"',                                     1),
    ("bad_filedel_iq",  'puts " rm [file delete x.tmp]"',                               1),
    ("bad_bare_word",   'puts " val [grab=$uram]"',                                     1),
    ("bad_unterm_q",    'puts " unbalanced',                                            1),
    ("bad_unterm_br",   'puts " [clock seconds',                                        1),
    ("ok_getports",     'puts " [get_ports clk]"',                                      0),
    ("ok_clock",        'puts " t : [clock format [clock seconds]]"',                    0),
    ("ok_nested",       'set m "DIRTY: [string map [list "\\n" " "] $lm]"',              0),
    ("ok_stringmap",    'puts $rf " [string map {a b} $x]"',                             0),
    ("ok_plain",        'set fh [open "x.txt" w]',                                       0),
    ("ok_comment",      '# --- puts " [Flow A] " (comment: harmless) ---',               0),
    ("bad_script",      None,                                                            1),
]


def selftest():
    """Prove the gate both fires and stays quiet.  A gate that only ever prints
    CLEAN proves nothing."""
    # a realistic bad script: the exact line that killed impl_check.tcl
    bad_script = ('puts " [Flow A] synth ..."\n'
                  'puts $rf " URAM : 0 (none) [grab=$uram] ..."\n')
    fails = 0
    for name, body, want in SELFTEST:
        if body is None:
            bad = lint_text(bad_script)
            got = 1 if bad else 0
        else:
            got = 1 if lint_text(body) else 0
        ok = got == want
        fails += 0 if ok else 1
        print("%s %-15s got=%d want=%d" % ("ok " if ok else "FAIL", name, got, want))
    print("SELFTEST %s" % ("PASS" if not fails else "FAIL (%d)" % fails))
    return 1 if fails else 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] in ("--selftest", "-t"):
        return selftest()
    rc = 0
    for path in argv:
        if not os.path.isfile(path):
            print("%s: no such file" % path)
            rc = 1
            continue
        bad = lint_text(io.open(path, encoding="utf-8").read())
        for i, shown, text in bad:
            print("%s:%d  in-quote [%s ...]  | %s" % (path, i, shown, text))
        print("%-32s %s" % (path, "LINT CLEAN" if not bad
                            else "LINT FAILED (%d)" % len(bad)))
        if bad:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
