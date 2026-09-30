assistant: I’ll check the verdict logic and self-tests, add the passing-line regression sample, update the docs, and record the test evidence in the handback folder.

$ /bin/zsh -lc "pwd; rg --files -g AGENTS.md -g 'breakcheck.py' -g README.md -g SKILL.md; cat ../handback/RECEIPT.md"
  (exit 0)
  | <run>/work
  | SKILL.md
  | scripts/breakcheck.py
  | README.md
  | # Receipt
  | 
  | ## Claims
  | <<< FILL: one line per claim, exactly:  - C1: <one checkable sentence> | evidence: <file in evidence/>, <file> >>>
  | 
  | ## How I verified
  | <<< FILL >>>
  | 
  | ## Unsure
  | <<< FILL: what you are not sure of. Write "none" only if that is true. >>>
  | 
  | ## Boundary crossings
  | <<< FILL: anything you did outside the boundaries, or "none". >>>

$ /bin/zsh -lc 'git status --short; cat scripts/breakcheck.py; cat README.md; cat SKILL.md'
  (exit 0)
  | 5. **Read the verdicts.** `CAUGHT` is the only good one.
  |    `UNCOVERED` = the line is decorative or no sample exercises it → add an exclusive sample or delete the line.
  |    `CRASH` = your mutation broke syntax; a traceback is not a detection → pick a different break.
  |    `RED-ELSEWHERE` = it went red for an unrelated reason → the matrix would degrade into "always red"; fix the sample.
  |    `CONTROL-RED` = the command fails without any mutation → nothing else in the table means anything.
  | 6. **Pick break points that can actually change behaviour.** Removing a `break` inside a loop that is
  |    guarded by another condition changes nothing and looks like "uncovered". When a break is reported
  |    UNCOVERED, first confirm by hand that the mutation alters an output; only then blame the self-test.
  | 7. **Detectors fail loud, guardrails fail open.** A detector that errors must abort and print nothing that
  |    could be read as green. A pre-command guardrail that errors must let the command through (a broken
  |    guardrail that blocks everything is worse than none). Decide which one you are writing and say so in
  |    the header.
  | 8. **Name what was not scanned.** Files skipped, extensions ignored, archives not opened: list them in the
  |    report. "All green" is read as "everything was checked".
  | 9. **Do not mix apertures.** "Committed version matches", "working tree matches", "no drift at all" are
  |    three states; one number covering two of them creates the next incident.
  | 10. **Ask the inverse question once.** The matrix asks "is deliberate breakage caught?". Also try a sample
  |     that satisfies the rule while doing the job badly (a lazy satisfier). If it passes, the rule measures
  |     the wrong thing.
  | 
  | ## Evidence to keep
  | 
  | Paste the matrix table (control row included) and the exact command next to the change. A claim that the
  | self-test "works" without the table is the thing this skill exists to stop.
  | 
  | ## Boundaries
  | 
  | - `--auto` only understands Python line structure; for shell/JS/other files use `--spec`.
  | - Point `--auto` at the file that does the checking, not at the self-test's own assertions: neutralising an
  |   assertion can only make the self-test *more* lenient, so every such row reads UNCOVERED by construction.
  | - Neutralising a line that is part of a multi-line expression yields `CRASH`; use `--spec` for those.
  | - The matrix proves the self-test reacts to the breaks you listed. It says nothing about failure modes
  |   nobody wrote a rule for (see rule 8).
  | 
  | ## Provenance
  | 
  | Own practice, 2026-08 to 2026-09: the rule came from a detector whose self-test stayed green while the
  | real run emitted 266 false positives, and was refined by the cases in `references/incidents.md`. The four
  | break-matrix criteria (red / control green / not a crash / red on the named assertion) were written after an
  | audit showed a matrix could be satisfied for the wrong reason. No external source was used.

$ /bin/zsh -lc "rg --files -g '*test*' -g AGENTS.md; ls -a"
  (exit 0)
  | .
  | ..
  | .claude-plugin
  | .git
  | LICENSE
  | README.md
  | SKILL.md
  | references
  | scripts

