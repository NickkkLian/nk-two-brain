# Handoff: row79-failure-lines

## Goal
`scripts/breakcheck.py` in this repository (nk-breakable-selftest, an agent skill that proves a self-test can go red)
judges a mutation CAUGHT only if the self-test's output names the expected assertion (`must_mention`). Today it counts
a match anywhere in the output, including on lines of checks that passed. So a mutation that breaks rule B, with
`must_mention: "rule A"`, is judged CAUGHT whenever the output also prints a passing line such as `✔ rule A sample
caught`. That is a false CAUGHT. Make `must_mention` count only on failure lines, add a self-test sample where the name
appears only on a passing line, and say so in the docs.

## Boundaries (orders, each with its reason)
- Work only inside `<run>/work`. Write your receipt and evidence only inside `<run>/handback`. Reason: everything else belongs to someone else's line of work; a helpful write there overwrites it silently.
- Do not commit, push, tag or add remotes. Leave your changes in the working tree. Reason: the acceptor reviews the diff and commits it; a push cannot be taken back.
- Do not read `<run>/acceptor`. Reason: it holds the acceptance checks; they stay independent only if the work was not shaped to them.
- Do not change version numbers (`.claude-plugin/plugin.json`, SKILL.md metadata). Reason: releasing is the acceptor's job and follows its own checklist.
- Standard library only; keep Python 3.9 compatibility. Reason: the skill promises both in its README.
- Do not change the verdict names (CAUGHT, UNCOVERED, CRASH, RED-ELSEWHERE, CONTROL-RED, BAD-ANCHOR) or the exit codes. Reason: users grep them.

## What you cannot see
- This was found in an audit of the published repo: the must_mention check was shown to accept a break that landed elsewhere. It is item 79 on the owner's deferred list, to be fixed before the next release.
- Definition to use. A **failure line** is a line of the self-test's output whose first non-space character is `✘`, `✗` or `×`, or whose first word is FAIL, FAILED, FAILURE or ERROR (any case, optionally followed by `:`). `must_mention` must be found on at least one failure line. Output with no failure lines at all therefore never satisfies must_mention.
- Tracebacks are already judged CRASH before must_mention is looked at; keep that order.
- House style of the repo: short, plain English; each rule in SKILL.md says what it cannot catch. The self-test prints `  ✔ label` / `  ✘ label` lines, one per check.

## Done means
1. `python3 scripts/breakcheck.py --selftest` exits 0, and it contains a new sample: a mutation whose must_mention appears only on a passing line is judged RED-ELSEWHERE, not CAUGHT.
2. The same new sample would be judged CAUGHT by the old matching (show this in your evidence: e.g. a run of the self-test against the old matching logic, or a break matrix over your new lines).
3. SKILL.md and README.md say that must_mention counts only on failure lines, with the definition above.
4. Nothing else in behaviour changes.


---
## Hand-back rules (added by two_brain.py; the same for every run)
- Your working folder: `<run>/work`. Your receipt: `<run>/handback/RECEIPT.md` (already there as a template; replace every `<<< FILL` slot).
- Evidence: one file per claim in `<run>/handback/evidence/`. First line `$ <the exact command, re-runnable from <run>/work>`, then the command's raw output, unedited. A summary is not evidence.
- Each claim in the receipt is one line: `- C1: <sentence> | evidence: <file>, <file>`. Claim only what your evidence shows.
- "Unsure" is the most useful section. Empty means unfilled, not confident.
- A separate model that did not see your work will judge each claim from the evidence alone: supported, not supported or insufficient. The acceptor also re-runs its own checks.
- If you need an answer to continue, stop and write the question as the last line of your final message.
