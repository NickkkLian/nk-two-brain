---
name: nk-two-brain
description: "Run a coding task through two different AI agents with proof at the end: Claude writes a handoff package (goal, boundaries as orders, what the builder cannot see, acceptance checks kept from the builder), OpenAI Codex builds it in a fresh clone, the acceptor re-runs its own checks (including one with the code broken on purpose), a separate model run that did no building judges each claim from the evidence alone with exactly three verdicts (supported, not supported, insufficient), and a post draft is written from the run's files. Use when handing a real change to a second agent and you need to know what actually got proven, when you want a builder and a judge that are not the same session, or when you want a record of a delegated task that someone else can re-check. Works from Claude Code; falls back to Claude as the builder when Codex is not installed, and to a manual stage when neither CLI is there. Not an autopilot: nothing is committed or pushed."
license: MIT
metadata:
  provenance: own practice (2026-09) delegating work between Claude Code and Codex; see Provenance
  version: 0.1.0
---
# Two brains

**The agent that did the work is the worst judge of whether it worked.** So split the roles: one brain writes the
handoff and keeps the acceptance checks, another builds, and a third run that did no building reads only the evidence
and answers, claim by claim, *supported*, *not supported* or *insufficient*. Nothing in between is taken on faith: the
builder's "tests pass" is a claim, not a result.

> **Paths.** Commands in this skill start with `${…SKILL_DIR}`: this skill's own folder, the one that contains this SKILL.md. Claude Code fills it in. If your agent shows the placeholder as written (Codex, Cursor, Gemini CLI and others), replace it with that folder's absolute path before you run the command. Left as it is, it expands to nothing and the path breaks.

## The pipeline

| # | stage | who | what it produces | discipline it applies |
|---|---|---|---|---|
| 1 | handoff | you (Claude) | `handoff/START.md`, `acceptance.json`, hidden checks in `acceptor/`, `trust.json` | handoff package: boundaries as orders with reasons, "what you cannot see", acceptance kept outside the builder's reach |
| 2 | build | Codex (default) | the change in `work/`, `build/transcript.md`, `build/diff.patch`, the builder's `handback/RECEIPT.md` and evidence | the builder works in a fresh clone with no remote, inside Codex's workspace-write sandbox |
| 3 | verify | the script | `verify/A*.txt` (each file starts with `$ command`), `summary.json` | evidence audit (raw output, re-runnable command); breakable self-test (a check must go red when the code is broken) |
| 4 | judge | a fresh model run with no tools | `judge/bundle.md`, `verdicts.json`, `verdicts.md` | evidence audit: three verdicts, no fourth; the judge is not the builder |
| 5 | post | the script | `post/draft.md`, every number with its source file | post kit: claims traced to files; a privacy gate before anything is public |

All five live in one run folder. The builder is pointed at two sub-folders only: `work/` and `handback/`.

## Procedure

1. **Check the machine.** `python3 ${CLAUDE_SKILL_DIR}/scripts/two_brain.py doctor` names the builder and judge it
   found. Default: Codex builds, Claude judges. No Codex: Claude builds (say so in the write-up: builder and judge
   are then one model family, in separate runs). Neither: both stages are written out for a person or another agent.
2. **Start a run.** `two_brain.py init <run> --repo <git repo> --name <short-name> [--base REF]`. It clones the
   committed base into `<run>/work`, removes the remote, and writes templates. Keep `<run>` outside the repo and
   outside any folder whose `AGENTS.md` or `CLAUDE.md` you do not want the builder to load.
3. **Write the handoff** (`handoff/START.md`). Fill every `<<< FILL` slot:
   - *Goal*: what must be true, in words a stranger could check.
   - *Boundaries*: orders with reasons ("do not change version numbers: releasing is the acceptor's job"), never
     statements about what the builder can or cannot do. Three are already there: work only in `work/`, no commit or
     push, do not read `acceptor/`.
   - *What you cannot see*: the context only you have — history, conventions, definitions, what was tried.
   - *Done means*: a short list of observable end states.
4. **Write the acceptance checks** (`handoff/acceptance.json`) and put any hidden test in `acceptor/`. Each item is
   `{id, cmd, expect: pass|fail}`, run with a shell in `{root}`. Add at least one **break item**: the same check with
   the change undone (`"break": {"revert": "path"}`) or one anchor replaced (`{"file", "find", "replace"}`), which
   must then FAIL. A check that passes both with and without the change proves nothing about the change. Write the
   check so it exits non-zero with a message: a red that only comes from a traceback counts as a crash, not a detection.
5. **Seal.** `two_brain.py seal <run>` refuses while a slot is unfilled, then prints a trust-root hash. Keep that
   line outside the run (the chat is fine) and pass it to `verify --trust-root`.
