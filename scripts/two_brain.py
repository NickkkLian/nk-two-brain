#!/usr/bin/env python3
"""two_brain.py — one brain writes the handoff, another builds, a third run that did no building judges the evidence.

    python3 two_brain.py doctor                                   which builders and judges this machine has
    python3 two_brain.py init   <run> --repo <git repo> --name <n> [--base REF]
    python3 two_brain.py seal   <run>                             refuses while a <<< FILL slot is left
    python3 two_brain.py build  <run> [--builder codex|claude|manual] [--model M] [--effort E] [--timeout S]
                                      [--allow-tool RULE ...]   Claude builder only, e.g. 'Bash(python3 *)'
    python3 two_brain.py verify <run> [--trust-root SHA256]       re-runs the acceptance checks itself
    python3 two_brain.py judge  <run> [--judge claude|codex|manual] [--model M] [--effort E] [--check]
    python3 two_brain.py post   <run>                             a launch-post draft built only from the run's files
    python3 two_brain.py status <run>
    python3 two_brain.py --selftest

A run folder holds everything, and the builder is only ever pointed at two of its sub-folders:
  handoff/START.md, acceptance.json   written by the handing-out brain; sealed by trust.json
  acceptor/                           acceptance material the builder is told not to read (hidden tests, expected output)
  work/                               a fresh clone of the repo at the base commit, origin removed: the builder works here
  handback/RECEIPT.md, evidence/      the builder's claims and its own evidence ("$ command" first line, then raw output)
  build/  verify/  judge/  post/      one folder per stage, raw files only

Exit codes: 0 ok · 1 findings (a check failed, the trust root does not match, a stage is incomplete)
· 2 crashed or invalid (a judge answer that breaks the rules is never read as a verdict) · 4 no builder/judge CLI found
(the prompt is written so a person or another agent can do that stage by hand).
Standard library only, Python 3.9+.
"""
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

VERDICTS = ("supported", "not supported", "insufficient")
FILL = "<<< FILL"
EVIDENCE_CAP, DIFF_CAP = 40_000, 60_000
CODEX_APP = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"   # the Codex CLI bundled with the ChatGPT app on macOS
CLAIM_RE = re.compile(r"^- (C[1-9]\d*): (.+?)\s*\|\s*evidence:\s*(.+?)\s*$")

START_TEMPLATE = """# Handoff: {name}

## Goal
<<< FILL: one paragraph. What must be true when you are done, in words a stranger could check. >>>

## Boundaries (orders, each with its reason)
- Work only inside `{work}`. Write your receipt and evidence only inside `{handback}`. Reason: everything else belongs to someone else's line of work; a helpful write there overwrites it silently.
- Do not commit, push, tag or add remotes. Leave your changes in the working tree. Reason: the acceptor reviews the diff and commits it; a push cannot be taken back.
- Do not read `{acceptor}`. Reason: it holds the acceptance checks; they stay independent only if the work was not shaped to them.
<<< FILL: any task-specific orders (files not to touch, dependencies not to add), each with its reason. Write "none" if there are none. >>>

## What you cannot see
<<< FILL: the context the builder has no way to know — history, conventions, why the task exists, what was tried before. >>>

## Done means
<<< FILL: the observable end state, as a short list. >>>
"""

RECEIPT_TEMPLATE = """# Receipt

## Claims
<<< FILL: one line per claim, exactly:  - C1: <one checkable sentence> | evidence: <file in evidence/>, <file> >>>

## How I verified
<<< FILL >>>

## Unsure
<<< FILL: what you are not sure of. Write "none" only if that is true. >>>

## Boundary crossings
<<< FILL: anything you did outside the boundaries, or "none". >>>
"""

ACCEPT_TEMPLATE = {"items": [], "_help": (
    "Each item: {id, cmd, expect: pass|fail, timeout?, break?}. cmd runs with a shell, cwd = {root}. "
    "Placeholders: {root} (the work folder, or the temporary broken copy), {acceptor}, {run}. "
    "break: {revert: path} puts back the base version of that file, or {file, find, replace} with find occurring exactly "
    "once; it is applied to a temporary copy of the work folder and the command must then FAIL (the check can go red).")}

HANDBACK_RULES = """

---
## Hand-back rules (added by two_brain.py; the same for every run)
- Your working folder: `{work}`. Your receipt: `{handback}/RECEIPT.md` (already there as a template; replace every `<<< FILL` slot).
- Evidence: one file per claim in `{handback}/evidence/`. First line `$ <the exact command, re-runnable from {work}>`, then the command's raw output, unedited. A summary is not evidence.
- Each claim in the receipt is one line: `- C1: <sentence> | evidence: <file>, <file>` (a file name in evidence/, with or without the `evidence/` prefix). Claim only what your evidence shows.
- "Unsure" is the most useful section. Empty means unfilled, not confident.
- A separate model that did not see your work will judge each claim from the evidence alone: supported, not supported or insufficient. The acceptor also re-runs its own checks.
- If you need an answer to continue, stop and write the question as the last line of your final message.
"""

JUDGE_BRIEF = """You are the judge. You did not do this work, you will not fix anything, and you have no tools: everything you may
use is in the bundle below. For each claim answer one question only: does the evidence in this bundle prove this sentence?

Rules:
1. Read only the bundle. The builder's wording and confidence are the object under review, not evidence.
2. Each verdict is exactly one of: "supported", "not supported", "insufficient". There is no fourth.
   - supported: cite the file(s) and the lines that prove the words of the claim. If you cannot point, it is not supported.
   - not supported: cite the lines that contradict the claim.
   - insufficient: say what is missing and which single artefact would settle it (field would_settle).
3. Files marked BUILDER-SUPPLIED were written by the builder and were not re-run by anyone; files marked RE-RUN BY
   ACCEPTOR were produced by the acceptor running its own commands after the build. Weigh them accordingly.
4. A file marked [truncated] may hide the deciding lines; if it does, the verdict is insufficient.
5. "Looks fine", "probably", "should be" are insufficient.
6. Judge every claim id listed under CLAIMS exactly once, C0 included. Cite files only by the names shown in the bundle.
Answer with JSON only: {"claims":[{"id","verdict","why","evidence":[file names],"would_settle"}]}.
"""

JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["claims"], "properties": {"claims": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["id", "verdict", "why", "evidence", "would_settle"],
                               "properties": {"id": {"type": "string"}, "verdict": {"type": "string", "enum": list(VERDICTS)},
                                              "why": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}},
                                              "would_settle": {"type": "string"}}}}}}


# ── small helpers ───────────────────────────────────────────────────────────────────────────────────
def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def rd(p, default=""):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return default


def wr(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, p)


def paths(run):
    run = os.path.abspath(run)
    j = lambda *a: os.path.join(run, *a)
    return {"run": run, "handoff": j("handoff"), "start": j("handoff", "START.md"), "accept": j("handoff", "acceptance.json"),
            "acceptor": j("acceptor"), "work": j("work"), "handback": j("handback"), "receipt": j("handback", "RECEIPT.md"),
            "evidence": j("handback", "evidence"), "build": j("build"), "verify": j("verify"), "judge": j("judge"),
            "post": j("post"), "trust": j("trust.json"), "meta": j("run.json")}


def git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def meta(P, **upd):
    m = json.loads(rd(P["meta"], "{}") or "{}")
    if upd:
        m.update(upd); wr(P["meta"], json.dumps(m, indent=2, ensure_ascii=False) + "\n")
    return m