edit: update <run>/work/scripts/breakcheck.py

assistant: The verdict now checks the name only on failure lines, with crash detection still taking precedence. The new mutation breaks rule B while rule A prints a passing line; it must return RED-ELSEWHERE. I’m checking the accepted failure prefixes and comparing that sample with the old matcher.

edit: update <run>/work/README.md, update <run>/work/SKILL.md

$ /bin/zsh -lc 'TMPDIR="$PWD" python3 scripts/breakcheck.py --selftest; git diff --check; git diff --stat'
  (exit 0)
  | breakcheck selftest · 22/22 passed
  |   ✔ control run is green
  |   ✔ auto: neutralising rule A's append is CAUGHT (CAUGHT)
  |   ✔ auto: neutralising rule B's append is UNCOVERED (UNCOVERED)
  |   ✔ spec: flipping rule A is CAUGHT and names 'rule A' (CAUGHT)
  |   ✔ spec: a syntax error is CRASH, not a detection (CRASH)
  |   ✔ spec: a missing anchor is refused (BAD-ANCHOR)
  |   ✔ spec: red on the wrong assertion is RED-ELSEWHERE (RED-ELSEWHERE)
  |   ✔ zero candidate lines is exit 2 'proves nothing', never a green 0 mutations (2)
  |   ✔ an always-red command is reported as CONTROL-RED, never as caught
  |   ✔ spec: must_mention only on a passing line is RED-ELSEWHERE (RED-ELSEWHERE)
  |   ✔ failure prefix ✘ names the assertion
  |   ✔ failure prefix ✗ names the assertion
  |   ✔ failure prefix × names the assertion
  |   ✔ failure prefix FAIL names the assertion
  |   ✔ failure prefix FAILED: names the assertion
  |   ✔ failure prefix failure names the assertion
  |   ✔ failure prefix eRrOr: names the assertion
  |   ✔ no failure line cannot satisfy must_mention ('  ✔ rule A')
  |   ✔ no failure line cannot satisfy must_mention ('rule A')
  |   ✔ no failure line cannot satisfy must_mention ('  FAILEDLY rule A')
  |   ✔ no failure line cannot satisfy must_mention ('note: FAIL rule A')
  |   ✔ no failure line cannot satisfy must_mention ('')
  |  README.md             |  5 +++++
  |  SKILL.md              |  3 +++
  |  scripts/breakcheck.py | 27 +++++++++++++++++++++++++--
  |  3 files changed, 33 insertions(+), 2 deletions(-)