6. **Build.** `two_brain.py build <run> [--builder codex|claude|manual] [--model M] [--effort E]`. The Codex route is
   `codex exec --json -s workspace-write -C work --add-dir handback`, prompt on stdin: START.md plus fixed hand-back
   rules (receipt format, one evidence file per claim, first line `$ command`). If the builder ends on a question,
   the script says so; answer it and build again, or finish by hand. The Claude route (`claude -p --permission-mode
   acceptEdits`) cannot ask anyone for approval mid-run, so a command your settings do not allow is denied and listed
   in the transcript. Allow what the task needs up front: `--allow-tool 'Bash(python3 *)'` (repeatable).
7. **Verify.** `two_brain.py verify <run> --trust-root <hash>` checks the seal (an edited acceptance list is not
   run), checks the receipt (claims in the form `- C1: … | evidence: file`, cited files exist and start with `$ `,
   Unsure filled), then runs every acceptance item itself and prints `planned N / ran M / failed K`. NOT RUN is never
   a pass.
8. **Judge.** `two_brain.py judge <run> [--judge claude|codex|manual]`. The bundle holds only: the task, the
   acceptance list, the claims (plus C0, "the goal is met", added by the acceptor), the receipt and builder evidence
   (marked BUILDER-SUPPLIED, not re-run), the acceptor's re-runs (marked RE-RUN BY ACCEPTOR) and the diff. The Claude
   route runs `claude -p --tools ""` in an empty folder, so the judge has nothing but the bundle. An answer that
   breaks the rules (a fourth verdict, a claim skipped or judged twice, a file cited that is not in the bundle,
   "insufficient" without what would settle it) is rejected with exit 2, never read as a verdict.
9. **Draft the post.** `two_brain.py post <run>` writes `post/draft.md` from the run's files only. Before anything
   goes public, turn it into a full kit (nk-post-kit) and run a privacy check (nk-publish-gate).
10. **Accept or send back.** Read `judge/verdicts.md`. Its `rests on` column is worked out from the citations: a
    claim "supported" on builder files only is one to re-run yourself before relying on it. Commit the diff yourself
    only for what holds up; for "insufficient", the verdict names the artefact that would settle it — ask for exactly that.

## Design rules

- **A builder's "all tests pass" is a claim.** The acceptor re-runs its own checks after the build; the judge sees
  which files the builder wrote and which the acceptor re-ran.
- **Boundaries are orders, not capability statements.** "It has no access to X" is either false (then it is a
  signpost to X) or redundant. Say "do not write to X" and why.
- **An acceptance check must be able to fail.** The break item runs the check against the base version of the file;
  if it still passes, the check does not test the change.
- **The judge judges evidence, not code.** It gets no tools and no repository, so "I looked and it seemed fine" is not
  available to it. Three verdicts, no fourth; "insufficient" must name what would settle it.
- **Results from an earlier verify never reach the judge.** Each verify clears the old re-run files first.
- **Degrade loudly.** A missing CLI is exit 4 with the manual route printed; it is never a silent skip.

## Build route: `codex exec`, with room for a richer client

The build stage uses `codex exec`, which ships with every Codex CLI and needs nothing else. It cannot stop mid-run to
ask a question or wait for an approval: the builder either finishes or ends its message on a question, which the
script reports. If you run a client of the Codex app-server (the interface Codex offers for approvals and streamed
events), it can replace this stage: the later stages only read `work/`, `handback/` and the files in `build/`.

## Boundaries

- The receipt and evidence checks read shapes (a `$` line, a filled section, a cited file). A plausible fabricated
  evidence file passes them; that is why builder evidence is labelled and the acceptor re-runs its own checks.
- The builder's own evidence commands are not re-run automatically (they are the builder's commands, not yours).
- The Codex judge route runs read-only in an empty folder but can still read files elsewhere; only the Claude route
  has tools switched off. Headless Claude loads your user-level `CLAUDE.md` in both roles.
- Codex's workspace-write sandbox lets the builder write in `work/`, `handback/` and the system temp folders;
  whether it has network follows your Codex configuration. The Claude builder route relies on
  Claude Code's permission settings instead (`--permission-mode acceptEdits` plus any `--allow-tool` rules). In a toy
  run without `--allow-tool`, every command in which the Claude builder ran `python3` was denied; it said so in its receipt and
  the judge marked that claim insufficient.
- A verdict is one model reading the evidence once. In the example run, two judge runs on identical evidence
  disagreed about one claim (supported on builder files only). Re-run builder-only evidence, or judge more than once.
- `trust.json` sits in the run folder. It proves the handoff was not changed only if you kept the trust-root hash
  somewhere the builder could not write.

## Provenance

Own practice, 2026-09: whole lines of work handed from Claude Code to Codex through handoff packages, with a second
agent auditing the evidence afterwards. This skill joins those separate habits into one run folder and one command.
The first end-to-end run is recorded in `references/example-run/README.md`: a fix to must_mention matching in
nk-breakable-selftest, handed to Codex and judged by a separate Claude run. No external source.
