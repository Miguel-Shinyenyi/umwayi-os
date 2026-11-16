"""W44: `umwayi up`, the single front door. A thin layer over commands that already exist.

    umwayi up [--agents PATH] [--goal TEXT --guide NAME --plan-budget-uu N [--guide-model M] [--guide-effort E]]

It runs the read-only checks of the existing commands, one line each, in this order, and then says what to do next:

  1. the root: umwayi.json loads (config.load_config) and rules.yaml is there
  2. the logbook: logbook.verify, as `umwayi logbook verify` (no logbook yet is fine)
  3. the kill switch: kill.state, as `umwayi kill status`
  4. the agents: agents.load and, for each agent, loginwizard.status_of, the report half of `umwayi login` (it runs the gate
     checks up to the login check: version and login probes, no agent and no sign-in)
  5. guidance: guidance.guard(root, None), as `umwayi goal guard`
  6. git: goalgit.is_repo and goalgit.has_main, the questions `umwayi goal` asks before it makes a worktree
  7. the goals: goal.status_lines, as `umwayi goal status`

With --goal, --guide and --plan-budget-uu (all three), and only when every check above is ok, it then calls goal.dispatch with
the arguments of `umwayi goal start`, the same function the typed command calls, with its own guard, kill switch, rules,
budget, lock, tamper check and logbook entries. It stops there: the plan waits for the owner's `umwayi goal approve`.

What it never does: it writes nothing of its own and adds no logbook entry (only `goal start`, when asked for, writes its own
entries); it starts no sign-in (it says to run `umwayi login`), no server, no approve, no run and no merge; it never turns the
kill switch off; it installs nothing, opens no network connection and runs no shell. The probes of step 4 and the git
questions of step 6 start the same programs `umwayi agent check` and `umwayi goal` start, with an argument list, never a shell.

Exit codes: 0 every check is ok (and, with --goal, the plan waits for approval); 2 a check failed (the logbook check, an
agent that is not signed in or cannot be checked, not a git repo or no main branch, a goal folder that cannot be read) or
goal start refused or an unexpected error; 3 Ask me first (the kill switch on or unreadable, guidance.yaml missing or a
changed source, or goal start gave Ask me first); 64 usage or config (a bad option, umwayi.json, agents.yaml or
guidance.yaml), which stops at once. 2 wins over 3. Never 1.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from umwayi import agents, goalgit, guidance, kill, logbook, loginwizard
from umwayi.config import load_config
from umwayi.errors import ConfigError, UmwayiError, UsageError

OK, NO, ASK, USAGE = 0, 2, 3, 64
GOAL_FLAGS = "--goal, --guide and --plan-budget-uu go together: give all three, or none"
NOT_STARTED = "The goal was not started, because a check above is not ok. Fix that line first, then run umwayi up again."
SEE_IT = "See it: umwayi serve --page ui/dist/goal-map.html (it runs in the foreground; umwayi up never starts it)."


@dataclass(frozen=True)
class Step:
    mark: str  # ok, no, ask or info
    name: str
    detail: str

    def line(self) -> str:
        return f"{self.mark}: {self.name}: {self.detail}"


def _root_step(root: Path) -> Step:
    load_config(root)  # a missing or bad umwayi.json is a config error: 64 at once
    if not (root / "rules.yaml").is_file():
        return Step("ask", "root", "umwayi.json loads, but rules.yaml is not there, so every check gives Ask me first "
                                   "(copy rules.yaml from the repo into this folder)")
    return Step("ok", "root", "umwayi.json loads and rules.yaml is there")


def _logbook_step(root: Path) -> Step:
    if not (root / "LOGBOOK.md").exists():
        return Step("ok", "logbook", "no logbook yet; the first command that writes makes it")
    report = logbook.verify(root, None)
    if report.problems:
        return Step("no", "logbook", f"{len(report.problems)} problem(s) found; run umwayi logbook verify and read what it says")
    return Step("ok", "logbook", f"{report.entries} entries, the format is valid and the hash matches the record")


def _kill_step(root: Path) -> Step:
    try:
        st = kill.state(root)
    except Exception:
        st = kill.UNKNOWN
    if kill.stopped(st):
        return Step("ask", "kill switch", f"{st}, so nothing is started. {kill.reason(st)}")
    return Step("ok", "kill switch", "off")


def _agent_steps(root: Path, given) -> list:
    listed = agents.load(root, given)  # a missing or bad agents file is 64, and so is one with no agent
    out = []
    for a in listed:
        s = loginwizard.status_of(root, a)
        mark = {loginwizard.OK: "ok", loginwizard.NOT_OFFERED: "info"}.get(s.kind, "no")
        detail = f"{s.kind}: {s.detail}"
        if s.kind == loginwizard.NEEDS:
            detail += " Run umwayi login to sign in."
        out.append(Step(mark, f"agent {a.name}", detail))
    return out


def _guidance_step(root: Path) -> Step:
    try:
        r = guidance.guard(root, None)  # a malformed guidance.yaml raises GuidanceError: 64
    except guidance.AskFirst as e:
        return Step("ask", "guidance", f"{e} (umwayi goal needs it)")
    return Step("ok", "guidance", " ".join(r.lines)) if r.code == 0 else Step("ask", "guidance", " ".join(r.lines))


def _git_step(root: Path) -> Step:
    if not goalgit.is_repo(root):
        return Step("no", "git", "this folder is not a git repo; umwayi goal needs one with a main branch")
    if not goalgit.has_main(root):
        return Step("no", "git", "this git repo has no main branch; umwayi goal needs one")
    return Step("ok", "git", "a git repo with a main branch")


def _goal_lines(root: Path):
    from umwayi import goal  # as the command line does: other commands load nothing of it
    ctx = goal.make_ctx(root, out=lambda s: None, err=lambda s: None)
    try:
        return Step("ok", "goals", "read"), goal.status_lines(ctx)
    except UmwayiError:
        return Step("no", "goals", "the goal folder cannot be read; run umwayi goal status"), []


def _code(steps) -> int:
    marks = {s.mark for s in steps}
    return NO if "no" in marks else ASK if "ask" in marks else OK


def run(root, args, say=None, warn=None) -> int:
    """`umwayi up`. Returns the exit code. say and warn take one line each."""
    say = say or (lambda s: sys.stdout.write(s + "\n"))
    warn = warn or (lambda s: sys.stderr.write(s + "\n"))
    root = Path(root)
    given = [args.goal, args.guide, args.plan_budget_uu]
    if any(v is not None for v in given) and not all(v is not None for v in given):
        raise UsageError(f"up: {GOAL_FLAGS}")
    if (args.guide_model or args.guide_effort) and args.goal is None:
        raise UsageError("up: --guide-model and --guide-effort go with --goal")
    say("umwayi up: the checks of the existing commands, in order. Nothing here writes or starts an agent.")
    steps = []
    goal_lines = []

    def add(found):
        for s in found if isinstance(found, list) else [found]:
            steps.append(s)
            say(s.line())

    # each line is printed as soon as it is known, so a config error (64) still shows the lines before it
    add(_root_step(root))
    add(_logbook_step(root))
    add(_kill_step(root))
    add(_agent_steps(root, args.agents))
    add(_guidance_step(root))
    add(_git_step(root))
    goal_step, goal_lines = _goal_lines(root)
    add(goal_step)
    for line in goal_lines:
        say("  " + line)
    code = _code(steps)
    if args.goal is None:
        if code == OK:
            say("Ready. Next: umwayi goal start \"your goal in plain words\" --guide NAME --plan-budget-uu N, "
                "or umwayi up with --goal, --guide and --plan-budget-uu.")
            say(SEE_IT)
        return code
    if code != OK:
        warn(NOT_STARTED)
        return code
    from umwayi import goal
    say("Every check is ok, so umwayi up runs umwayi goal start now (the same command, with its own checks).")
    ctx = goal.make_ctx(root, out=say, err=warn)
    rc = goal.dispatch(ctx, SimpleNamespace(goal_command="start", text=args.goal, guide=args.guide,
                                            plan_budget_uu=args.plan_budget_uu, guide_model=args.guide_model,
                                            guide_effort=args.guide_effort))
    if rc == OK:
        say(SEE_IT)
    return rc