$ /bin/zsh -lc "python3 - <<'PY'
from pathlib import Path
p = Path('../handback/verify_failure_lines.py')
p.write_text('''import ast
import itertools
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path.cwd()
tempfile.tempdir = str(root)
current = {}
source = Path(\"scripts/breakcheck.py\").read_text()
exec(compile(source, \"scripts/breakcheck.py\", \"exec\"), current)
old_source = subprocess.check_output([\"git\", \"show\", \"HEAD:scripts/breakcheck.py\"], text=True)
old_judge = next(node for node in ast.parse(old_source).body if isinstance(node, ast.FunctionDef) and node.name == \"judge\")
old = {}
exec(compile(ast.Module(body=[old_judge], type_ignores=[]), \"old judge\", \"exec\"), old)

with tempfile.TemporaryDirectory(prefix=\"row79_verify_\", dir=root) as tmp:
    Path(tmp, \"checker.py\").write_text(current[\"MIXED_CHECKER\"])
    mutation = {\"name\": \"passing name only\", \"file\": \"checker.py\", \"find\": 'if \"BBB\" in s:', \"replace\": \"if False:\", \"must_mention\": \"rule A\"}
    cmd = f\"{sys.executable} checker.py --selftest\"
    rc0, out0 = current[\"run\"](cmd, tmp)
    print(\"control output:\", flush=True)
    print(out0, end=\"\")
    print(f\"control exit: {rc0}\")
    current[\"apply_mutation\"](tmp, mutation)
    rc, out = current[\"run\"](cmd, tmp)
    print(\"mutated output:\")
    print(out, end=\"\")
    print(f\"mutated exit: {rc}\")
    before = old[\"judge\"](rc0, rc, out, mutation[\"must_mention\"])
    after = current[\"judge\"](rc0, rc, out, mutation[\"must_mention\"])
    print(f\"old matcher: {before}; current matcher: {after}\")
    assert rc0 == 0 and rc == 1 and before == \"CAUGHT\" and after == \"RED-ELSEWHERE\"

outputs = [\"\", \"  ✔ rule A\", \"rule A\", \"  ✘ rule A\", \"  ✗ rule A\", \"  × rule A\",
           \"FAIL rule A\", \"FAILED: rule A\", \"failure rule A\", \"eRrOr: rule A\",
           \"FAILURELY rule A\", \"prefix ERROR rule A\", \"  ✘ rule B\", \"Traceback: rule A\",
           \"SyntaxError: rule A\", \"IndentationError: rule A\"]
count = 0
for control, rc, out, mention in itertools.product([0, 1], [0, 1, 124], outputs, [None, \"\", \"rule A\", \"rule B\"]):
    before = old[\"judge\"](control, rc, out, mention)
    after = current[\"judge\"](control, rc, out, mention)
    if before "'!= after:
        assert before == "CAUGHT" and after == "RED-ELSEWHERE" and mention
    count += 1
print(f"{count} judge comparisons passed: changes only CAUGHT to RED-ELSEWHERE when must_mention is set")
ast.parse(source, feature_version=(3, 9))
print("Python 3.9 grammar check passed (not a Python 3.9 runtime test)")
'"''')
PY"
  (exit 0)


$ /bin/zsh -lc "python3 - <<'PY'
from pathlib import Path
import subprocess
folder = Path('../handback/evidence')
folder.mkdir(exist_ok=True)
commands = {
    'selftest.txt': 'TMPDIR=\""'$PWD" python3 scripts/breakcheck.py --selftest && printf "exit=0'"\\\\n\"',
    'old-vs-new.txt': 'python3 ../handback/verify_failure_lines.py',
    'docs.txt': 'git diff -- README.md SKILL.md',
    'diff-check.txt': 'git diff --check && git status --short',
}
for name, cmd in commands.items():
    result = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (folder / name).write_text('"'$ '"' + cmd + '\\n' + result.stdout)
    print(name + ': exit=' + str(result.returncode))
    print(result.stdout, end='')
    if result.returncode:
        raise SystemExit(result.returncode)
