#!/usr/bin/env python3
"""Acceptor's hidden check for the must_mention fix. Usage: accept_failure_lines.py <repo root>
Runs the repo's breakcheck.py --spec against two tiny checkers and reads the verdict of each mutation.
Exit 0 when every verdict is the expected one, 1 otherwise (never a traceback on a wrong verdict)."""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.abspath(sys.argv[1])
TICK = '''import sys
def check(s):
    out = []
    if "AAA" in s:
        out.append("A")
    if "BBB" in s:
        out.append("B")
    return out
def selftest():
    a, b = check("AAA") == ["A"], check("BBB") == ["B"]
    print(("  \\u2714" if a else "  \\u2718") + " rule A sample caught")
    print(("  \\u2714" if b else "  \\u2718") + " rule B sample caught")
    return 0 if a and b else 1
sys.exit(selftest())
'''
WORD = '''import sys
def check(s):
    return [x for x in ("C", "D") if x * 3 in s]
def selftest():
    c, d = check("CCC") == ["C"], check("DDD") == ["D"]
    print("ok: rule D" if d else "FAIL: rule D broken")
    print("ok: rule C" if c else "FAIL: rule C broken")
    return 0 if c and d else 1
sys.exit(selftest())
'''
CASES = [  # (checker, name, find, replace, must_mention, expected verdict)
    ("tick.py", "breakB-mentionA", 'if "BBB" in s:', "if False:", "rule A", "RED-ELSEWHERE"),
    ("tick.py", "breakB-mentionB", 'if "BBB" in s:', "if False:", "rule B", "CAUGHT"),
    ("word.py", "breakC-mentionC", '("C", "D")', '("D",)', "rule C", "CAUGHT"),
    ("word.py", "breakC-mentionD", '("C", "D")', '("D",)', "rule D", "RED-ELSEWHERE"),
]
bad = 0
for checker, name, find, rep, mention, want in CASES:
    d = tempfile.mkdtemp(prefix="accept79_")
    open(os.path.join(d, "tick.py"), "w").write(TICK); open(os.path.join(d, "word.py"), "w").write(WORD)
    spec = os.path.join(d, "spec.json")
    json.dump({"mutations": [{"name": name, "file": checker, "find": find, "replace": rep, "must_mention": mention}]}, open(spec, "w"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "breakcheck.py"), "--root", d, "--cmd",
                        f"{sys.executable} {checker}", "--spec", spec], capture_output=True, text=True, timeout=120)
    row = [l for l in r.stdout.splitlines() if name in l]
    got = row[0].split()[-1] if row else "(no row)"
    ok = got == want
    bad += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name}: must_mention {mention!r} -> {got} (want {want})")
print("all verdicts as expected" if not bad else f"FAIL: {bad} verdict(s) wrong")
sys.exit(1 if bad else 0)
