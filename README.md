# nk-two-brain

![nk-two-brain](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/social/nk-two-brain.png)

A [Claude Code](https://code.claude.com) skill. Run a coding task through two different AI agents with proof at the end: Claude writes a handoff package (goal, boundaries as orders, what the builder cannot see, acceptance checks kept from the builder), OpenAI Codex builds it in a fresh clone, the acceptor re-runs its own checks (including one with the code broken on purpose), a separate model run that did no building judges each claim from the evidence alone with exactly three verdicts (supported, not supported, insufficient), and a post draft is written from the run's files.

Part of [nickkk-skills](https://github.com/NickkkLian/nickkk-skills) — skills that stop an AI coding agent's
"done, tested, safe" from being taken on faith.

![nk-two-brain demo: before and after](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/nk-two-brain.gif)

## What it does

- `two_brain.py init / seal` sets up one run folder: a fresh clone with no remote for the builder, a handoff with boundaries written as orders and "what you cannot see", acceptance checks the builder is told not to read, and a trust-root hash kept outside.
- `build` runs OpenAI Codex (`codex exec` in its workspace-write sandbox) or, without Codex, headless Claude Code, and keeps the transcript, the diff and the builder's receipt with one evidence file per claim.
- `verify` re-runs the acceptor's own checks, including one with the change undone that must go red, and prints planned / ran / failed; NOT RUN is never a pass.
- `judge` gives a tool-less model run only the evidence bundle; it must answer supported / not supported / insufficient for every claim, and an answer that breaks the rules is rejected, not read.
- `post` drafts what happened from the run's files, every number with its source file.
- The example run is real: a fix to nk-breakable-selftest handed to Codex, re-checked, and judged by Claude, with the full transcript.

The full procedure, the boundaries and where the rules came from are in [SKILL.md](SKILL.md).

## How it works

1. Check the machine
2. Start a run
3. Write the handoff
4. Write the acceptance checks
5. Seal
6. Build

## Why it is built this way

**The idea.** The agent that did the work is the worst judge of whether it worked.

**Where it came from.** Own practice, 2026-09: whole lines of work handed from Claude Code to Codex through handoff packages, with a second agent auditing the evidence afterwards. This skill joins those separate habits into one run folder and one command.

**Evidence.** What was broken on purpose to show that the self-tests can fail is under [Verify](#verify); what was run end to end, and in which agent, is under [Compatibility](#compatibility).

## Install

Pick one of four ways: three for Claude Code, one for OpenAI Codex. Skills load when a session starts, so open a **new** session after installing.

### 1 · Terminal, one command

```bash
git clone https://github.com/NickkkLian/nk-two-brain ~/.claude/skills/nk-two-brain
```

1. Run the command above (for one project only, clone into `.claude/skills/nk-two-brain` inside that project).
2. Start a new Claude Code session.
3. Check it loaded: type `/nk-two-brain` — it appears in the slash-command menu. Or just ask for the task; the skill triggers on its own.

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
3. Check it loaded, without spending a model call: `codex debug prompt-input | grep -o -- '- nk-two-brain[a-z0-9:-]*' | sort -u` prints `- nk-two-brain:nk-two-brain:`. Codex adds the `nk-two-brain:` prefix because this repository also carries a Claude Code plugin manifest. Ask for the task and the skill triggers on its own, or type `$` and pick it from the list.

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
40 lines that record a finding or return a failing exit code, matched by a pattern rather than listed by hand
(two of them inside the self-test's stand-in builders), were neutralised one at a time; each turned the self-test red
without a traceback. 17 hand-written breaks of checks that are not such lines (the crash rule, the seal
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
