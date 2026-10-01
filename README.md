# nk-two-brain

A [Claude Code](https://code.claude.com) skill. Hand a coding task from Claude to OpenAI Codex, re-run your own checks on what comes back, and have a run that did no building judge every claim: supported, not supported or insufficient.

**What you get.** The recorded example run in `references/example-run/` (2026-09-29): Codex built a real fix, the acceptor re-ran its own checks, and a run that did no building judged every claim, twice.

![nk-two-brain: two judge runs on the same build: run 1 gives 4 supported and 2 insufficient, run 2 gives 6 supported](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/results/nk-two-brain.png)

| claim | judge run 1 | judge run 2 | run 2 rests on |
|---|---|---|---|
| C0: The goal in START.md is met, as far as this bundle shows… | supported | supported | acceptor |
| C1: The self-test passes all 22 checks and exits 0, including the mutation… | supported | supported | acceptor |
| C2: The same rule B mutation prints rule A only on a passing line; the… | supported | supported | acceptor |
| C3: In 384 judge comparisons, verdict changes were limited to CAUGHT becoming… | insufficient | supported | builder only |
| C4: README.md and SKILL.md define failure lines and state that passing lines… | supported | supported | acceptor |
| C5: git diff --check passes and the working tree lists only README.md,… | insufficient | supported | acceptor |

The builder was Codex (gpt-6.1-sol, effort medium): 179 s, 3 files changed (+33 −2). The acceptor then ran its own 5 checks, which the builder was told not to read: planned 5 / ran 5 / failed 0; check A3 puts the old code back and has to fail, and it did. Judge run 1: 4 supported, 2 insufficient. Judge run 2: 6 supported. Between the two runs one heading of the bundle was made clearer; C3 changed on evidence that had not changed, and it rests on files only the builder wrote, which the last column shows. A verdict is one model reading the evidence once: re-run builder-only evidence yourself, or judge more than once.

## Try it

Nothing is installed and nothing under `~/.claude` changes: clone, run the self-tests, run the example. It writes only `demo*` files inside the clone.

```bash
git clone https://github.com/NickkkLian/nk-two-brain && cd nk-two-brain
python3 scripts/two_brain.py --selftest
python3 scripts/two_brain.py init demo-run --repo . --name demo
python3 scripts/two_brain.py seal demo-run
cp -R references/example-run demo-example
python3 scripts/two_brain.py judge demo-example --check
```

The self-test ends on this line:

```text
✔ selftest passed (68/68)
```

The example commands print this (recorded in a fresh copy with an empty home folder; the path of the clone is taken out):

```text
$ python3 scripts/two_brain.py init demo-run --repo . --name demo
✔ run demo-run
  work: fresh clone of . at 8cad279de01f, branch two-brain/demo, no remote
  next: fill demo-run/handoff/START.md and demo-run/handoff/acceptance.json, put hidden checks in demo-run/acceptor/, then seal
$ python3 scripts/two_brain.py seal demo-run
  ✘ S1 START.md still has 4 '<<< FILL' slot(s)
  ✘ S2 acceptance.json has no items: a run with no acceptance checks has nothing to re-run
✘ not sealed
$ python3 scripts/two_brain.py judge demo-example --check
  C0   supported      The four Done-means are each covered by acceptor re-runs. A1 shows the self-test exits 0 with the new RED-ELSE
  C1   supported      The acceptor's own re-run of the self-test prints 'breakcheck selftest 22/22 passed', includes 'spec: must_men
  C2   supported      old-vs-new.txt shows the rule-B mutation output printing 'rule A' only on a passing check line while rule B fa
  C3   supported      verify_failure_lines.py iterates itertools.product over 2 control x 3 rc x 16 outputs x 4 mentions = 384 cases
  C4   supported      build/diff.patch (acceptor-collected) shows README.md adds the failure-line definition plus 'A name on a passi
  C5   supported      diff-check.txt runs 'git diff --check && git status --short'; the && chain reaching git status shows diff --ch
✔ judged 6 claims: 6 supported, 0 not supported, 0 insufficient
```

The second command exits 1 on purpose: `seal` refuses a handoff whose slots are still empty. The stages between that and a verdict (`build`, `verify`, `judge`) call Codex or Claude and spend their quota, so the last two lines use the recorded run in `references/example-run/` instead: `judge --check` reads the answer the judge gave on 2026-09-29 (`judge/raw-output.txt`), holds it to the rules a verdict has to follow, and prints the six verdicts. No model is called.

### What to type

With the skill installed ([Install](#install)), invoke it by name in Claude Code and say what to hand over:

> /nk-two-brain hand this fix to Codex and judge what comes back: [the task, in a sentence or two]

Claude Code is the host: it writes the handoff and drives the stages. Codex is the builder, and can be the judge. Whether a plain request triggers the skill without its name, and starting it from inside a Codex session, are both not tested.

![nk-two-brain](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/social/nk-two-brain.png)

Part of [nickkk-skills](https://github.com/NickkkLian/nickkk-skills) — skills that stop an AI coding agent's
"done, tested, safe" from being taken on faith.

![nk-two-brain demo: before and after](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/nk-two-brain.gif)

## What it does

- `two_brain.py init / seal` sets up one run folder: a fresh clone with no remote for the builder, a handoff with boundaries written as orders and "what you cannot see", acceptance checks the builder is told not to read, and a trust-root hash kept outside.
- `build` runs OpenAI Codex (`codex exec` in its workspace-write sandbox) or, without Codex, headless Claude Code, and keeps the transcript, the diff and the builder's receipt with one evidence file per claim.
- `verify` re-runs the acceptor's own checks, including one with the change undone that must go red, and prints planned / ran / failed; NOT RUN is never a pass.
- `judge` gives a tool-less model run only the evidence bundle; it must answer supported / not supported / insufficient for every claim, and an answer that breaks the rules is rejected, not read.
- `post` drafts what happened from the run's files, every number with its source file.
- The example run is real: a fix to nk-breakable-selftest handed to Codex, re-checked, and judged by Claude, with the full transcript. `judge references/example-run --check` re-reads the judge's saved answer and prints its six verdicts, with no model call.

The full procedure, the boundaries and where the rules came from are in [SKILL.md](SKILL.md).

## Next to codex-plugin-cc

The tool most people use today to send work from Claude Code to Codex is OpenAI's own
[codex-plugin-cc](https://github.com/openai/codex-plugin-cc). Its README (read 2026-10-01) offers `/codex:rescue` to hand Codex a
task, `/codex:review` and `/codex:adversarial-review` to have Codex review your changes, background jobs with `/codex:status` and
`/codex:result`, and an optional review gate that keeps Claude from stopping while a Codex review still finds issues. If you want
delegation or a second-model code review inside your session, use it: it is one install, OpenAI maintains it, and it does those
jobs with far less ceremony than this skill.

nk-two-brain is for a narrower question: whether to believe what came back. It adds three things that README does not describe.
The builder works in a fresh clone and is told not to read your acceptance checks; you re-run them yourself after the build, and
one of them puts the old code back and has to fail. A judge with every tool switched off reads only the evidence bundle. Each
verdict is one of three words, and says whether it rests on anything the acceptor produced or only on files the builder wrote.
The price is more steps and more quota per task. codex-plugin-cc was read, not installed or run here, and the two were not
compared on the same task.

## How it works

1. Check the machine. `python3 scripts/two_brain.py doctor` names the builder and judge it found.
2. Start a run. `two_brain.py init <run> --repo <git repo> --name <short-name> [--base REF]`.
3. Write the handoff (`handoff/START.md`).
4. Write the acceptance checks (`handoff/acceptance.json`) and put any hidden test in `acceptor/`.
5. Seal. `two_brain.py seal <run>` refuses while a slot is unfilled, then prints a trust-root hash.
6. Build. `two_brain.py build <run> [--builder codex|claude|manual] [--model M] [--effort E]`.
7. Verify. `two_brain.py verify <run> --trust-root <hash>`.
8. Judge. `two_brain.py judge <run> [--judge claude|codex|manual]`.
9. Draft the post. `two_brain.py post <run>` writes `post/draft.md` from the run's files only.
10. Accept or send back. Read `judge/verdicts.md`.

## Why it is built this way

**The idea.** The agent that did the work is the worst judge of whether it worked.

**Where it came from.** Own practice, 2026-09: whole lines of work handed from Claude Code to Codex through handoff packages, with a second agent auditing the evidence afterwards. This skill joins those separate habits into one run folder and one command.

**Evidence.** What was broken on purpose to show that the self-tests can fail is under [Verify](#verify); what was run end to end, and in which agent, is under [Compatibility](#compatibility).

## Install

Pick one of four ways: three for Claude Code, and one that puts the folder where OpenAI Codex reads skills. Claude Code is the tested host; Codex was tested as the builder and as a judge, not as the session the skill starts from. Skills load when a session starts, so open a **new** session after installing.

### 1 · Terminal, one command

```bash
git clone https://github.com/NickkkLian/nk-two-brain ~/.claude/skills/nk-two-brain
```

1. Run the command above (for one project only, clone into `.claude/skills/nk-two-brain` inside that project).
2. Start a new Claude Code session.
3. Check it loaded: type `/nk-two-brain` — it appears in the slash-command menu. Invoke it by that name: whether a plain request triggers it has not been tested.

### 2 · Claude Code in a terminal session (plugin)

The plugin route goes through the [nickkk-skills](https://github.com/NickkkLian/nickkk-skills) marketplace. Add it once; after that each skill is one command.

```
/plugin marketplace add NickkkLian/nickkk-skills
/plugin install nk-two-brain@nickkk-skills
```

1. In a Claude Code session, run the first line (once per machine).
2. Run the second line.
3. Start a new session (or run `/reload-plugins`). The skill shows up as `nk-two-brain:nk-two-brain`.

Without opening a session, the same two steps work from a shell: `claude plugin marketplace add NickkkLian/nickkk-skills` then `claude plugin install nk-two-brain@nickkk-skills`.

### 3 · Claude desktop app (Code tab)

**Add the marketplace first — Discover only searches marketplaces you have already added.**

<img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/panel-route.gif" alt="Adding the marketplace and installing a skill in the desktop app" width="640">

<sub>Recorded on 2026-09-16, when the marketplace listed ten skills, all at version 0.1.0; it lists more now. The repository list in this recording shows the recorder's own repositories because a GitHub account is connected; yours will show yours. Type the full name as in step 4.</sub>

1. In the chat box, type `/plugin marketplace` and press Enter (or open **Settings → Customize → Plugins**). The **Plugins** panel opens.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step1-type-plugin-marketplace.png" alt="/plugin marketplace typed in the chat box" width="480">
2. Top right, open **Add ▾** and choose **Add marketplace**.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step2-add-menu.png" alt="The Add menu with Add marketplace" width="480">
3. Choose **Add from a repository**.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step3-add-from-repository.png" alt="Add marketplace dialog: Add from a repository" width="480">
4. In **URL**, type the full `NickkkLian/nickkk-skills`. At the bottom of the list choose the row **Use "NickkkLian/nickkk-skills"**, then press **Sync**.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step4-url-then-sync.png" alt="URL filled in, Sync button" width="480">
5. You land on **Discover**, filtered to the new marketplace (**Filter · 1**). Find **Nk two brain** and press **Add**. Installed ones show **✓ Added**.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step5-discover-add.png" alt="Discover list with Added and Add buttons" width="480">
6. Close the panel and start a new session.

To try it for one session without installing anything: `claude --plugin-dir ./nk-two-brain` from a clone.

### 4 · OpenAI Codex CLI

```bash
git clone https://github.com/NickkkLian/nk-two-brain.git ~/.agents/skills/nk-two-brain
```

1. Run the command above (for one project only, clone into `.agents/skills/nk-two-brain` inside that project).
2. Start a new Codex session.
3. Check it loaded, without spending a model call: `codex debug prompt-input | grep -o -- '- nk-two-brain[a-z0-9:-]*' | sort -u` prints `- nk-two-brain:nk-two-brain:`. Codex adds the `nk-two-brain:` prefix because this repository also carries a Claude Code plugin manifest. Starting this skill from inside a Codex session has not been tested.

## Compatibility

| Agent | Tested | What was checked |
|---|---|---|
| Claude Code (CLI 2.1.173, macOS) | partly | The example run was driven from a Claude Code session through its shell tool, every stage in order; the judge was a headless `claude -p` run with tools switched off. With Codex hidden from the script, a toy task also ran with headless Claude Code as the builder and as the judge. Not tested: whether a plain request in a fresh session triggers the skill without naming it. |
| OpenAI Codex CLI (0.159.0, gpt-6.1-sol, medium, macOS) | as builder and judge | Codex built the example task through `codex exec` in the run's clone, and judged the same evidence through the Codex judge route. The skill was not loaded into a Codex session, so starting the skill from Codex is not tested. |
| Cursor, Gemini CLI | no | Not tested. |

This skill's frontmatter uses only name, description, license and metadata.

## Verify

```bash
python3 scripts/two_brain.py --selftest
```

Python 3.9+, standard library only; needs git. Two break matrices were run on two_brain.py in a sandbox copy.
41 lines that record a finding or return a failing exit code, matched by a pattern rather than listed by hand
(two of them inside the self-test's stand-in builders), were neutralised one at a time; each turned the self-test red
without a traceback. 19 hand-written breaks of checks that are not such lines (the crash rule, the seal
comparison, the judge's switched-off tools, the bundle's file list, the untracked-file diff, among others) each turned
the self-test red, and each named its own check on a failing line. The unmutated control stayed green both times.

## Limits

- The receipt and evidence checks read shapes (a `$` line, a filled section, a cited file). A plausible fabricated evidence file passes them; that is why builder evidence is labelled and the acceptor re-runs its own checks.
- The builder's own evidence commands are not re-run automatically (they are the builder's commands, not yours).
- The Codex judge route runs read-only in an empty folder but can still read files elsewhere; only the Claude route has tools switched off. Headless Claude loads your user-level `CLAUDE.md` in both roles.
- Codex's workspace-write sandbox lets the builder write in `work/`, `handback/` and the system temp folders; whether it has network follows your Codex configuration. The Claude builder route relies on Claude Code's permission settings instead (`--permission-mode acceptEdits` plus any `--allow-tool` rules). In a toy run without `--allow-tool`, every command in which the Claude builder ran `python3` was denied; it said so in its receipt and the judge marked that claim insufficient.
- A verdict is one model reading the evidence once. In the example run, two judge runs on identical evidence disagreed about one claim (supported on builder files only). Re-run builder-only evidence, or judge more than once.
- `trust.json` sits in the run folder. It proves the handoff was not changed only if you kept the trust-root hash somewhere the builder could not write.

## License

MIT. Read a script before letting it run in your environment.
