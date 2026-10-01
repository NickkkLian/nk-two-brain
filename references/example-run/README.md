# Example run: a real fix, handed to Codex, judged by Claude

Recorded on 2026-09-29 with this skill's `two_brain.py`. Local paths are replaced by `<run>` (the run folder),
`<temporary copy of work/>` and `<local clone of nk-breakable-selftest>`; nothing else was edited.

**The task.** [nk-breakable-selftest](https://github.com/NickkkLian/nk-breakable-selftest) judges a deliberate
break CAUGHT only if the self-test's output names the expected check (`must_mention`). It counted a match anywhere,
including on lines of checks that passed, so a break that landed elsewhere could still be judged CAUGHT. That was an
open item on the author's own list for that repository. The fix was built in a local clone and not pushed.

## Timeline

| stage | what happened | files |
|---|---|---|
| handoff | Claude (the session driving the skill) wrote the goal, three task-specific orders with reasons, a definition of "failure line" under *What you cannot see*, and five acceptance checks. One of them, A3, runs the hidden test with `scripts/breakcheck.py` put back to the base commit and must fail. | `handoff/START.md`, `handoff/acceptance.json`, `acceptor/accept_failure_lines.py` |
| build | Codex CLI 0.159.0, model gpt-6.1-sol, effort medium: exit 0 after 179 s, 7 commands, 3 files changed (+33 −2). It also wrote a helper script and four evidence files for its five claims. | `build/transcript.md` (readable), `build/events.jsonl` (raw), `build/diff.patch`, `handback/` |
| verify, pass 1 | All 5 acceptance checks passed, A3 included: with the old file, the hidden test reports 2 of its 4 verdicts wrong (`verify/A3.txt`). But the receipt was flagged 5 times: Codex cited its files as `evidence/selftest.txt`, and the checker only accepted a bare name. The hand-back rules had not said which. | `verify/first-pass-output.txt` |
| tool change | `two_brain.py` now accepts both forms, and the hand-back rules say so. | — |
| verify, pass 2 | planned 5 / ran 5 / failed 0, receipt clean. | `verify/output.txt`, `verify/A1.txt` … `A5.txt`, `verify/summary.json` |
| judge, run 1 | A tool-less `claude -p` run read the bundle: 4 supported, 2 insufficient. C3 (a count of 384 comparisons) and C5 (only three files modified) rested on files the builder wrote and nobody re-ran. For C5 it also said a diff of tracked files cannot rule out untracked ones. | `judge/run-1-verdicts.md` |
| tool change | The bundle's heading for `build/diff.patch` now says that it includes untracked files, which it always did. The two bundles differ in that one line only. | `judge/bundle.md` (run 2) |
| judge, run 2 | 6 supported. C5's change fits the new heading. C3 changed on identical evidence, so that change is one run reading differently from another. After this run, `verdicts.json` gained a `rests on` column, worked out from the citations: C3 is supported on builder files only, and the post draft says so. | `judge/run-2-verdicts.md`, `judge/run-2-verdicts.json` |
| judge, Codex | The same run-2 bundle, judged through the Codex route (`--judge codex`, gpt-6.1-sol, medium, read-only sandbox, empty folder) on a copy of the run: 6 supported. In its reasons it says which parts rest on builder files. | `judge/codex-judge-verdicts.md` |
| post | Draft from the run's files (Claude run 2); every number names its source file. | `post/draft.md` |

## Checking the saved verdicts yourself

`judge/raw-output.txt` is the answer the judge gave in run 2, as `--check` reads it: the `structured_output` of the recorded
`claude -p` call, with that call's session, cost and usage fields left out. From the skill folder,
`python3 scripts/two_brain.py judge references/example-run --check` holds that answer to the rules a verdict has to follow and
prints the six verdicts; it calls no model, leaves `judge/bundle.md` as the judge read it, and writes `judge/verdicts.json`,
which matches `judge/run-2-verdicts.json`. (The command also rebuilds the bundle in memory to list the files a verdict may
cite. That list has two more files than the bundle the judge read: `verify/first-pass-output.txt` and `verify/output.txt`
were added to this folder for the timeline above.)

## What this run shows, and what it does not

- The acceptor's own checks, not the builder's report, are what show the fix works: A2 passes on the new code and
  A3 fails on the old, both run by the acceptor after the build.
- Three judge runs: Claude run 1 gave 4 supported and 2 insufficient; Claude run 2 and the Codex run each gave 6
  supported. The two Claude runs disagreed about one claim on identical evidence. A verdict is one model reading the evidence once.
  For anything that matters, re-run the builder-only evidence yourself or judge more than once.
- The judge did not run anything, and nobody re-ran the builder's helper script (`handback/verify_failure_lines.py`).
- The fix itself had not been released when this was recorded.
