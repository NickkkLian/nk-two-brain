import ast
import itertools
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path.cwd()
tempfile.tempdir = str(root)
current = {}
source = Path("scripts/breakcheck.py").read_text()
exec(compile(source, "scripts/breakcheck.py", "exec"), current)
old_source = subprocess.check_output(["git", "show", "HEAD:scripts/breakcheck.py"], text=True)
old_judge = next(node for node in ast.parse(old_source).body if isinstance(node, ast.FunctionDef) and node.name == "judge")
old = {}
exec(compile(ast.Module(body=[old_judge], type_ignores=[]), "old judge", "exec"), old)

with tempfile.TemporaryDirectory(prefix="row79_verify_", dir=root) as tmp:
    Path(tmp, "checker.py").write_text(current["MIXED_CHECKER"])
    mutation = {"name": "passing name only", "file": "checker.py", "find": 'if "BBB" in s:', "replace": "if False:", "must_mention": "rule A"}
    cmd = f"{sys.executable} checker.py --selftest"
    rc0, out0 = current["run"](cmd, tmp)
    print("control output:", flush=True)
    print(out0, end="")
    print(f"control exit: {rc0}")
    current["apply_mutation"](tmp, mutation)
    rc, out = current["run"](cmd, tmp)
    print("mutated output:")
    print(out, end="")
    print(f"mutated exit: {rc}")
    before = old["judge"](rc0, rc, out, mutation["must_mention"])
    after = current["judge"](rc0, rc, out, mutation["must_mention"])
    print(f"old matcher: {before}; current matcher: {after}")
    assert rc0 == 0 and rc == 1 and before == "CAUGHT" and after == "RED-ELSEWHERE"

outputs = ["", "  ✔ rule A", "rule A", "  ✘ rule A", "  ✗ rule A", "  × rule A",
           "FAIL rule A", "FAILED: rule A", "failure rule A", "eRrOr: rule A",
           "FAILURELY rule A", "prefix ERROR rule A", "  ✘ rule B", "Traceback: rule A",
           "SyntaxError: rule A", "IndentationError: rule A"]
count = 0
for control, rc, out, mention in itertools.product([0, 1], [0, 1, 124], outputs, [None, "", "rule A", "rule B"]):
    before = old["judge"](control, rc, out, mention)
    after = current["judge"](control, rc, out, mention)
    if before != after:
        assert before == "CAUGHT" and after == "RED-ELSEWHERE" and mention
    count += 1
print(f"{count} judge comparisons passed: changes only CAUGHT to RED-ELSEWHERE when must_mention is set")
ast.parse(source, feature_version=(3, 9))
print("Python 3.9 grammar check passed (not a Python 3.9 runtime test)")
