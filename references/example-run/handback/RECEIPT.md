# Receipt

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
