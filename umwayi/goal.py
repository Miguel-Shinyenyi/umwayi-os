"""Goal orchestration (W9.8): the `umwayi goal` commands start, show, approve, run, status, answer, merged, stop, report.

The commands are thin. They read the arguments, check the terminal for the owner commands, call the guard of W19.1,
and then call `umwayi/goalstate.py` (the records) and `umwayi/goalrun.py` (the supervisor, the only code that starts a
process). Nothing here starts a process, opens a network connection or runs git: every git question goes through
`goalrun`, which asks `goalgit`.

Exit codes (W9.R3.2), never 1:
  start                      0 a plan was made and waits for approval; 2 No, a refused or invalid plan, an error;
                             3 Ask me first (the rules, the kill switch, the budget, the run lock, the goal lock)
  show, status, report       0 printed; 2 an unexpected error
  approve, answer, merged,   0 done; 2 refused (expired, not a terminal, not the right state, a failed check;
  stop                       nothing changed) or an unexpected error
  run                        0 the loop ended and no task failed or was stopped; 2 a task failed or was stopped, or an
                             error; 3 a task needs the owner, the kill switch is on, the budget or a lock refused
  any                        64 usage or a config error
A command with both a 2 and a 3 reason gives 2. A crash is 2 and prints no exception text.

Time: `time.time()` is read once per command and passed in; the date of an entry is the election clock (the latest of
the system date and the newest logbook date), so a clock set back never revives an approval.
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from umwayi import agents, fsutil, goalbudget, goaldocs, goallog, goalpacket as gp, goalrun as gr, goalstate as gs
from umwayi import goalwatch as gw, guidance, kill, logbook, rules, taskqueue, units
from umwayi.errors import ConfigError, UmwayiError, UsageError

OK, NO, ASK, USAGE = 0, 2, 3, 64
NOT_A_TERMINAL = ("This is an owner command: it needs a terminal on standard input and output, so it was refused "
                  "and nothing changed (exit 2).")
QUIET_S = 5 * 60
_GOAL = re.compile(r"^G-\d{4,}$")
_TASK = re.compile(r"^T-\d{2}$")
_BUDGET_ARG = re.compile(r"^(T-\d{2})=(\d{1,9})$")
_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
REPORT_MAX = 64 * 1024


class Refused(UmwayiError):
    """A refusal of an owner command or of `start`: exit 2, with a fixed sentence, nothing changed."""


class AskFirst(UmwayiError):
    """Ask me first: exit 3."""


# ----------------------------------------------------------------------------------------------- the context


def _is_terminal():
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError, OSError):
        return False


@dataclass
class Ctx:
    """What a command reads from outside. A test replaces any piece. `now` is read once; `env` makes the supervisor's
    environment (goalrun.Env) for the commands that run it."""
    root: Path
    now: int
    out: object
    err: object
    tty: object = _is_terminal
    gate: object = None
    env_kw: dict = field(default_factory=dict)

    @property
    def when(self):
        day = datetime.fromtimestamp(self.now, timezone.utc).strftime("%Y-%m-%d")
        return rules.election_clock(self.root, day)

    def env(self):
        kw = dict(out=self.out)
        if self.gate is not None:
            kw["gate"] = self.gate
        kw.update(self.env_kw)
        return gr.Env(self.root, **kw)

    def say(self, *lines):
        for line in lines:
            self.out(line)

    def warn(self, *lines):
        for line in lines:
            self.err(line)


def make_ctx(root, out=None, err=None, now=None, **kw):
    out = out or (lambda s: sys.stdout.write(s + "\n"))
    err = err or (lambda s: sys.stderr.write(s + "\n"))
    return Ctx(Path(os.path.realpath(root)), int(time.time() if now is None else now), out, err, **kw)


# ----------------------------------------------------------------------------------------------- shared steps


def _need_goal(goal):
    if not (isinstance(goal, str) and _GOAL.fullmatch(goal)):
        raise UsageError("goal: a goal id is G- and four or more digits")
    return goal


def _need_task(task):
    if not (isinstance(task, str) and _TASK.fullmatch(task)):
        raise UsageError("goal: a task id is T- and two digits")
    return task


def _exists(ctx, goal):
    if goal not in gs.list_goals(ctx.root):
        raise Refused(f"There is no goal {goal} in this root. Nothing changed.")


def _owner(ctx):
    """W9.R2.6 and W9-Q9: approve, answer and merged need a terminal on standard input and output."""
    if not ctx.tty():
        raise Refused(NOT_A_TERMINAL)


def _guard(ctx):
    """W19.1: the guard runs before the command does anything else. Without a task record it checks guidance.yaml
    (a malformed file is 64, a missing file or a changed source is Ask me first)."""
    r = guidance.guard(ctx.root, None)
    if r.code != 0:
        raise AskFirst(" ".join(r.lines))


def _tamper_check(ctx):
    """The logbook is read with its tamper checks and the `umwayi goal` entries are parsed strictly (W9.R18.3). Either
    failing stops every goal command that writes, with exit 2."""
    logbook.read_checked_chain(ctx.root)
    gs.view(ctx.root)


def _housekeeping(ctx, holding=False):
    """Before a writing command does its own work: repair the files from the logbook (W9.R13.5), deny what has expired
    (W9.R9.5), find a lost supervisor (W9.R19.5) and remove the worktree of a plan that was just denied."""
    gs.repair(ctx.root, when=ctx.when, now=ctx.now)
    for goal, task in gs.deny_expired(ctx.root, when=ctx.when, now=ctx.now):
        if not task:
            gr.remove_plan_worktree(ctx.env(), goal)
    gs.mark_lost(ctx.root, when=ctx.when, now=ctx.now, holding=holding)


def _per_day(ctx):
    return units.load(ctx.root, ctx.when).limits["per_day"]


def _per_run(ctx):
    return units.load(ctx.root, ctx.when).limits["per_run"]


# ----------------------------------------------------------------------------------------------- start and show


def start(ctx, text, guide, plan_budget_uu, guide_model="", guide_effort=""):
    """`goal start TEXT --guide NAME --plan-budget-uu N`: make the goal and run the guide once (W9.R5.1 to W9.R5.4)."""
    if guide_model and not re.fullmatch(r"[A-Za-z0-9._:/-]{1,64}", guide_model):
        raise UsageError("goal start: --guide-model is a model word of 1 to 64 letters, digits and ._:/-")
    if guide_effort and guide_effort not in gp.EFFORTS:
        raise UsageError("goal start: --guide-effort is one of " + ", ".join(gp.EFFORTS))
    _guard(ctx)
    if kill.stopped(kill.state(ctx.root)):  # W9.R7.1: before anything is made
        raise AskFirst(f"{rules.ASK}: {kill.reason(kill.state(ctx.root))} Nothing was made or started.")
    if goalbudget.plan_budget_problem(plan_budget_uu, _per_run(ctx)):
        raise Refused(f"--plan-budget-uu must be a whole number from 1 to limits.per_run ({_per_run(ctx)} UU). "
                      "Nothing was made.")
    agents.find(agents.load(ctx.root), guide)  # a name that is not in agents.yaml is a usage error (64)
    with gs.lock(ctx.root):
        _tamper_check(ctx)
        _housekeeping(ctx, holding=True)
        try:
            goal = gs.start_goal(ctx.root, text, guide, plan_budget_uu, when=ctx.when, now=ctx.now,
                                 guide_model=guide_model, guide_effort=guide_effort)
        except gs.RecordFailed:
            raise
        except gs.GoalError as e:
            raise Refused(f"{str(e).rstrip('.')}. Nothing was made.") from None
        ctx.say(f"Goal {goal} made. The guide {guide} plans it now.")
        o = gr.run_plan(ctx.env(), goal)
    if o.exit == OK:
        ctx.say(f"Goal {goal} has a plan that waits for you. Read it with: umwayi goal show {goal}",
                f"Approve it with: umwayi goal approve {goal} --builder NAME --tester NAME --model M --effort E "
                "--task-budget-uu N --goal-budget-uu N")
        _print_show(ctx, goal)
        return OK
    word = o.word or "refused"
    if o.exit == ASK:
        ctx.warn(f"{rules.ASK}: the planning run of goal {goal} did not start ({word}). Nothing was planned.")
    else:
        ctx.warn(f"No: the plan of goal {goal} was refused ({word}). The goal stays without packets; start a new goal.")
    return o.exit


def _packets(ctx, goal):
    """The packets of a goal: the task files once approved, plan.json before."""
    tasks = gs.list_tasks(ctx.root, goal)
    if tasks:
        out = []
        for task in tasks:
            t = gs.read_task(ctx.root, goal, task)
            out.append((gp.packet_from_dict(t["packet"]), t))
        return out
    path = gs.goal_dir(ctx.root, goal) / "plan.json"
    if not path.exists():
        return []
    raw = gs._read_json(path, gs.MAX_TASK_FILE, "plan")
    return [(gp.packet_from_dict(p), None) for p in raw.get("tasks", [])]


def _print_show(ctx, goal):
    g = gs.read_goal(ctx.root, goal)
    ctx.say(f"Goal {goal}: {_goal_word(ctx, goal)}. Guide {g['guide']}. Plan budget {g['plan_budget_uu']} UU."
            + (f" Builder {g['builder']}, tester {g['tester']}, goal budget {g['goal_budget_uu']} UU." if g["approved"] else ""))
    for p, t in _packets(ctx, goal):
        state = ("dropped" if t["dropped"] else t["state"]) if t else "proposed"
        own = gp.own_files(goal, p.id)
        ctx.say(f"  {p.id}  {state}  {p.size} min  model {p.model or '(blank)'}  effort {p.effort or '(blank)'}  "
                f"budget {p.budget_uu if p.budget_uu is not None else '(blank)'} UU",
                f"    Goal: {p.goal}")
        for i, c in enumerate(p.checks, 1):
            ctx.say(f"    Check {i}: {c}")
        ctx.say("    Files: " + ", ".join(list(p.files) + list(own)) + " (the last two by right)",
                "    Context: " + (", ".join(p.context) if p.context else "(none)"))


def show(ctx, goal):
    _need_goal(goal)
    _exists(ctx, goal)
    _print_show(ctx, goal)
    return OK


# ----------------------------------------------------------------------------------------------- approve


def _agent(ctx, name, what):
    try:
        return agents.find(agents.load(ctx.root), name)
    except UsageError:
        raise Refused(f"The {what} {name} is not an agent of agents.yaml. Nothing changed.") from None


def _model_ok(platform, model, effort, who):
    if (model or effort) and platform not in gr.PLATFORM_OPTIONS:
        raise Refused(f"The {who} runs on {platform}, which takes no model or effort from umwayi yet. Nothing changed.")
    if model and not re.fullmatch(r"[A-Za-z0-9._:/-]{1,64}", model):
        raise Refused(f"The model word of the {who} is not one umwayi accepts. Nothing changed.")
    if effort and effort not in gp.EFFORTS:
        raise Refused(f"The effort of the {who} must be one of " + ", ".join(gp.EFFORTS) + ". Nothing changed.")


def _parse_budgets(items):
    out = {}
    for item in items or ():
        m = _BUDGET_ARG.fullmatch(item or "")
        if not m or m.group(1) in out:
            raise UsageError("goal approve: --budget is T-NN=N, once per task")
        out[m.group(1)] = int(m.group(2))
    return out


def approve(ctx, goal, builder, tester, model, effort, task_budget_uu, goal_budget_uu, budgets=(), keep=None,
            tester_model="", tester_effort="", plan_hours=None, wait_hours=None):
    """The owner's approval of a plan (W9.R5.5, W9.R5.6). Refused (2, nothing changed) unless every check passes."""
    _need_goal(goal)
    per_task_override = _parse_budgets(budgets)
    for k in keep or ():
        _need_task(k)
    _owner(ctx)
    _guard(ctx)
    _exists(ctx, goal)
    try:
        lock = gs.lock(ctx.root)
        lock.__enter__()
    except gs.GoalLockBusy:
        raise Refused("Another umwayi goal command holds the goal lock. Nothing changed.") from None
    try:
        _tamper_check(ctx)
        _housekeeping(ctx, holding=True)
        g = gs.read_goal(ctx.root, goal)
        if g["plan"] is None or g["approved"] or g["stopped"]:
            raise Refused(f"Goal {goal} has no plan that waits for approval. Nothing changed.")
        if ctx.now >= g["plan"]["deadline"]:
            raise Refused("This approval timed out and was denied. Nothing changed.")
        guide = g["guide"]
        if not gp.roles_ok(guide, builder, tester):
            raise Refused("The tester and the guide must not be the builder. Nothing changed.")
        b, t, gd = _agent(ctx, builder, "builder"), _agent(ctx, tester, "tester"), _agent(ctx, guide, "guide")
        _model_ok(b.platform, model, effort, "builder")
        if not model or not effort:
            raise Refused("The builder needs --model and --effort. Nothing changed.")
        _model_ok(t.platform, tester_model, tester_effort, "tester")
        for name in (builder, tester, guide):
            r = (ctx.gate or gr._gate)(ctx.root, name, None)
            if getattr(r, "code", 2) != 0:
                raise Refused(f"agent check {name} did not pass, so it cannot be gated. Nothing changed.")
        if not gr.GIT.root_ok(ctx.root):
            raise Refused("The root is not a git work tree with a local main branch. Nothing changed.")
        packets = [p for p, _t in _packets(ctx, goal)]
        kept = [p for p in packets if keep is None or p.id in keep]
        if keep is not None and len(kept) != len(set(keep)):
            raise Refused("--keep must name tasks of the plan. Nothing changed.")
        if not kept:
            raise Refused("No task would be kept. Nothing changed.")
        need = -(-max(p.size for p in kept) * 3 // 2)
        if b.timeout_minutes < need:
            raise Refused(f"The builder's timeout_minutes in agents.yaml is {b.timeout_minutes}; the largest task "
                          f"needs at least {need} (1.5 times its size). Nothing changed.")
        if any(k not in [p.id for p in kept] for k in per_task_override):
            raise Refused("--budget names a task that is not kept. Nothing changed.")
        per_task = {p.id: per_task_override.get(p.id, task_budget_uu) for p in kept}
        if goalbudget.approval_problem(per_task, goal_budget_uu, _per_day(ctx), g["plan_budget_uu"]):
            raise Refused("Every task needs a budget from 1 UU to limits.per_day, and the goal budget must cover the "
                          "task budgets and the planning budget. Nothing changed.")
        for v, what in ((plan_hours, "--plan-hours"), (wait_hours, "--wait-hours")):
            if v is not None and not 1 <= v <= 168:
                raise Refused(f"{what} must be 1 to 168. Nothing changed.")
        if wait_hours is not None or plan_hours is not None:
            g2 = dict(g)
            if wait_hours is not None:
                g2["wait_hours"] = wait_hours
            if plan_hours is not None:
                g2["plan_hours"] = plan_hours
            gs.write_goal(ctx.root, goal, g2)
        try:
            gs.approve_plan(ctx.root, goal, builder=builder, tester=tester, guide=guide, model=model, effort=effort,
                            task_budget_uu=task_budget_uu, goal_budget_uu=goal_budget_uu, budgets=per_task_override,
                            keep=None if keep is None else [p.id for p in kept], tester_model=tester_model,
                            tester_effort=tester_effort, per_day=_per_day(ctx), when=ctx.when, now=ctx.now)
        except gs.RecordFailed:
            raise
        except gs.GoalError as e:
            raise Refused(f"{str(e).rstrip('.')}. Nothing changed.") from None
    finally:
        lock.__exit__(None, None, None)
    gr.remove_plan_worktree(ctx.env(), goal)
    if b.platform == t.platform and (tester_model or "") == (model or "") and tester_model:
        ctx.warn(f"Warning: the builder and the tester share the platform {b.platform} and the model {model}, so their "
                 "independence is weak.")
    ctx.say(f"Approved goal {goal}: {len(kept)} tasks queued, {len(packets) - len(kept)} dropped. Nothing was started.",
            f"Run the first task with: umwayi goal run {goal}")
    return OK


# ----------------------------------------------------------------------------------------------- run


def run(ctx, goal):
    """`goal run G`: the supervisor runs the next task whose turn has come (W9.R6.6), then the report (W9.R20.2)."""
    _need_goal(goal)
    _guard(ctx)
    _exists(ctx, goal)
    env = ctx.env()
    try:
        o = gr.supervise(env, goal)
    except gs.GoalLockBusy as e:
        raise AskFirst(str(e)) from None
    if o.state == "needs owner":
        t = _waiting_task(ctx, goal)
        if t is not None:
            a = t["approval"]
            ctx.say(f"Goal {goal} task {t['id']} needs you ({t['reason']}). "
                    + (gw.approval_sentence(_approval(goal, t), ctx.now) if a else ""),
                    f"Answer with: umwayi goal answer {goal} {t['id']} yes   (or no)")
    _print_report(ctx, goal, write=True)
    return o.exit


def _waiting_task(ctx, goal):
    for task in gs.list_tasks(ctx.root, goal):
        t = gs.read_task(ctx.root, goal, task)
        if t["state"] == "needs owner":
            return t
    return None


def _approval(goal, t):
    a = t["approval"]
    return gw.Approval("needs-owner", goal, t["id"], a["asked"], a["deadline"])


# ----------------------------------------------------------------------------------------------- answer, merged, stop


def _locked(ctx):
    try:
        lock = gs.lock(ctx.root)
        lock.__enter__()
    except gs.GoalLockBusy:
        raise Refused("Another umwayi goal command holds the goal lock. Nothing changed.") from None
    return lock


def answer(ctx, goal, task, word):
    """The owner's answer to a task that needs them (W9.R9.6). It is not a Yes to the rules."""
    _need_goal(goal)
    _need_task(task)
    if word not in ("yes", "no"):
        raise UsageError("goal answer: the answer is yes or no")
    _owner(ctx)
    _exists(ctx, goal)
    lock = _locked(ctx)
    try:
        _tamper_check(ctx)
        gs.repair(ctx.root, when=ctx.when, now=ctx.now)
        try:
            gs.answer_approval(ctx.root, goal, task, word, when=ctx.when, now=ctx.now)
        except gs.RecordFailed:
            raise
        except gs.GoalError as e:
            raise Refused(f"{str(e).rstrip('.')}. Nothing changed.") from None
    finally:
        lock.__exit__(None, None, None)
    if word == "yes":
        ctx.say(f"Goal {goal} task {task} is queued again. Answering starts nothing: run it with umwayi goal run {goal}.",
                "If the task's worktree or branch is still there, the next start stops as leftover until you remove it "
                "with git worktree remove.")
    else:
        ctx.say(f"Goal {goal} task {task} is stopped. Its worktree stays until you remove it.")
    return OK


def merged(ctx, goal, task, commit=None):
    """The owner's declaration that a task is merged (W9.R17.3): the commit must exist and be on the local main."""
    _need_goal(goal)
    _need_task(task)
    if commit is not None and not _SHA.fullmatch(commit):
        raise UsageError("goal merged: --commit is 40 or 64 lower case hex characters")
    _owner(ctx)
    _exists(ctx, goal)
    lock = _locked(ctx)
    try:
        _tamper_check(ctx)
        _housekeeping(ctx, holding=True)
        t = gs.read_task(ctx.root, goal, task)
        if t["state"] != "in review":
            raise Refused(f"Goal {goal} task {task} is not in review. Nothing changed.")
        sha = commit or t["tip"]
        problem = gr.declared_merge_problem(ctx.env(), sha)
        if problem is not None:
            raise Refused("That commit is not on the local main (update main first, or name the merge commit with "
                          "--commit). Nothing changed.")
        try:
            gs.change_state(ctx.root, goal, task, "merged", "declared", when=ctx.when, now=ctx.now, commit=sha)
        except gs.GoalError as e:
            raise Refused(f"{str(e).rstrip('.')}. Nothing changed.") from None
        cleaned = gr.cleanup_merged(ctx.env(), goal, task, "declared")
    finally:
        lock.__exit__(None, None, None)
    ctx.say(f"Goal {goal} task {task} is merged (declared, commit {sha[:12]}).")
    if cleaned == "kept":
        ctx.say("Its worktree was kept (it is not clean, or git refused). Remove it with git worktree remove.")
    return OK


def stop(ctx, goal):
    """`goal stop G` (W9.R16.3): open to everyone, because it only makes things safer. It does not wait for the goal
    lock: a running supervisor sees the stop within a second and stops its child. Idempotent."""
    _need_goal(goal)
    _exists(ctx, goal)
    _tamper_check(ctx)
    changed = gs.stop_goal(ctx.root, goal, "owner", when=ctx.when, now=ctx.now, queued_too=True)
    gr.remove_plan_worktree(ctx.env(), goal)
    if gs.lock_free(ctx.root):
        gs.mark_lost(ctx.root, when=ctx.when, now=ctx.now)
    ctx.say(f"Goal {goal} is stopped." if changed else f"Goal {goal} was already stopped. Nothing changed.")
    return OK


# ----------------------------------------------------------------------------------------------- status


def _events(ctx, goal, task):
    p = gs.events_path(ctx.root, goal, task)
    if not p.exists():
        return [], []
    try:
        return goallog.read(fsutil.read_regular(p, goallog.MAX_LOG + goallog.MAX_LINE + 1))
    except OSError:
        return [], []


def _at(ev):
    try:
        return int(datetime.strptime(ev["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
    except (KeyError, ValueError, TypeError):
        return None


def _age(ctx, t):
    if t is None or t > ctx.now:
        return None
    return ctx.now - t


def _event_words(ev):
    """umwayi's own words for an event (W9.R11.5): counts, a signature, a verdict word. Never a helper's text."""
    k, d = ev["kind"], ev["data"]
    if k == "output":
        return f"output: {d['lines']} lines"
    if k == "error":
        return f"error: signature {d['sig'][:8]}"
    if k == "check_result":
        return f"check_result: check {d['n']} {d['verdict']}"
    if k == "fingerprint":
        return f"fingerprint changed ({d['files']} files)"
    if k == "state":
        return f"state: {d['from']} to {d['to']} ({d['reason']})"
    if k == "started":
        return f"started: {d['role']} {d['agent']}"
    if k == "stopped":
        return f"stopped: {d['reason']}"
    if k == "skipped":
        return f"skipped: a bad log line ({d['reason']})"
    if k == "worktree":
        return f"worktree {d['action']}"
    return k


def _pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def _goal_word(ctx, goal):
    try:
        return gr.goal_status(ctx.root, goal)
    except UmwayiError:
        return "unknown"


def _spent(ctx, goal):
    g = gs.read_goal(ctx.root, goal)
    total = int(g["plan_budget_uu"]) if g["plan"] is not None or g["approved"] else 0
    for task in gs.list_tasks(ctx.root, goal):
        total += int(gs.read_task(ctx.root, goal, task).get("spent_uu") or 0)
    return total


def _docs_line(ctx):
    if not (ctx.root / goaldocs.STATUS_DIR).is_dir():
        return None  # a root without docs parts has no shared docs to build (W9-Q12)
    try:
        r = goaldocs.check(ctx.root)
    except UmwayiError:
        return "Docs: the parts cannot be read (run umwayi goal docs check)"
    if r.code == 0:
        return None
    try:
        names = [n for n in goaldocs.list_names(ctx.root / goaldocs.LIMITS_DIR)
                 if not n.startswith(goaldocs.RESERVED_PREFIX)]
        unnumbered = sum(1 for n in names
                         if not re.search(rb"(?m)^number: ", (ctx.root / goaldocs.LIMITS_DIR / n).read_bytes()))
    except OSError:
        unnumbered = 0
    return (f"Docs: {unnumbered} parts not yet built" if unnumbered else
            "Docs: the shared files are not current (run umwayi goal docs build)")


def status_lines(ctx, only=None):
    """The status text of W9.R11.1, in its order: what waits for the owner, the task and its state, the last real event
    and its age, the supervisor line after it, the child's line, the spend, the skipped lines. Reads, never writes."""
    goals = [only] if only else gs.list_goals(ctx.root)
    lines, waiting = [], []
    behind = set()
    try:
        behind = set(gs.behind(ctx.root))
    except UmwayiError:
        lines.append("The logbook could not be read with its checks, so this status comes from the files alone.")
    for goal in goals:
        g = gs.read_goal(ctx.root, goal)
        if g["plan"] and g["plan"]["answer"] is None and not g["approved"] and not g["stopped"]:
            a = gw.Approval("plan", goal, "", g["plan"]["asked"], g["plan"]["deadline"])
            waiting += [f"  Goal {goal} has a plan that waits for you. {gw.approval_sentence(a, ctx.now)}",
                        f"  Approve with: umwayi goal approve {goal} ...   (read it first: umwayi goal show {goal})"]
        for task in gs.list_tasks(ctx.root, goal):
            t = gs.read_task(ctx.root, goal, task)
            if t["state"] == "needs owner" and t["approval"]:
                waiting += [f"  Goal {goal} task {task} needs you ({t['reason']}). "
                            f"{gw.approval_sentence(_approval(goal, t), ctx.now)}",
                            f"  Answer with: umwayi goal answer {goal} {task} yes   (or no)"]
    if waiting:
        lines += ["Waiting for you"] + waiting
    supervisor_alive = not gs.lock_free(ctx.root)
    for goal in goals:
        g = gs.read_goal(ctx.root, goal)
        tasks = [gs.read_task(ctx.root, goal, t) for t in gs.list_tasks(ctx.root, goal)]
        kept = [t for t in tasks if not t["dropped"]]
        n_merged = sum(1 for t in kept if t["state"] == "merged")
        n_review = sum(1 for t in kept if t["state"] == "in review")
        lines.append(f"Goal {goal}  {_goal_word(ctx, goal)}  ({n_merged} of {len(kept)} tasks merged, {n_review} in review)")
        for t in kept:
            if t["state"] in ("merged", "queued"):
                continue
            lines += _task_lines(ctx, goal, g, t, supervisor_alive)
            if (goal, t["id"]) in behind:
                lines.append("  The task file is behind the logbook; the logbook's state is the true one.")
        lines.append(f"  Spent: {_spent(ctx, goal)} of {g['goal_budget_uu'] or g['plan_budget_uu']} UU on the goal.")
    d = _docs_line(ctx)
    if d:
        lines.append(d)
    if not goals:
        lines.append("No goals.")
    return lines


def _task_lines(ctx, goal, g, t, supervisor_alive):
    events, skipped = _events(ctx, goal, t["id"])
    started = [e for e in events if e["kind"] == "started"]
    role = started[-1]["data"]["role"] if started else "builder"
    agent = started[-1]["data"]["agent"] if started else g["builder"]
    head = f"  Task {t['id']}  {t['state']}"
    if t["state"] == "running":
        age = _age(ctx, _at(started[-1])) if started else None
        head += f"  {role} {agent}  started {gw.ago(age)}"
    elif t["reason"]:
        head += f" ({t['reason']})"
    out = [head]
    real = [e for e in events if goallog.is_real(e)]
    if real:
        last = real[-1]
        age = _age(ctx, _at(last))
        line = f"  Last event: {_event_words(last)}, {gw.ago(age)}"
        if t["state"] == "running" and (age is None or age > QUIET_S):
            quiet = "age unknown" if age is None else f"{age // 60} min"
            line += f"   QUIET for {quiet}"
            if age is not None and age >= gw.STALL_SECONDS:
                line += "   STALLED soon"
        out.append(line)
    else:
        age = _age(ctx, _at(started[-1])) if started else None
        out.append(f"  Last event: none yet (task started {gw.ago(age)})" if started else "  Last event: none yet")
    if t["state"] == "running":
        polls = [e for e in events if e["kind"] == "poll"]
        if supervisor_alive:
            pa = _age(ctx, _at(polls[-1])) if polls else None
            sup = f"Supervisor: alive (last poll {gw.ago(pa)})" if polls else "Supervisor: alive"
        else:
            sup = "Supervisor: lost"
        pid = started[-1]["data"]["pid"] if started else 0
        child = f"{role.capitalize()}: running (pid is alive)" if _pid_alive(pid) else f"{role.capitalize()}: not running"
        out.append(f"  {sup}. {child}.")
    budget = t["packet"].get("budget_uu")
    out.append(f"  Spent: {int(t.get('spent_uu') or 0)} of {budget} UU on this task.")
    out.append(f"  Skipped log lines: {len(skipped)}")
    if t["state"] == "in review":
        out.append(f"  In review: branch {t['branch']}, tip {t['tip'][:12]}. Merge it yourself; umwayi never merges.")
    return out


def status(ctx, goal=None):
    if goal is not None:
        _need_goal(goal)
        _exists(ctx, goal)
    for line in status_lines(ctx, goal):
        ctx.say(line)
    return OK


# ----------------------------------------------------------------------------------------------- report


def report_lines(ctx, goal):
    """The report of W9.R20.1: per task the state and reason, the runs (role and agent), the minutes, the UU, the files
    changed, the branch and tip, the tester's verdict words, the guide's word, the skipped lines; for the goal the
    spend, what needs the owner, what waits to be merged and the docs parts. No helper output, diff or file content."""
    g = gs.read_goal(ctx.root, goal)
    lines = [f"# Report of goal {goal}", "",
             f"Goal ({g['length']} characters, the owner's text): {g['text']}", "",
             f"State: {_goal_word(ctx, goal)}. Guide {g['guide']}, builder {g['builder'] or '(none)'}, "
             f"tester {g['tester'] or '(none)'}.", ""]
    needs, review = [], []
    for task in gs.list_tasks(ctx.root, goal):
        t = gs.read_task(ctx.root, goal, task)
        p = gp.packet_from_dict(t["packet"])
        if t["dropped"]:
            lines += [f"## {task}: dropped at approval", ""]
            continue
        events, skipped = _events(ctx, goal, task)
        runs = [e["data"] for e in events if e["kind"] == "started"]
        times = [x for x in (_at(e) for e in events) if x is not None]
        minutes = (max(times) - min(times)) // 60 if times else 0
        verdicts = [(e["data"]["n"], e["data"]["verdict"]) for e in events if e["kind"] == "check_result"]
        guide_word = {"in review": "accept", "merged": "accept"}.get(t["state"]) or (
            {"rejected": "reject", "unclear": "unclear"}.get(t["reason"]) if len(runs) >= 3 else None)
        lines += [f"## {task}: {t['state']}" + (f" ({t['reason']})" if t["reason"] else ""), "",
                  f"- Goal: {p.goal}"]
        lines += [f"- Check {i}: {c}" for i, c in enumerate(p.checks, 1)]
        lines += [f"- Runs: " + (", ".join(f"{r['role']} {r['agent']} (cap {r['cap_uu']} UU)" for r in runs) or "none"),
                  f"- Minutes: {minutes}", f"- Spent: {int(t.get('spent_uu') or 0)} of {p.budget_uu} UU",
                  f"- Branch: {t['branch'] or '(none)'}, tip {t['tip'][:12] if t['tip'] else '(none)'}",
                  f"- Files changed: {_files_changed(ctx, goal, t)}",
                  "- The tester's verdicts: " + (", ".join(f"{n} {v}" for n, v in verdicts) or "none"),
                  f"- The guide's word: {guide_word or 'none'}",
                  f"- Skipped log lines: {len(skipped)}", ""]
        if t["state"] == "needs owner":
            needs.append(f"{task} ({t['reason']})")
        if t["state"] == "in review":
            review.append(f"{task} (branch {t['branch']}, tip {t['tip'][:12]})")
    left = (g["goal_budget_uu"] - _spent(ctx, goal)) if g["goal_budget_uu"] else 0
    lines += ["## The goal", "", f"- Spent: {_spent(ctx, goal)} UU, left {max(0, left)} UU of {g['goal_budget_uu']} UU",
              "- Needs you: " + (", ".join(needs) or "nothing"),
              "- Waiting for your merge: " + (", ".join(review) or "nothing")]
    d = _docs_line(ctx)
    lines.append("- " + (d or "Docs: current"))
    lines += ["", "This is a draft for you. It holds no diff, no file content and no output of a helper."]
    return lines


def _files_changed(ctx, goal, t):
    if not t["tip"] or not t["base"] or t["state"] in ("merged",):
        return "not counted"
    try:
        return str(len(gr.GIT.changed(ctx.root, gr.GIT.worktree_path(ctx.root, goal, t["id"]), t["base"])))
    except (UmwayiError, ValueError):
        return "not counted"


def _print_report(ctx, goal, write=True):
    lines = report_lines(ctx, goal)
    if write:
        data = ("\n".join(lines) + "\n").encode("utf-8")
        if len(data) <= REPORT_MAX:
            fsutil.atomic_write(gs.goal_dir(ctx.root, goal) / "report.md", data, 0o600)
    for line in lines:
        ctx.say(line)


def report(ctx, goal):
    _need_goal(goal)
    _exists(ctx, goal)
    _print_report(ctx, goal, write=True)
    return OK


# ----------------------------------------------------------------------------------------------- the dispatcher


COMMANDS = ("start", "show", "approve", "run", "status", "answer", "merged", "stop", "report")


def dispatch(ctx, args):
    """Run one command from the parsed arguments and return its exit code. Every error fails closed."""
    c = args.goal_command
    try:
        if c == "start":
            return start(ctx, args.text, args.guide, args.plan_budget_uu, args.guide_model or "", args.guide_effort or "")
        if c == "show":
            return show(ctx, args.goal)
        if c == "approve":
            return approve(ctx, args.goal, args.builder, args.tester, args.model, args.effort, args.task_budget_uu,
                           args.goal_budget_uu, args.budget, args.keep, args.tester_model or "",
                           args.tester_effort or "", args.plan_hours, args.wait_hours)
        if c == "run":
            return run(ctx, args.goal)
        if c == "status":
            return status(ctx, args.goal)
        if c == "answer":
            return answer(ctx, args.goal, args.task, args.answer)
        if c == "merged":
            return merged(ctx, args.goal, args.task, args.commit)
        if c == "stop":
            return stop(ctx, args.goal)
        if c == "report":
            return report(ctx, args.goal)
        raise UsageError("goal: unknown command")
    except (UsageError, ConfigError, guidance.GuidanceError) as e:
        ctx.warn(f"umwayi: error: {e}")
        return USAGE
    except AskFirst as e:
        ctx.warn(str(e) if str(e).startswith(rules.ASK) else f"{rules.ASK}: {e}")
        return ASK
    except guidance.AskFirst as e:
        ctx.warn(f"{rules.ASK}: {e}")
        return ASK
    except gs.GoalLockBusy as e:
        ctx.warn(f"{rules.ASK}: {e}")
        return ASK if c in ("start", "run") else NO
    except Refused as e:
        ctx.warn(f"No: {e}")
        return NO
    except gs.RecordFailed:
        ctx.warn(gs.RECORD_FAILED)
        return NO
    except UmwayiError as e:
        ctx.warn(f"umwayi: {e}")
        return NO
    # Anything else is a crash: the command line turns it into exit 2 with the error's type and never its text.