def child_env():
    """Environment for a child claude/codex process. A Claude Code session exports its own CLAUDE_CODE_* variables and
    may point ANTHROPIC_BASE_URL at itself; a child that inherits them talks to the parent instead of starting fresh."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_") and k not in ("CLAUDECODE",)}
    if "CLAUDECODE" in os.environ or "CLAUDE_CODE_ENTRYPOINT" in os.environ:
        env.pop("ANTHROPIC_BASE_URL", None)
    return env


def find_cli(name):
    """Env override first (TWO_BRAIN_CODEX / TWO_BRAIN_CLAUDE; an empty value means 'pretend it is not installed'),
    then PATH, then the usual install places."""
    key = "TWO_BRAIN_" + name.upper()
    if key in os.environ:
        v = os.environ[key]
        return v if v and os.access(v, os.X_OK) else None
    hit = shutil.which(name)
    if hit:
        return hit
    for c in ([CODEX_APP] if name == "codex" else [os.path.expanduser("~/.local/bin/claude")]):
        if os.access(c, os.X_OK):
            return c
    return None


# ── doctor ──────────────────────────────────────────────────────────────────────────────────────────
def plan_roles():
    codex, claude = find_cli("codex"), find_cli("claude")
    builder = "codex" if codex else ("claude" if claude else "manual")
    judge = "claude" if claude else ("codex" if codex else "manual")
    notes = []
    if not codex:
        notes.append("Codex CLI not found: the build falls back to " + ("headless Claude Code (a second vendor is better: "
                     "the builder and the judge then share one model family)" if claude else "a manual build (prompt written to build/prompt.md)"))
    if not claude:
        notes.append("Claude Code CLI not found: the judge runs " + ("in Codex, read-only" if codex else "by hand (judge/brief.md + bundle.md)"))
    return {"codex": codex, "claude": claude, "builder": builder, "judge": judge, "notes": notes}


def cmd_doctor(a):
    r = plan_roles()
    print(f"codex : {r['codex'] or 'not found'}")
    print(f"claude: {r['claude'] or 'not found'}")
    print(f"default builder: {r['builder']} · default judge: {r['judge']}")
    for n in r["notes"]:
        print("note: " + n)
    return 0


# ── init / seal ─────────────────────────────────────────────────────────────────────────────────────
def cmd_init(a):
    P = paths(a.run)
    if os.path.exists(P["run"]) and os.listdir(P["run"]):
        print(f"✘ {P['run']} is not empty; init never writes over a run"); return 1
    repo = os.path.abspath(a.repo)
    base = git("rev-parse", a.base, cwd=repo).strip()
    os.makedirs(P["run"], exist_ok=True)
    git("clone", "--quiet", "--no-hardlinks", repo, P["work"])
    git("checkout", "--quiet", "-b", f"two-brain/{a.name}", base, cwd=P["work"])
    git("remote", "remove", "origin", cwd=P["work"])     # nothing to push to, by construction
    for d in ("handoff", "acceptor", "evidence", "build", "verify", "judge", "post"):
        os.makedirs(P[d], exist_ok=True)
    wr(P["start"], START_TEMPLATE.format(name=a.name, work=P["work"], handback=P["handback"], acceptor=P["acceptor"]))
    wr(P["accept"], json.dumps(ACCEPT_TEMPLATE, indent=2) + "\n")
    wr(P["receipt"], RECEIPT_TEMPLATE)
    meta(P, name=a.name, repo=repo, base=base, created=now())
    print(f"✔ run {P['run']}\n  work: fresh clone of {repo} at {base[:12]}, branch two-brain/{a.name}, no remote\n"
          f"  next: fill {P['start']} and {P['accept']}, put hidden checks in {P['acceptor']}/, then seal")
    return 0


def trust_files(P):
    out = [P["start"], P["accept"]]
    for root, _, files in os.walk(P["acceptor"]):
        out += [os.path.join(root, f) for f in sorted(files) if f != ".DS_Store" and "__pycache__" not in root]
    return sorted(out)


def load_accept(P):
    items = json.loads(rd(P["accept"], "{}") or "{}").get("items", [])
    return items if isinstance(items, list) else []


def cmd_seal(a):
    P = paths(a.run)
    probs = []
    if FILL in rd(P["start"]):
        probs.append(("S1", f"START.md still has {rd(P['start']).count(FILL)} '<<< FILL' slot(s)"))
    items = load_accept(P)
    if not items:
        probs.append(("S2", "acceptance.json has no items: a run with no acceptance checks has nothing to re-run"))
    for it in items:
        if not isinstance(it, dict) or not it.get("id") or not it.get("cmd") or it.get("expect") not in ("pass", "fail"):
            probs.append(("S3", f"acceptance item needs id, cmd and expect pass|fail: {it!r}"))
        elif it.get("break") and it.get("expect") != "fail":
            probs.append(("S4", f"{it['id']}: a break item must expect fail (with the code broken, the check has to go red)"))
    if probs:
        for code, msg in probs:
            print(f"  ✘ {code} {msg}")
        print("✘ not sealed"); return 1
    t = {"sealed": now(), "files": {os.path.relpath(f, P["run"]): sha(f) for f in trust_files(P)}}
    wr(P["trust"], json.dumps(t, indent=2) + "\n")
    print(f"✔ sealed {len(t['files'])} files\ntrust-root sha256: {sha(P['trust'])}\n"
          "  keep that line somewhere the builder cannot write (the chat is fine) and pass it to verify --trust-root")
    return 0


def trust_problems(P, root_sha=None):
    probs = []
    if not os.path.isfile(P["trust"]):
        return [("T1", "not sealed: trust.json missing")]
    if root_sha and sha(P["trust"]) != root_sha:
        probs.append(("T2", "trust.json does not match the trust root you kept"))
    t = json.loads(rd(P["trust"]))
    now_files = {os.path.relpath(f, P["run"]): sha(f) for f in trust_files(P)}
    for rel, h in t["files"].items():
        if now_files.get(rel) != h:
            probs.append(("T3", f"changed or missing since seal: {rel}"))
    for rel in sorted(set(now_files) - set(t["files"])):
        probs.append(("T4", f"added since seal: {rel}"))
    return probs


# ── build ───────────────────────────────────────────────────────────────────────────────────────────
def builder_prompt(P):
    return rd(P["start"]) + HANDBACK_RULES.format(work=P["work"], handback=P["handback"])


def render_codex(lines):
    out, counts = [], {"commands": 0, "file_changes": 0, "messages": 0}
    for l in lines:
        try:
            ev = json.loads(l)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "item.completed":
            it = ev.get("item", {}); typ = it.get("type")
            if typ == "agent_message":
                counts["messages"] += 1; out.append("assistant: " + it.get("text", "").strip())
            elif typ == "command_execution":
                counts["commands"] += 1
                out.append(f"$ {it.get('command', '')}\n  (exit {it.get('exit_code')})\n"
                           + "\n".join("  | " + x for x in str(it.get("aggregated_output", "")).splitlines()[-40:]))
            elif typ == "file_change":
                counts["file_changes"] += 1
                out.append("edit: " + ", ".join(f"{c.get('kind', '?')} {c.get('path', '?')}" for c in it.get("changes", [])))
            elif typ != "reasoning":
                out.append(f"[{typ}]")
        elif t in ("error", "turn.failed"):
            out.append(f"ERROR: {json.dumps(ev)[:500]}")
        elif t == "turn.completed":
            out.append(f"[turn completed] usage {json.dumps(ev.get('usage', {}))}")
    return "\n\n".join(out) + "\n", counts


def render_claude(lines):
    out, counts, last, denials = [], {"commands": 0, "file_changes": 0, "messages": 0}, "", []
    for l in lines:
        try:
            ev = json.loads(l)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "text":
                    counts["messages"] += 1; out.append("assistant: " + b.get("text", "").strip())
                elif b.get("type") == "tool_use":
                    name, inp = b.get("name"), b.get("input", {})
                    if name == "Bash":
                        counts["commands"] += 1
                    elif name in ("Edit", "Write", "MultiEdit"):
                        counts["file_changes"] += 1
                    out.append(f"tool {name}: {json.dumps(inp, ensure_ascii=False)[:400]}")
        elif ev.get("type") == "result":
            last = ev.get("result", "") or ""; denials = ev.get("permission_denials", []) or []
            out.append(f"[result] {ev.get('subtype')} turns={ev.get('num_turns')}")
    if denials:
        out.append("permission denials:\n" + json.dumps(denials, indent=1)[:3000])
    return "\n\n".join(out) + "\n", counts, last


def collect_diff(P):
    base = meta(P)["base"]
    tracked = git("diff", "--binary", base, cwd=P["work"])
    untracked = [f for f in git("ls-files", "--others", "--exclude-standard", cwd=P["work"]).splitlines() if f]
    parts = [tracked]
    for f in untracked:
        r = subprocess.run(["git", "diff", "--no-index", "--binary", "/dev/null", f], cwd=P["work"], capture_output=True, text=True)
        parts.append(r.stdout)
    patch = "".join(parts)
    changed = sorted(set(re.findall(r"^\+\+\+ b/(.+)$", patch, re.M)) | set(re.findall(r"^--- a/(.+)$", patch, re.M)) - {"/dev/null"})
    added = sum(1 for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in patch.splitlines() if l.startswith("-") and not l.startswith("---"))
    wr(os.path.join(P["build"], "diff.patch"), patch)
    stat = {"files_changed": len(changed), "lines_added": added, "lines_removed": removed, "files": changed}
    wr(os.path.join(P["build"], "diff-stat.json"), json.dumps(stat, indent=2) + "\n")
    return stat


def cmd_build(a):
    P = paths(a.run)
    probs = trust_problems(P)
    if probs:
        for c, m in probs:
            print(f"  ✘ {c} {m}")
        print("✘ seal the handoff before building"); return 1
    roles = plan_roles()
    builder = a.builder or roles["builder"]
    prompt = builder_prompt(P)
    wr(os.path.join(P["build"], "prompt.md"), prompt)
    exe = find_cli(builder) if builder in ("codex", "claude") else None
    if builder == "manual" or not exe:
        print(("✘ no builder CLI found" if builder != "manual" else "manual build") +
              f"\n  hand {P['build']}/prompt.md to a person or an agent working in {P['work']};\n"
              f"  they fill {P['receipt']} and {P['evidence']}/, then run: two_brain.py verify {P['run']}")
        meta(P, builder="manual", build_started=now())
        return 4 if builder != "manual" else 0
    if builder == "codex":
        cmd = [exe, "exec", "--json", "-s", "workspace-write", "-C", P["work"], "--add-dir", P["handback"],
               "--skip-git-repo-check", "-o", os.path.join(P["build"], "last-message.md")]
        if a.model: cmd += ["-m", a.model]
        if a.effort: cmd += ["-c", f"model_reasoning_effort={a.effort}"]
        cmd += ["-"]
    else:
        cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
               "--add-dir", P["handback"]]
        if a.model: cmd += ["--model", a.model]
        if a.effort: cmd += ["--effort", a.effort]
        for t in a.allow_tool or []:        # headless Claude cannot ask anyone: commands the task needs must be allowed up front
            cmd += ["--allowedTools", t]
    wr(os.path.join(P["build"], "command.txt"), " ".join(cmd) + "   (prompt on stdin: build/prompt.md)\n")
    t0 = time.time(); started = now()
    with open(os.path.join(P["build"], "events.jsonl"), "w") as out, open(os.path.join(P["build"], "stderr.txt"), "w") as err:
        try:
            r = subprocess.run(cmd, input=prompt, stdout=out, stderr=err, text=True, cwd=P["work"], env=child_env(), timeout=a.timeout)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = 124
    lines = rd(os.path.join(P["build"], "events.jsonl")).splitlines()
    if builder == "codex":
        text, counts = render_codex(lines)
    else:
        text, counts, last = render_claude(lines)
        wr(os.path.join(P["build"], "last-message.md"), last)
    wr(os.path.join(P["build"], "transcript.md"), text)
    stat = collect_diff(P)
    info = {"builder": builder, "exit": rc, "started": started, "seconds": round(time.time() - t0), **counts,
            "model": a.model or "(CLI default)", "effort": a.effort or "(CLI default)"}
    wr(os.path.join(P["build"], "meta.json"), json.dumps(info, indent=2) + "\n")
    meta(P, builder=builder, build_exit=rc)
    print(f"{'✔' if rc == 0 else '✘'} {builder} exited {rc} after {info['seconds']} s · {counts['commands']} commands · "
          f"diff: {stat['files_changed']} files, +{stat['lines_added']} -{stat['lines_removed']}")
    last_line = (rd(os.path.join(P["build"], "last-message.md")).strip().splitlines() or [""])[-1]
    if last_line.endswith("?"):
        print(f"  the builder ended on a question: {last_line}\n  answer it, then build again or finish by hand")
    return 0 if rc == 0 else 1


# ── verify ──────────────────────────────────────────────────────────────────────────────────────────
def receipt_problems(P):
    probs, text = [], rd(P["receipt"])
    if not text:
        return [("R1", "no RECEIPT.md in handback/")], []
    if text.strip() == RECEIPT_TEMPLATE.strip():
        return [("R2", "RECEIPT.md is the untouched template")], []
    claims = []
    for line in text.splitlines():
        m = CLAIM_RE.match(line.strip())
        if m:
            # cited by bare name or as evidence/<name> (both seen from real builders); stored as evidence/<name>
            files = [f.strip().strip("`") for f in m.group(3).split(",") if f.strip()]
            files = ["evidence/" + (f[len("evidence/"):] if f.startswith("evidence/") else f) for f in files]
            claims.append({"id": m.group(1), "text": m.group(2).strip(), "evidence": files})
    if not claims:
        probs.append(("R3", "receipt has no claims in the form '- C1: <sentence> | evidence: <file>'"))
    ids = [c["id"] for c in claims]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        probs.append(("R4", f"claim id {dup} is used twice"))
    for c in claims:
        for f in c["evidence"]:
            name = f[len("evidence/"):]
            p = os.path.join(P["evidence"], name)
            if os.path.dirname(os.path.normpath(name)) or not os.path.isfile(p):
                probs.append(("R5", f"{c['id']} cites {f}, which is not a file in handback/evidence/"))
            elif not rd(p).startswith("$ "):
                probs.append(("R6", f"{f}: first line is not '$ <command>'"))
    sec = re.search(r"^## Unsure\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not sec or not sec.group(1).strip() or FILL in sec.group(1):
        probs.append(("R7", "the Unsure section is empty or unfilled (write 'none' only if that is true)"))
    if FILL in text:
        probs.append(("R8", f"receipt still has {text.count(FILL)} '<<< FILL' slot(s)"))
    return probs, claims


def base_version(P, rel):
    r = subprocess.run(["git", "show", f"{meta(P)['base']}:{rel}"], cwd=P["work"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def run_item(P, it):
    """Returns (status, detail, text). status: PASS / FAIL / NOT RUN."""
    brk, tmp = it.get("break"), None
    root = P["work"]
    if brk:
        tmp = tempfile.mkdtemp(prefix="two_brain_break_")
        root = os.path.join(tmp, "root")
        shutil.copytree(P["work"], root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        if "revert" in brk:
            rel = brk["revert"]; old = base_version(P, rel); target = os.path.join(root, rel)
            if old is None and not os.path.exists(target):
                shutil.rmtree(tmp, ignore_errors=True)
                return "NOT RUN", f"revert {rel}: the file exists neither at base nor now", ""
            if old is None:
                os.remove(target)
            else:
                open(target, "wb").write(old)
            how = f"revert {rel} to the base commit"
        else:
            target = os.path.join(root, brk.get("file", ""))
            s = rd(target); n = s.count(brk.get("find", "\0")) if brk.get("find") else 0
            if n != 1:
                shutil.rmtree(tmp, ignore_errors=True)
                return "NOT RUN", f"break anchor occurs {n} times in {brk.get('file')} (need exactly 1)", ""
            open(target, "w", encoding="utf-8").write(s.replace(brk["find"], brk.get("replace", ""), 1))
            how = f"replace one anchor in {brk['file']}"
    try:
        cmd = it["cmd"].format(root=root, acceptor=P["acceptor"], run=P["run"])
    except (KeyError, IndexError) as e:
        if tmp: shutil.rmtree(tmp, ignore_errors=True)
        return "NOT RUN", f"unknown placeholder {e} in cmd", ""
    try:
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=it.get("timeout", 300))
        rc, out = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        rc, out = 124, "TIMEOUT"
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    text = f"$ {cmd}\n{out}" + ("" if out.endswith("\n") or not out else "\n") + \
           f"# exit {rc} · cwd {'a temporary copy of work/ with the break applied: ' + how if brk else 'work/'}\n"
    crashed = "Traceback (most recent call last)" in out
    if it["expect"] == "pass":
        ok = rc == 0
    else:
        ok = rc != 0 and not crashed and rc != 124
    detail = f"exit {rc}" + (" (a crash, not a detection)" if crashed and it["expect"] == "fail" else "")
    return ("PASS" if ok else "FAIL"), detail, text


def cmd_verify(a):
    P = paths(a.run)
    rows, probs = [], trust_problems(P, a.trust_root)
    rprobs, claims = receipt_problems(P)
    for f in os.listdir(P["verify"]) if os.path.isdir(P["verify"]) else []:
        if f.endswith(".txt"):
            os.remove(os.path.join(P["verify"], f))   # results of an earlier verify must never reach the judge as this one's
    # an unsealed run, or one whose acceptance list changed after the seal, is not run: its results would prove the wrong thing
    skip = any(c == "T1" or (c == "T3" and m.endswith("acceptance.json")) for c, m in probs)
    items = [] if skip else load_accept(P)
    for it in items:
        status, detail, text = run_item(P, it)
        if text:
            wr(os.path.join(P["verify"], f"{it['id']}.txt"), text)
        rows.append({"id": it["id"], "expect": it["expect"], "break": bool(it.get("break")), "status": status, "detail": detail})
    planned = len(load_accept(P)) if os.path.isfile(P["accept"]) else 0
    ran = sum(1 for r in rows if r["status"] != "NOT RUN")
    failed = sum(1 for r in rows if r["status"] != "PASS") + (planned - len(rows))
    for c, m in probs + rprobs:
        print(f"  ✘ {c} {m}")
    for r in rows:
        print(f"  {'✔' if r['status'] == 'PASS' else '✘'} {r['id']:<4} {r['status']:<8} expect {r['expect']}"
              f"{' (break)' if r['break'] else ''} · {r['detail']}")
    summary = {"when": now(), "planned": planned, "ran": ran, "failed": failed, "items": rows,
               "trust": [m for _, m in probs], "receipt": [m for _, m in rprobs], "claims": claims}
    wr(os.path.join(P["verify"], "summary.json"), json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    bad = failed or probs or rprobs
    print(f"{'✘' if bad else '✔'} planned {planned} / ran {ran} / failed {failed}"
          f" · trust {'FAIL' if probs else 'ok'} · receipt {len(rprobs)} problem(s) · {len(claims)} claim(s)")
    return 1 if bad else 0


# ── judge ───────────────────────────────────────────────────────────────────────────────────────────
def capped(text, cap):
    b = text.encode("utf-8")
    if len(b) <= cap:
        return text
    return b[:cap].decode("utf-8", "ignore") + f"\n[truncated: {cap} of {len(b)} bytes shown]\n"


def build_bundle(P):
    """The judge sees exactly these files and nothing else. Returns (markdown, claim list, file names)."""
    s = json.loads(rd(os.path.join(P["verify"], "summary.json"), "{}") or "{}")
    claims = [{"id": "C0", "text": "The goal in START.md is met, as far as this bundle shows (claim added by the acceptor).",
               "evidence": []}] + s.get("claims", [])
    files = []
    parts = [JUDGE_BRIEF, "\n# BUNDLE\n", "## TASK (START.md, written by the acceptor)\n", rd(P["start"]),
             "\n## ACCEPTANCE CHECKS (acceptance.json)\n", "```json\n" + rd(P["accept"]) + "```\n", "\n## CLAIMS\n"]
    parts += [f"- {c['id']}: {c['text']}" + (f"  (builder cites: {', '.join(c['evidence'])})" if c["evidence"] else "") + "\n" for c in claims]
    parts.append("\n## RECEIPT (BUILDER-SUPPLIED)\n" + rd(P["receipt"]) + "\n")
    handed = []                                   # everything the builder handed back: evidence files first, then helpers
    for root, dirs, fs in os.walk(P["handback"]):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        handed += [os.path.relpath(os.path.join(root, f), P["handback"]) for f in sorted(fs) if f not in (".DS_Store",)]
    handed = sorted((f for f in handed if f != "RECEIPT.md"), key=lambda f: (not f.startswith("evidence/"), f))
    for f in handed:
        files.append(f)
        parts.append(f"\n## FILE {f} — BUILDER-SUPPLIED, not re-run\n```\n{capped(rd(os.path.join(P['handback'], f)), EVIDENCE_CAP)}```\n")
    for f in sorted(os.listdir(P["verify"])) if os.path.isdir(P["verify"]) else []:
        p = os.path.join(P["verify"], f)
        if f.endswith(".txt") and os.path.isfile(p):
            name = "verify/" + f; files.append(name)
            parts.append(f"\n## FILE {name} — RE-RUN BY ACCEPTOR after the build\n```\n{capped(rd(p), EVIDENCE_CAP)}```\n")
    if s:
        files.append("verify/summary.json")
        parts.append("\n## FILE verify/summary.json — RE-RUN BY ACCEPTOR\n```json\n" +
                     json.dumps({k: s[k] for k in ("planned", "ran", "failed", "items", "trust", "receipt")}, indent=1) + "\n```\n")
    diff = rd(os.path.join(P["build"], "diff.patch"))
    files.append("build/diff.patch")
    parts.append("\n## FILE build/diff.patch — the builder's change, collected by the acceptor after the build: `git diff <base>` "
                 "for tracked files plus one new-file diff per untracked file (`git ls-files --others --exclude-standard`), "
                 "so a file the builder created and left untracked appears here too\n```diff\n" + capped(diff, DIFF_CAP) + "```\n")
    return "".join(parts), claims, files


def validate_verdicts(obj, claims, files):
    probs = []
    if not isinstance(obj, dict) or not isinstance(obj.get("claims"), list):
        return [("J1", "answer is not {\"claims\": [...]}")]
    want = [c["id"] for c in claims]
    got = [v.get("id") for v in obj["claims"] if isinstance(v, dict)]
    for i in want:
        if got.count(i) == 0:
            probs.append(("J2", f"claim {i} was not judged"))
        elif got.count(i) > 1:
            probs.append(("J3", f"claim {i} was judged {got.count(i)} times"))
    for i in sorted(set(g for g in got if g not in want), key=str):
        probs.append(("J4", f"verdict for a claim that does not exist: {i}"))
    for v in obj["claims"]:
        if not isinstance(v, dict):
            probs.append(("J1", f"not an object: {v!r}")); continue
        if v.get("verdict") not in VERDICTS:
            probs.append(("J5", f"{v.get('id')}: verdict {v.get('verdict')!r} is not one of the three"))
        if not str(v.get("why", "")).strip():
            probs.append(("J6", f"{v.get('id')}: no reason given"))
        cited = v.get("evidence") or []
        if v.get("verdict") in ("supported", "not supported") and not cited:
            probs.append(("J7", f"{v.get('id')}: '{v.get('verdict')}' must cite at least one file"))
        for f in cited:
            if f not in files:
                probs.append(("J8", f"{v.get('id')}: cites {f!r}, which is not in the bundle"))
        if v.get("verdict") == "insufficient" and not str(v.get("would_settle", "")).strip():
            probs.append(("J9", f"{v.get('id')}: 'insufficient' must say what would settle it"))
    return probs


def parse_judge_output(raw):
    """claude --output-format json puts the schema answer in structured_output; codex -o writes the JSON itself."""
    try:
        obj = json.loads(raw)
    except ValueError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            return None
    if isinstance(obj, dict) and "structured_output" in obj:
        return obj["structured_output"]
    if isinstance(obj, dict) and obj.get("type") == "result" and isinstance(obj.get("result"), str):
        return parse_judge_output(obj["result"])
    return obj


def cmd_judge(a):
    P = paths(a.run)
    if not os.path.isfile(os.path.join(P["verify"], "summary.json")):
        print("✘ run verify first: the judge reads the acceptor's re-run results"); return 1
    bundle, claims, files = build_bundle(P)
    wr(os.path.join(P["judge"], "bundle.md"), bundle)
    wr(os.path.join(P["judge"], "schema.json"), json.dumps(JUDGE_SCHEMA, indent=1) + "\n")
    raw_p = os.path.join(P["judge"], "raw-output.txt")
    judge = a.judge or plan_roles()["judge"]
    if not a.check:
        builder = meta(P).get("builder")
        exe = find_cli(judge) if judge in ("claude", "codex") else None
        if judge == "manual" or not exe:
            print(("✘ no judge CLI found" if judge != "manual" else "manual judge") +
                  f"\n  give {P['judge']}/bundle.md (and nothing else) to a model or person who did not build this;\n"
                  f"  save its JSON answer as {raw_p}, then run: two_brain.py judge {P['run']} --check")
            return 4 if judge != "manual" else 0
        empty = tempfile.mkdtemp(prefix="two_brain_judge_")    # the judge runs in an empty folder
        if judge == "claude":
            cmd = [exe, "-p", "--tools", "", "--no-session-persistence", "--output-format", "json",
                   "--json-schema", json.dumps(JUDGE_SCHEMA)]
            if a.model: cmd += ["--model", a.model]
            if a.effort: cmd += ["--effort", a.effort]
        else:
            cmd = [exe, "exec", "-s", "read-only", "--skip-git-repo-check", "--ephemeral", "-C", empty,
                   "--output-schema", os.path.join(P["judge"], "schema.json"), "-o", raw_p]
            if a.model: cmd += ["-m", a.model]
            if a.effort: cmd += ["-c", f"model_reasoning_effort={a.effort}"]
            cmd += ["-"]
        wr(os.path.join(P["judge"], "command.txt"), " ".join(c if c else '""' for c in cmd) + "   (bundle on stdin: judge/bundle.md)\n")
        try:
            r = subprocess.run(cmd, input=bundle, capture_output=True, text=True, cwd=empty, env=child_env(), timeout=a.timeout)
            if judge == "claude":
                wr(raw_p, r.stdout)
                try:
                    meta(P, judge_models=sorted(json.loads(r.stdout).get("modelUsage", {})))
                except ValueError:
                    pass
            wr(os.path.join(P["judge"], "stderr.txt"), r.stderr)
        except subprocess.TimeoutExpired:
            wr(raw_p, "")
        shutil.rmtree(empty, ignore_errors=True)
        meta(P, judge=judge, judged=now(), judge_same_as_builder=(judge == builder))
    obj = parse_judge_output(rd(raw_p))
    probs = [("J0", "no JSON in the judge's answer")] if obj is None else validate_verdicts(obj, claims, files)
    if probs:
        for c, m in probs:
            print(f"  ✘ {c} {m}")
        print(f"✘ the judge's answer breaks the rules, so it is not read as a verdict (raw: {raw_p})")
        return 2
    by = {v["id"]: v for v in obj["claims"]}
    rows = [{"id": c["id"], "claim": c["text"], **{k: by[c["id"]].get(k) for k in ("verdict", "why", "evidence", "would_settle")}} for c in claims]
    for r in rows:   # worked out from the citations, not asked of the judge: does the verdict lean on anything the acceptor produced?
        r["rests_on"] = "acceptor" if any(f.startswith(("verify/", "build/")) for f in r["evidence"] or []) else \
            ("builder only" if r["evidence"] else "nothing cited")
    wr(os.path.join(P["judge"], "verdicts.json"), json.dumps({"judge": meta(P).get("judge", judge), "claims": rows}, indent=2, ensure_ascii=False) + "\n")
    md = ["| claim | verdict | rests on | why |", "|---|---|---|---|"] + \
         [f"| {r['id']}: {r['claim']} | **{r['verdict']}** | {r['rests_on']} | {r['why']}" + (f" — would settle: {r['would_settle']}" if r['verdict'] == 'insufficient' else "") + " |" for r in rows]
    wr(os.path.join(P["judge"], "verdicts.md"), "\n".join(md) + "\n")
    tally = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}
    for r in rows:
        print(f"  {r['id']:<4} {r['verdict']:<14} {r['why'][:110]}")
    print(f"✔ judged {len(rows)} claims: " + ", ".join(f"{n} {v}" for v, n in tally.items()))
    return 0


# ── post ────────────────────────────────────────────────────────────────────────────────────────────
def cmd_post(a):
    P = paths(a.run)
    m, b = meta(P), json.loads(rd(os.path.join(P["build"], "meta.json"), "{}") or "{}")
    d = json.loads(rd(os.path.join(P["build"], "diff-stat.json"), "{}") or "{}")
    s = json.loads(rd(os.path.join(P["verify"], "summary.json"), "{}") or "{}")
    v = json.loads(rd(os.path.join(P["judge"], "verdicts.json"), "{}") or "{}")
    missing = [n for n, x in (("build/meta.json", b), ("build/diff-stat.json", d), ("verify/summary.json", s), ("judge/verdicts.json", v)) if not x]
    if missing:
        print("✘ the draft is built only from run files, and these are missing: " + ", ".join(missing)); return 1
    rows = v["claims"]
    tally = {k: sum(1 for r in rows if r["verdict"] == k) for k in VERDICTS}
    passed = sum(1 for i in s["items"] if i["status"] == "PASS")
    goal = re.search(r"^## Goal\s*\n(.*?)(?=^## |\Z)", rd(P["start"]), re.M | re.S)
    goal = " ".join(goal.group(1).split()) if goal else m.get("name", "")
    goal = re.split(r"(?<=[.!?])\s", goal, maxsplit=1)[0][:300]
    src = lambda f: f" [source: {f}]"
    who = {"codex": "Codex", "claude": "Claude Code", "manual": "a person or agent working by hand"}
    b_name, j_name = who.get(b.get("builder"), b.get("builder")), who.get(v.get("judge"), v.get("judge"))
    lines = [f"# Draft: what happened in two-brain run `{m.get('name')}`", "",
             "Draft only, built from the run's files; every number names the file it came from. Before posting anything "
             "public, turn it into a full launch kit (nk-post-kit) and run a privacy check (nk-publish-gate).", "",
             "## Short post", "",
             f"One model wrote the handoff, {b_name} built it, and a separate {j_name} run that did no building "
             f"judged the evidence: {tally['supported']} supported, {tally['not supported']} not supported, "
             f"{tally['insufficient']} insufficient out of {len(rows)} claims. The acceptor's own checks: {passed} of "
             f"{s['planned']} passed.", "",
             "## What happened", "",
             f"- Task: {goal}{src('handoff/START.md')}",
             f"- Base commit: {m.get('base', '')[:12]}{src('run.json')}",
             f"- Builder: {b_name}, model {b.get('model')}, effort {b.get('effort')}, exit {b.get('exit')}, "
             f"{b.get('seconds')} s{src('build/meta.json')}",
             f"- Judge: {j_name}" + (f", models reported {', '.join(m['judge_models'])}" if m.get("judge_models") else "") +
             (", tools switched off" if v.get("judge") == "claude" else ", read-only sandbox" if v.get("judge") == "codex" else "") +
             f", given only judge/bundle.md{src('run.json')}",
             f"- The builder ran {b.get('commands')} commands and made {b.get('file_changes')} file edits{src('build/meta.json')}",
             f"- Diff: {d.get('files_changed')} files, +{d.get('lines_added')} -{d.get('lines_removed')} lines{src('build/diff-stat.json')}",
             f"- Acceptance checks re-run by the acceptor: planned {s['planned']}, ran {s['ran']}, failed {s['failed']}"
             f"{src('verify/summary.json')}"]
    lines += [f"  - {i['id']}: {i['status']} (expect {i['expect']}{', with the code broken on purpose' if i['break'] else ''}; "
              f"{i['detail']}){src('verify/' + i['id'] + '.txt')}" for i in s["items"]]
    lines += [f"- Receipt claims: {len(rows) - 1} from the builder plus C0 from the acceptor{src('judge/verdicts.json')}", "",
              "## What the judge said", "", "| claim | verdict |", "|---|---|"]
    lines += [f"| {r['id']}: {r['claim']} | {r['verdict']} |" for r in rows]
    lean = [r["id"] for r in rows if r["verdict"] == "supported" and r.get("rests_on") == "builder only"]
    lines += ["", f"Reasons and citations: judge/verdicts.md{src('judge/verdicts.json')}", "",
              "## Not verified by this run", "",
              "- The builder's own evidence files were read by the judge but not re-run by anyone."]
    if lean:
        lines.append(f"- Supported only on files the builder wrote: {', '.join(lean)}. Re-run those commands before relying on "
                     f"{'it' if len(lean) == 1 else 'them'}{src('judge/verdicts.json')}")
    lines += [
              
              "- The judge reads files; it did not run anything. Its verdicts are about the evidence, not about the code beyond it."]
    if m.get("judge_same_as_builder"):
        lines.append("- The judge used the same CLI as the builder (a fresh run with no build context, but the same model family).")
    if s.get("trust") or s.get("receipt"):
        lines.append("- verify reported problems: " + "; ".join(s.get("trust", []) + s.get("receipt", [])) + src("verify/summary.json"))
    wr(os.path.join(P["post"], "draft.md"), "\n".join(lines) + "\n")
    print(f"✔ {P['post']}/draft.md ({len(lines)} lines)")
    return 0


def cmd_status(a):
    P = paths(a.run)
    stages = [("handoff sealed", os.path.isfile(P["trust"])), ("built", os.path.isfile(os.path.join(P["build"], "meta.json"))),
              ("verified", os.path.isfile(os.path.join(P["verify"], "summary.json"))),
              ("judged", os.path.isfile(os.path.join(P["judge"], "verdicts.json"))), ("post drafted", os.path.isfile(os.path.join(P["post"], "draft.md")))]
    for name, done in stages:
        print(f"  {'✔' if done else '·'} {name}")
    return 0


# ── self-test ───────────────────────────────────────────────────────────────────────────────────────
FAKE_CODEX = r'''#!/usr/bin/env python3
import json, os, re, sys
a = sys.argv[1:]
prompt = sys.stdin.read()
if "--output-schema" in a:                              # judge route
    mode = os.environ.get("FAKE_VERDICTS", "valid")
    ids = re.findall(r"^- (C\d+):", prompt.split("## CLAIMS", 1)[1].split("## RECEIPT", 1)[0], re.M)
    rows = [{"id": i, "verdict": "supported", "why": "A1 exit 0", "evidence": ["verify/A1.txt"], "would_settle": ""} for i in ids]
    if mode == "fourth": rows[-1]["verdict"] = "partly supported"
    if mode == "missing": rows = rows[:-1]
    if mode == "badcite": rows[0]["evidence"] = ["secret.txt"]
    open(a[a.index("-o") + 1], "w").write(json.dumps({"claims": rows}))
    sys.exit(0)
work = a[a.index("-C") + 1]; hb = a[a.index("--add-dir") + 1]
open(os.path.join(work, "lib.py"), "a").write("def double(x):\n    return 2 * x\n")
open(os.path.join(work, "notes_new.py"), "w").write("# a file the builder created and did not add\n")
os.makedirs(os.path.join(hb, "evidence"), exist_ok=True)
open(os.path.join(hb, "evidence", "e1.txt"), "w").write("$ python3 -c 'import lib; print(lib.double(2))'\n4\n")
open(os.path.join(hb, "RECEIPT.md"), "w").write("# Receipt\n\n## Claims\n- C1: double(2) returns 4 | evidence: e1.txt\n\n"
    "## How I verified\nran it\n\n## Unsure\nnone\n\n## Boundary crossings\nnone\n")
print(json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "python3 -c x", "exit_code": 0, "aggregated_output": "4"}}))
print(json.dumps({"type": "item.completed", "item": {"type": "file_change", "changes": [{"path": "lib.py", "kind": "update"}]}}))
print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}))
open(a[a.index("-o") + 1], "w").write("done\n")
'''

FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, re, sys
prompt = sys.stdin.read()
if "--permission-mode" in sys.argv:                     # builder route
    hb = sys.argv[sys.argv.index("--add-dir") + 1]
    open("lib.py", "a").write("def double(x):\n    return 2 * x\n")
    os.makedirs(os.path.join(hb, "evidence"), exist_ok=True)
    open(os.path.join(hb, "evidence", "e1.txt"), "w").write("$ true\n")
    open(os.path.join(hb, "RECEIPT.md"), "w").write("# Receipt\n\n## Claims\n- C1: added double | evidence: e1.txt\n\n## Unsure\nnone\n")
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}}]}}))
    print(json.dumps({"type": "result", "subtype": "success", "num_turns": 3, "result": "done. shall I also add tests?",
                      "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "git push"}}]}))
    sys.exit(0)
mode = os.environ.get("FAKE_VERDICTS", "valid")
if mode == "empty": sys.exit(0)
ids = re.findall(r"^- (C\d+):", prompt.split("## CLAIMS", 1)[1].split("## RECEIPT", 1)[0], re.M)
rows = [{"id": i, "verdict": "insufficient", "why": "not re-run", "evidence": [], "would_settle": "a re-run log"} for i in ids]
rows[0].update(verdict="supported", evidence=["verify/A1.txt"], why="A1 exit 0")
if mode == "nosettle": rows[-1]["would_settle"] = ""
if mode == "twice": rows.append(dict(rows[0]))
print(json.dumps({"type": "result", "subtype": "success", "structured_output": {"claims": rows}}))
'''


def selftest():
    ok, lines = True, []

    def chk(cond, label):
        nonlocal ok
        ok &= bool(cond); lines.append(f"  {'✔' if cond else '✘'} {label}")

    def q(*argv, env=None):
        """run a sub-command in-process with stdout captured; returns (rc, text)"""
        import io, contextlib
        old = dict(os.environ); os.environ.update(env or {})
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = main(list(argv))
        finally:
            os.environ.clear(); os.environ.update(old)
        return rc, buf.getvalue()

    tmp = tempfile.mkdtemp(prefix="two_brain_self_")
    try:
        repo = os.path.join(tmp, "repo"); os.makedirs(repo)
        g = lambda *x: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *x], cwd=repo, capture_output=True)
        g("init", "-q"); open(os.path.join(repo, "lib.py"), "w").write("def half(x):\n    return x / 2\n")
        g("add", "--", "lib.py"); g("commit", "-qm", "base")
        fc, fl = os.path.join(tmp, "fake-codex"), os.path.join(tmp, "fake-claude")
        open(fc, "w").write(FAKE_CODEX.replace("#!/usr/bin/env python3", "#!" + sys.executable))
        open(fl, "w").write(FAKE_CLAUDE.replace("#!/usr/bin/env python3", "#!" + sys.executable)); os.chmod(fc, 0o755); os.chmod(fl, 0o755)
        env = {"TWO_BRAIN_CODEX": fc, "TWO_BRAIN_CLAUDE": fl}
        run = os.path.join(tmp, "run"); P = paths(run)

        rc, _ = q("init", run, "--repo", repo, "--name", "t")
        chk(rc == 0 and os.path.isdir(os.path.join(P["work"], ".git")) and not git("remote", cwd=P["work"]).strip(),
            "T01 init clones the repo at base with no remote")
        rc, out = q("init", run, "--repo", repo, "--name", "t")
        chk(rc == 1, "T02 init refuses a non-empty run folder")
        rc, out = q("seal", run)
        chk(rc == 1 and "S1" in out and "S2" in out, "T03 seal refuses an unfilled START.md and an empty acceptance list")
        wr(P["start"], rd(P["start"]).replace(FILL, "filled:"))
        CLEAN_RED = "python3 -c 'import sys, lib; ok = hasattr(lib, \"double\") and lib.double(2) == 4; print(\"ok\" if ok else \"FAIL: double\"); sys.exit(0 if ok else 1)'"
        wr(P["accept"], json.dumps({"items": [{"id": "A1", "cmd": "python3 -c 'import lib; assert lib.double(2) == 4'", "expect": "pass"},
                                              {"id": "A2", "cmd": CLEAN_RED, "expect": "fail", "break": {"revert": "lib.py"}},
                                              {"id": "A3", "cmd": "true", "expect": "fail", "break": {"file": "lib.py", "find": "NOT THERE", "replace": ""}}]}))
        rc, out = q("seal", run)
        chk(rc == 0 and os.path.isfile(P["trust"]), "T04 seal writes the trust root once every slot is filled")
        root = re.search(r"trust-root sha256: (\w+)", out).group(1)

        rc, out = q("build", run, "--builder", "codex", env={"TWO_BRAIN_CODEX": ""})
        chk(rc == 4 and os.path.isfile(os.path.join(P["build"], "prompt.md")), "T05 no Codex installed: exit 4 and the prompt is written for a manual build")
        chk("Do not read" in rd(os.path.join(P["build"], "prompt.md")) and "Hand-back rules" in rd(os.path.join(P["build"], "prompt.md")),
            "T06 the builder prompt carries the boundaries and the hand-back rules")
        rc, out = q("doctor", env={"TWO_BRAIN_CODEX": "", "TWO_BRAIN_CLAUDE": fl})
        chk("default builder: claude" in out and "Codex CLI not found" in out, "T07 doctor falls back to Claude as builder and says why")

        rc, out = q("build", run, env=env)
        st = json.loads(rd(os.path.join(P["build"], "diff-stat.json")))
        chk(rc == 0 and "+def double" in rd(os.path.join(P["build"], "diff.patch")),
            "T08 build runs the builder and collects its diff against base")
        chk(st["files_changed"] == 2 and "+++ b/notes_new.py" in rd(os.path.join(P["build"], "diff.patch")),
            "T63 a file the builder created and left untracked is in the diff")
        chk("$ python3 -c x" in rd(os.path.join(P["build"], "transcript.md")), "T09 the transcript renders the builder's commands")

        crash = {"id": "A9", "cmd": "python3 -c 'import lib; assert lib.double(2) == 4'", "expect": "fail", "break": {"revert": "lib.py"}}
        status, detail, _ = run_item(P, crash)
        chk(status == "FAIL" and "crash" in detail, "T35 a break that goes red only through a traceback is a crash, not a detection")
        rc, out = q("verify", run, "--trust-root", root)
        s = json.loads(rd(os.path.join(P["verify"], "summary.json")))
        stat = {i["id"]: i["status"] for i in s["items"]}
        chk(stat.get("A1") == "PASS", "T10 an acceptance check runs in work/ and passes")
        chk(stat.get("A2") == "PASS", "T11 a break item: with lib.py reverted to base the check goes red, which is a pass")
        chk(stat.get("A3") == "NOT RUN" and rc == 1 and s["failed"] >= 1, "T12 a break whose anchor is missing is NOT RUN, and NOT RUN is never green")
        chk(rd(os.path.join(P["verify"], "A1.txt")).startswith("$ "), "T13 each re-run is saved with its command as the first line")

        saved = rd(P["accept"])
        wr(P["accept"], saved.replace("double(2) == 4", "True or 1"))
        rc, out = q("verify", run)
        chk(rc == 1 and "T3" in out and "ran 0" in out and not os.path.exists(os.path.join(P["verify"], "A1.txt")),
            "T14 an acceptance list edited after the seal is caught and not run")
        wr(P["accept"], saved)
        rc, out = q("verify", run, "--trust-root", "0" * 64)
        chk(rc == 1 and "T2" in out, "T15 a trust root that does not match is caught")

        rec = rd(P["receipt"])
        wr(P["receipt"], rec.replace("- C1: double(2) returns 4 | evidence: e1.txt", "C1 double works"))
        rc, out = q("verify", run)
        chk(rc == 1 and "R3" in out, "T16 a receipt with no claim lines is caught")
        wr(P["receipt"], rec.replace("e1.txt", "e9.txt"))
        rc, out = q("verify", run)
        chk(rc == 1 and "R5" in out, "T17 a claim citing a missing evidence file is caught")
        wr(P["receipt"], rec.replace("evidence: e1.txt", "evidence: evidence/e1.txt"))
        chk(receipt_problems(P)[0] == [], "T57 a claim may cite its file as evidence/<name>")
        wr(P["receipt"], rec.replace("evidence: e1.txt", "evidence: ../e1.txt"))
        chk("R5" in [c for c, _ in receipt_problems(P)[0]], "T58 a cited path that leaves evidence/ is caught")
        wr(P["receipt"], rec.replace("## Unsure\nnone\n", "## Unsure\n\n"))
        rc, out = q("verify", run)
        chk(rc == 1 and "R7" in out, "T18 an empty Unsure section is caught")
        wr(P["receipt"], rec)
        wr(P["accept"], json.dumps({"items": [i for i in json.loads(saved)["items"] if i["id"] != "A3"]}))
        os.remove(P["trust"]); q("seal", run)
        rc, out = q("verify", run)
        chk(rc == 0 and "failed 0" in out, "T19 control: a clean run verifies green")

        open(os.path.join(P["run"], "secret.txt"), "w").write("PRIVATE-NOTE-XYZ")
        open(os.path.join(P["handback"], "helper.py"), "w").write("print('helper')\n")
        open(os.path.join(P["evidence"], "big.txt"), "w").write("$ yes\n" + "y\n" * 30000)
        rc, out = q("judge", run, "--judge", "claude", env=env)
        bundle = rd(os.path.join(P["judge"], "bundle.md"))
        chk(rc == 0 and os.path.isfile(os.path.join(P["judge"], "verdicts.json")), "T20 a valid judge answer is written as verdicts")
        chk('--tools ""' in rd(os.path.join(P["judge"], "command.txt")) and "--no-session-persistence" in rd(os.path.join(P["judge"], "command.txt")),
            "T62 the Claude judge runs with every tool switched off and no saved session")
        chk("PRIVATE-NOTE-XYZ" not in bundle, "T21 files outside the bundle list never reach the judge")
        chk("## FILE helper.py — BUILDER-SUPPLIED" in bundle, "T59 helper files the builder handed back reach the judge, labelled")
        chk("evidence/e1.txt — BUILDER-SUPPLIED" in bundle and "verify/A1.txt — RE-RUN BY ACCEPTOR" in bundle, "T22 the bundle labels who produced each file")
        chk("[truncated:" in bundle, "T23 an oversized file is cut with a visible marker")
        chk("- C0:" in bundle and json.loads(rd(os.path.join(P["judge"], "verdicts.json")))["claims"][0]["id"] == "C0",
            "T24 the acceptor's own claim C0 (goal met) is judged too")
        os.remove(os.path.join(P["evidence"], "big.txt"))
        for mode, code, label in (("fourth", "J5", "T25 a fourth verdict is rejected"), ("missing", "J2", "T26 a claim left unjudged is rejected"),
                                  ("badcite", "J8", "T27 citing a file that is not in the bundle is rejected")):
            rc, out = q("judge", run, "--judge", "codex", env={**env, "FAKE_VERDICTS": mode})
            chk(rc == 2 and code in out, label)
        for mode, code, label in (("empty", "J0", "T28 an empty judge answer is not a verdict"),
                                  ("nosettle", "J9", "T29 'insufficient' without what would settle it is rejected"),
                                  ("twice", "J3", "T30 a claim judged twice is rejected")):
            rc, out = q("judge", run, "--judge", "claude", env={**env, "FAKE_VERDICTS": mode})
            chk(rc == 2 and code in out, label)
        rc, out = q("judge", run, "--judge", "claude", env={"TWO_BRAIN_CLAUDE": ""})
        chk(rc == 4 and "bundle.md" in out, "T31 no judge CLI: exit 4 with the manual route")

        run2 = os.path.join(tmp, "run2"); P2 = paths(run2)
        q("init", run2, "--repo", repo, "--name", "t2"); wr(P2["start"], rd(P2["start"]).replace(FILL, "filled:"))
        wr(P2["accept"], json.dumps({"items": [{"id": "A1", "cmd": "true", "expect": "pass"}]})); q("seal", run2)
        rc, out = q("build", run2, "--builder", "claude", "--allow-tool", "Bash(pytest *)", env=env)
        chk("--allowedTools Bash(pytest *)" in rd(os.path.join(P2["build"], "command.txt")),
            "T65 --allow-tool reaches the headless Claude builder as --allowedTools")
        tr = rd(os.path.join(P2["build"], "transcript.md"))
        chk(rc == 0 and "tool Bash" in tr and "git push" in tr and "ended on a question" in out and
            json.loads(rd(os.path.join(P2["build"], "diff-stat.json")))["files_changed"] == 1,
            "T36 the Claude builder route: transcript, permission denials, a closing question and the diff are all kept")

        # ── rule-by-rule samples: each one exists so that exactly this rule has something to catch ──
        run3 = os.path.join(tmp, "run3"); P3 = paths(run3)
        q("init", run3, "--repo", repo, "--name", "t3")
        rc, out = q("build", run3, env=env)
        chk(rc == 1 and "seal the handoff" in out, "T37 build refuses an unsealed handoff")
        rc, out = q("judge", run3, env=env)
        chk(rc == 1 and "run verify first" in out, "T38 judge refuses to run before verify")
        rc, out = q("verify", run3)
        chk(rc == 1 and "T1" in out and "ran 0" in out, "T39 verify on an unsealed run reports it and runs nothing")
        wr(P3["start"], rd(P3["start"]).replace(FILL, "x"))
        wr(P3["accept"], json.dumps({"items": [{"id": "A1", "cmd": "true"}, {"id": "A2", "cmd": "true", "expect": "pass", "break": {"revert": "lib.py"}}]}))
        rc, out = q("seal", run3)
        chk(rc == 1 and "S3" in out, "T40 seal refuses an acceptance item without expect")
        chk("S4" in out, "T41 seal refuses a break item that expects pass")
        wr(P3["accept"], json.dumps({"items": [{"id": "A1", "cmd": "true", "expect": "pass"}]})); q("seal", run3)
        open(os.path.join(P3["acceptor"], "late.py"), "w").write("x = 1\n")
        chk(any(c == "T4" for c, _ in trust_problems(P3)), "T42 a file added to acceptor/ after the seal is caught")
        os.remove(P3["receipt"])
        chk([c for c, _ in receipt_problems(P3)[0]] == ["R1"], "T43 a missing receipt is caught")
        wr(P3["receipt"], RECEIPT_TEMPLATE)
        chk([c for c, _ in receipt_problems(P3)[0]] == ["R2"], "T44 the untouched receipt template is caught")
        os.makedirs(P3["evidence"], exist_ok=True); wr(os.path.join(P3["evidence"], "e.txt"), "ran it, all good\n")
        wr(P3["receipt"], "## Claims\n- C1: a | evidence: e.txt\n- C1: b | evidence: e.txt\n## Unsure\nnone <<< FILL\n")
        codes = [c for c, _ in receipt_problems(P3)[0]]
        chk("R4" in codes, "T45 a claim id used twice is caught")
        chk("R6" in codes, "T46 an evidence file without a '$ command' first line is caught")
        chk("R8" in codes, "T47 a receipt with a FILL slot left is caught")
        cl, fs = [{"id": "C0"}, {"id": "C1"}], ["verify/A1.txt"]
        good = lambda i, **k: {"id": i, "verdict": "supported", "why": "w", "evidence": ["verify/A1.txt"], "would_settle": "", **k}
        chk([c for c, _ in validate_verdicts([1], cl, fs)] == ["J1"], "T48 an answer that is not an object is rejected")
        chk("J1" in [c for c, _ in validate_verdicts({"claims": [good("C0"), good("C1"), "x"]}, cl, fs)], "T49 a verdict that is not an object is rejected")
        chk("J4" in [c for c, _ in validate_verdicts({"claims": [good("C0"), good("C1"), good("C7")]}, cl, fs)], "T50 a verdict for an invented claim is rejected")
        chk("J6" in [c for c, _ in validate_verdicts({"claims": [good("C0"), good("C1", why=" ")]}, cl, fs)], "T51 a verdict without a reason is rejected")
        chk("J7" in [c for c, _ in validate_verdicts({"claims": [good("C0"), good("C1", evidence=[])]}, cl, fs)], "T52 'supported' with no file cited is rejected")
        chk(validate_verdicts({"claims": [good("C0"), good("C1")]}, cl, fs) == [], "T53 control: a well-formed answer has no findings")
        rc, out = q()
        chk(rc == 2, "T54 no sub-command prints help and exits 2")
        saved_env = dict(os.environ)
        os.environ.update({"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x", "ANTHROPIC_BASE_URL": "http://parent", "KEEP_ME": "1"})
        ce = child_env(); os.environ.clear(); os.environ.update(saved_env)
        chk("CLAUDECODE" not in ce and "CLAUDE_CODE_ENTRYPOINT" not in ce and "ANTHROPIC_BASE_URL" not in ce and ce.get("KEEP_ME") == "1",
            "T64 a child started from inside Claude Code does not inherit the parent session's variables")
        wr(P3["accept"], "{not json")
        rc, out = q("seal", run3)
        chk(rc == 2 and "crashed" in out, "T55 a stage that cannot read its input reports a crash (exit 2), not findings")
        rc, out = q("seal", os.path.join(tmp, "nowhere"))
        chk(rc == 2 and "not a two-brain run" in out, "T56 a folder that is not a run is refused")

        q("judge", run, "--judge", "claude", env=env)
        rc, out = q("post", run)
        draft = rd(os.path.join(P["post"], "draft.md"))
        body = draft.split("## What happened", 1)[1].split("## What the judge said", 1)[0]
        numbered = [l for l in body.splitlines() if re.search(r"\d", l)]
        chk(rc == 0 and numbered and all("[source: " in l for l in numbered), "T32 every line with a number in the draft names its source file")
        chk("1 supported, 0 not supported, 1 insufficient out of 2 claims" in draft, "T33 the draft's tally matches verdicts.json")
        vj = json.loads(rd(os.path.join(P["judge"], "verdicts.json")))["claims"]
        chk([r["rests_on"] for r in vj] == ["acceptor", "nothing cited"], "T60 each verdict records whether it rests on acceptor files")
        vj[1].update(verdict="supported", evidence=["evidence/e1.txt"], rests_on="builder only")
        wr(os.path.join(P["judge"], "verdicts.json"), json.dumps({"judge": "claude", "claims": vj}))
        q("post", run)
        chk("Supported only on files the builder wrote: C1" in rd(os.path.join(P["post"], "draft.md")),
            "T61 the draft names claims supported only by builder files")
        os.remove(os.path.join(P["judge"], "verdicts.json"))
        rc, out = q("post", run)
        chk(rc == 1, "T34 no draft without the judge's verdicts")
    except Exception as e:                                 # a crash is reported as a crash, never as a pass
        import traceback
        lines.append("  ✘ CRASH " + "".join(traceback.format_exception_only(type(e), e)).strip())
        ok = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n".join(lines))
    print(("✔ selftest passed" if ok else "✘ selftest FAILED") + f" ({sum(1 for l in lines if '✔' in l)}/{len(lines)})")
    return 0 if ok else 2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("doctor")
    p = sub.add_parser("init"); p.add_argument("run"); p.add_argument("--repo", required=True); p.add_argument("--name", required=True); p.add_argument("--base", default="HEAD")
    p = sub.add_parser("seal"); p.add_argument("run")
    p = sub.add_parser("build"); p.add_argument("run"); p.add_argument("--builder", choices=["codex", "claude", "manual"])
    p.add_argument("--model"); p.add_argument("--effort"); p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--allow-tool", action="append", help="Claude builder only: a permission rule to allow, e.g. 'Bash(python3 *)' (repeatable)")
    p = sub.add_parser("verify"); p.add_argument("run"); p.add_argument("--trust-root")
    p = sub.add_parser("judge"); p.add_argument("run"); p.add_argument("--judge", choices=["claude", "codex", "manual"])
    p.add_argument("--model"); p.add_argument("--effort"); p.add_argument("--check", action="store_true"); p.add_argument("--timeout", type=int, default=900)
    p = sub.add_parser("post"); p.add_argument("run")
    p = sub.add_parser("status"); p.add_argument("run")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    fn = {"doctor": cmd_doctor, "init": cmd_init, "seal": cmd_seal, "build": cmd_build, "verify": cmd_verify,
          "judge": cmd_judge, "post": cmd_post, "status": cmd_status}.get(a.cmd)
    if not fn:
        ap.print_help(); return 2
    if a.cmd not in ("doctor", "init") and not os.path.isfile(paths(a.run)["meta"]):
        print(f"✘ {a.run} is not a two-brain run (no run.json); start with init"); return 2
    try:
        return fn(a)
    except (RuntimeError, OSError, ValueError) as e:
        print(f"✘ {a.cmd} crashed: {e}"); return 2


if __name__ == "__main__":
    sys.exit(main())