PY"
  (exit 0)
  |   ✘ rule B sample not caught
  | mutated exit: 1
  | old matcher: CAUGHT; current matcher: RED-ELSEWHERE
  | 384 judge comparisons passed: changes only CAUGHT to RED-ELSEWHERE when must_mention is set
  | Python 3.9 grammar check passed (not a Python 3.9 runtime test)
  | docs.txt: exit=0
  | diff --git a/README.md b/README.md
  | index eedf334..939a3f3 100644
  | --- a/README.md
  | +++ b/README.md
  | @@ -26,6 +26,11 @@ The full procedure, the boundaries and where the rules came from are in [SKILL.m
  |  5. Read the verdicts
  |  6. Pick break points that can actually change behaviour
  |  
  | +With `--spec`, `must_mention` counts only on failure lines: the first non-space character is `✘`, `✗`
  | +or `×`, or the first word is FAIL, FAILED, FAILURE or ERROR (any case, optionally followed by `:`).
  | +A name on a passing line cannot satisfy it. Output with no failure lines cannot satisfy it either;
  | +a red run then reads `RED-ELSEWHERE`.
  | +
  |  ## Why it is built this way
  |  
  |  **The idea.** A self-test that cannot be made to fail proves nothing. Break the line it guards; the self-test must go red.
  | diff --git a/SKILL.md b/SKILL.md
  | index 17fc430..559fac1 100644
  | --- a/SKILL.md
  | +++ b/SKILL.md
  | @@ -38,6 +38,9 @@ people from doubting.
  |       or write the breaks with `--spec`.
  |     - Any language, hand-picked breaks: write `mutations.json`
  |       (`{"mutations":[{"name":..,"file":..,"find":..,"replace":..,"must_mention":..}]}`) and run with `--spec`.
  | +     `must_mention` counts only on failure lines: the first non-space character is `✘`, `✗` or `×`, or
  | +     the first word is FAIL, FAILED, FAILURE or ERROR (any case, optionally followed by `:`).
  | +     A name on a passing line cannot satisfy it; output with no failure lines cannot satisfy it either.
  |     - The script's own `--selftest` runs first and aborts everything if it fails.
  |  5. **Read the verdicts.** `CAUGHT` is the only good one.
  |     `UNCOVERED` = the line is decorative or no sample exercises it → add an exclusive sample or delete the line.
  | diff-check.txt: exit=0
  |  M README.md
  |  M SKILL.md
  |  M scripts/breakcheck.py

assistant: All 22 self-test checks pass. On the same rule B mutation, the old matcher returns CAUGHT and the new matcher returns RED-ELSEWHERE. The comparison checks also preserve the other verdicts. Python 3.9 grammar validation passed; I haven’t tested on a Python 3.9 runtime.

edit: update <run>/work/README.md

$ /bin/zsh -lc "python3 - <<'PY'
from pathlib import Path
import subprocess
for name, cmd in [('docs.txt', 'git diff -- README.md SKILL.md'), ('diff-check.txt', 'git diff --check && git status --short')]:
    r = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    Path('../handback/evidence', name).write_text('"'$ '"' + cmd + '\\n' + r.stdout)
    assert r.returncode == 0
Path('../handback/RECEIPT.md').write_text('''# Receipt

## Claims
- C1: The self-test passes all 22 checks and exits 0, including the mutation whose must_mention appears only on a passing line and is judged RED-ELSEWHERE. | evidence: evidence/selftest.txt
- C2: The same rule B mutation prints rule A only on a passing line; the original HEAD judge returns CAUGHT and the updated judge returns RED-ELSEWHERE. | evidence: evidence/old-vs-new.txt
- C3: In 384 judge comparisons, verdict changes were limited to CAUGHT becoming RED-ELSEWHERE with must_mention set; the updated script parses with Python 3.9 grammar. | evidence: evidence/old-vs-new.txt
- C4: README.md and SKILL.md define failure lines and state that passing lines and output with no failure lines cannot satisfy must_mention. | evidence: evidence/docs.txt
- C5: git diff --check passes and the working tree lists only README.md, SKILL.md and scripts/breakcheck.py as modified. | evidence: evidence/diff-check.txt

## How I verified
Ran the bundled self-test with TMPDIR set to the working folder. The handback verification script executes the new two-rule checker, mutates rule B, and compares the current judge with the judge extracted from HEAD. It also compares verdicts across controls, return codes, output formats and optional names, and checks Python 3.9 grammar. Checked the documentation diff and whitespace. Each evidence file starts with its exact re-runnable command and contains raw command output.

## Unsure
Python 3.9 runtime execution was not tested; only its grammar was checked. The 384 comparisons are finite coverage, not a proof over every possible output string.

## Boundary crossings
none. Changes remain uncommitted. Temporary checker folders were created inside the working folder and removed. Receipt, verification helper and evidence are inside handback. The acceptor folder was not read; version metadata was not changed.
''')
PY"
  (exit 0)


assistant: Implemented failure-line-only matching, added the passing-line regression sample, and updated both docs.

All 22 self-tests pass. Evidence confirms the old matcher returns CAUGHT for the new sample while the fix returns RED-ELSEWHERE. Changes remain uncommitted.

[Receipt and evidence](../handback/RECEIPT.md)

[turn completed] usage {"input_tokens": 210239, "cached_input_tokens": 174336, "cache_write_input_tokens": 0, "output_tokens": 4450, "reasoning_output_tokens": 1021}
