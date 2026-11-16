"""W54: the system proposes the budget of each task in UU; the owner approves or changes the number.

The proposal is a number printed for the owner (`umwayi goal show G --builder ... --tester ... --model M --effort E`).
It reaches a cap only when the owner approves it in a real terminal (`umwayi goal approve ... --accept-proposed ID`).
The approved number stays the hard cap, and nothing here can raise an approved budget (W9.R15.1, W9.R15.7, W9.R15.9).

The proposal of a task is P = B + T + C: the builder's run, the tester's run and the guide's check, because the task
budget pays for all three. Each term comes from the first source that applies to its agent:

  declared    the platform is read by runs (Kiro) and units.yaml declares one run: the declared UU of one run
  unknown     the platform is read by runs and nothing is declared: limits.unknown_worst_case (100 by default). A
              Kiro run counts as the unknown 100 UU, so the proposal never gives a Kiro role less than that
  history     at least HISTORY_MIN earlier goal tasks of the same platform, model and effort for this role reached
              `in review` or `merged` with a measured spend: 1.5 times the 95th percentile (nearest rank) of
              UU per minute of task size times this task's size (builder), or of UU per task (tester and check)
  calibrate   the per_run that `umwayi budget calibrate` proposes (1.5 times the 95th percentile of one measured run,
              20 runs over 7 days), for the model when enough settle entries name it, else for all measured runs
  no history  none of the above: 1 UU, the smallest cap a measured platform can start with; the task is marked
              `no history` and `--accept-proposed` is refused for it: the owner types the number

Each term is rounded up to a whole UU and is at most limits.per_run; P is at most limits.per_day. The proposal id is the
first 8 hex digits of the SHA-256 of the inputs and the numbers, so the same inputs always give the same id and the
owner approves exactly the numbers that were shown.

The arithmetic is pure (`term_*`, `propose_task`, `propose`, `proposal_id`). `gather` reads the logbook, units.yaml,
agents.yaml and the goal folders, and writes nothing, takes no lock and starts nothing. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from fractions import Fraction

from umwayi import agents, budget, goalpacket as gp, goalstate as gs, units
from umwayi.errors import ConfigError, UmwayiError, UsageError

HISTORY_MIN = 5
ROLES = ("builder", "tester", "check")
SOURCES = ("declared", "unknown", "history", "calibrate", "no history")
MEASURED_PLATFORMS = ("claude-code",)  # the platforms whose runs report their own cost (B.R2): history can be measured
HISTORY_STATES = ("in review", "merged")


@dataclass(frozen=True)
class Role:
    role: str  # builder, tester or check
    agent: str
    platform: str
    model: str
    effort: str

    def key(self):
        return (self.role, self.platform, self.model, self.effort)


@dataclass(frozen=True)
class Term:
    role: str
    uu: int
    source: str
    count: int = 0  # the history tasks it came from, for `history`


@dataclass(frozen=True)
class TaskProposal:
    task: str
    terms: tuple
    total: int

    @property
    def no_history(self):
        return any(t.source == "no history" for t in self.terms)


@dataclass(frozen=True)
class Inputs:
    """What a proposal is made from: plain numbers and words only, so the arithmetic is pure."""
    per_run: int
    per_day: int
    run_uu: dict  # platform -> (source declared/unknown, UU of one run) for the platforms read by runs
    history: dict = field(default_factory=dict)  # Role.key() -> tuple of samples (Fraction UU per minute, or int UU)
    calibrate: dict = field(default_factory=dict)  # model -> per_run UU; key "" for all measured runs
    units_sha256: str = ""


def _ceil(x):
    x = Fraction(x)
    return -(-x.numerator // x.denominator)


def p95(samples):
    """The 95th percentile by nearest rank, as `umwayi budget calibrate` takes it."""
    s = sorted(samples)
    return s[_ceil(Fraction(95 * len(s), 100)) - 1]


def term_history(role, samples, size):
    """1.5 times the 95th percentile: of UU per minute times the size (builder), of UU per task (tester, check)."""
    top = Fraction(p95(samples))
    return _ceil(Fraction(3, 2) * top * (size if role == "builder" else 1))


def term_for(r, size, inp):
    """The term of one role, from the first source that applies, rounded up and at most per_run."""
    if r.platform not in MEASURED_PLATFORMS:
        source, uu = inp.run_uu.get(r.platform, ("unknown", None))
        if uu is None:
            raise ValueError("a platform read by runs has no run UU")
        return Term(r.role, min(max(uu, 1), inp.per_run), source)
    samples = inp.history.get(r.key(), ())
    if len(samples) >= HISTORY_MIN:
        return Term(r.role, min(max(term_history(r.role, samples, size), 1), inp.per_run), "history", len(samples))
    cal = inp.calibrate.get(r.model) or inp.calibrate.get("")
    if cal:
        return Term(r.role, min(max(cal, 1), inp.per_run), "calibrate")
    return Term(r.role, 1, "no history")


def propose_task(task, size, roles, inp):
    terms = tuple(term_for(r, size, inp) for r in roles)
    return TaskProposal(task, terms, min(sum(t.uu for t in terms), inp.per_day))


@dataclass(frozen=True)
class Proposal:
    tasks: tuple  # TaskProposal, in packet order
    plan_uu: int
    id: str

    def by_task(self):
        return {t.task: t for t in self.tasks}

    def goal_uu(self, kept=None):
        return self.plan_uu + sum(t.total for t in self.tasks if kept is None or t.task in kept)


def proposal_id(packets, roles, inp, tasks, plan_uu):
    """The first 8 hex digits of the SHA-256 of the inputs and the numbers (canonical JSON)."""
    doc = {
        "packets": [[p.id, p.size, p.sha256()] for p in packets],
        "roles": [[r.role, r.agent, r.platform, r.model, r.effort] for r in roles],
        "units": inp.units_sha256 or "", "limits": [inp.per_run, inp.per_day],
        "run_uu": sorted([k, *v] for k, v in inp.run_uu.items()),
        "history": sorted([list(k), len(v), [str(x) for x in sorted(v)]] for k, v in inp.history.items()),
        "calibrate": sorted([k, v] for k, v in inp.calibrate.items()),
        "numbers": [[t.task, t.total, [[x.role, x.uu, x.source, x.count] for x in t.terms]] for t in tasks],
        "plan_uu": plan_uu,
    }
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()[:8]


def propose(packets, roles, inp, plan_uu):
    """The proposal of every packet (pure)."""
    tasks = tuple(propose_task(p.id, p.size, roles, inp) for p in packets)
    return Proposal(tasks, plan_uu, proposal_id(packets, roles, inp, tasks, plan_uu))


def term_words(t):
    if t.source == "history":
        return f"{t.role} {t.uu} (history, {t.count} tasks)"
    return f"{t.role} {t.uu} ({t.source})"


def lines(proposal, kept=None):
    """The lines `goal show` prints for a proposal: one per task, then the goal and the id."""
    out = {}
    for t in proposal.tasks:
        if t.no_history:
            r = next(x for x in t.terms if x.source == "no history")
            out[t.task] = (f"    Proposed: no history for the {r.role}: give a number with --budget {t.task}=N "
                           f"(the parts: " + " + ".join(term_words(x) for x in t.terms) + ")")
        else:
            out[t.task] = f"    Proposed: {t.total} UU = " + " + ".join(term_words(x) for x in t.terms)
    tasks_uu = proposal.goal_uu(kept) - proposal.plan_uu
    tail = (f"  Proposed goal budget: {proposal.goal_uu(kept)} UU (the tasks {tasks_uu}, the planning run "
            f"{proposal.plan_uu}). Proposal id {proposal.id}.")
    return out, tail


# ------------------------------------------------------------------------------------------- what a proposal reads

MEASURED_KEY = gs.MEASURED_KEY  # the optional key of a task file: {role: UU} of the runs that were all measured


def _calibrate_numbers(led):
    """{model: per_run UU, "": per_run UU} from the measured settles, by the rule of `budget.calibrate` (at least
    MIN_RUNS runs over at least MIN_DAYS days, 1.5 times the 95th percentile of one run, rounded up)."""
    def one(settles):
        runs = [s.micros for s in settles]
        days = {led.reserves[s.run].date for s in settles if s.run in led.reserves}
        if len(runs) < budget.MIN_RUNS or len(days) < budget.MIN_DAYS:
            return None
        return budget.per_run_proposal_uu(runs)

    measured = [s for s in led.settles.values() if s.tag == units.MEASURED]
    out = {}
    all_runs = one(measured)
    if all_runs:
        out[""] = all_runs
    for model in sorted({m for s in measured for m in s.models}):
        n = one([s for s in measured if model in s.models])
        if n:
            out[model] = n
    return out


def _run_uu(u, platform):
    """(source, UU of one run) for a platform read by runs, from units.reading for a run that started."""
    r = units.reading(u, platform, None, True, 0)
    return ("declared" if r.tag == units.DECLARED else "unknown"), units.uu(r.micros) if r.micros else 0


def roles_of(found, g, builder, tester, model, effort, tester_model="", tester_effort=""):
    """The three roles of a task: the builder (the owner's model and effort), the tester and the guide's check."""
    b, t, c = found(builder), found(tester), found(g["guide"])
    return (Role("builder", builder, b.platform, model, effort),
            Role("tester", tester, t.platform, tester_model or "", tester_effort or ""),
            Role("check", g["guide"], c.platform, g.get("guide_model") or "", g.get("guide_effort") or ""))


def _history(root, found):
    """{Role.key(): samples} from every goal task in the root that reached in review or merged and recorded the measured
    spend of a role. The builder's sample is UU per minute of the task's size; the tester's and the check's are UU."""
    out = {}
    for goal in gs.list_goals(root):
        try:
            g = gs.read_goal(root, goal)
        except UmwayiError:
            continue
        if not g["approved"]:
            continue
        for task in gs.list_tasks(root, goal):
            try:
                t = gs.read_task(root, goal, task)
            except UmwayiError:
                continue
            spent = t.get(MEASURED_KEY) or {}
            if t["state"] not in HISTORY_STATES or t["dropped"] or not spent:
                continue
            p = gp.packet_from_dict(t["packet"])
            try:
                rs = roles_of(found, g, g["builder"], g["tester"], p.model, p.effort, g["tester_model"], g["tester_effort"])
            except (UsageError, ConfigError):
                continue  # an agent no longer in agents.yaml: its platform is not known, so it is not history
            for r in rs:
                v = spent.get(r.role)
                if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                    out.setdefault(r.key(), []).append(Fraction(v, p.size) if r.role == "builder" else v)
    return {k: tuple(v) for k, v in out.items()}


def gather(root, today, roles):
    """The Inputs for these roles, read from the root (read only)."""
    u = units.load(root, today)
    led = budget.read_ledger(root)
    found = _finder(root)
    run_uu = {r.platform: _run_uu(u, r.platform) for r in roles if r.platform not in MEASURED_PLATFORMS}
    hist = _history(root, found)
    keys = {r.key() for r in roles}
    return Inputs(per_run=u.limits["per_run"], per_day=u.limits["per_day"], run_uu=run_uu,
                  history={k: v for k, v in hist.items() if k in keys}, calibrate=_calibrate_numbers(led),
                  units_sha256=u.sha256 or "")


def _finder(root):
    roster = agents.load(root)
    return lambda name: agents.find(roster, name)


def for_goal(root, today, goal, packets, builder, tester, model, effort, tester_model="", tester_effort=""):
    """The proposal of the packets of a goal for the given roles (read only). Raises UsageError for an agent that is not
    in agents.yaml, ConfigError for a units.yaml that cannot be read, and a budget error for a broken ledger."""
    g = gs.read_goal(root, goal)
    roles = roles_of(_finder(root), g, builder, tester, model, effort, tester_model, tester_effort)
    inp = gather(root, today, roles)
    return propose(packets, roles, inp, int(g["plan_budget_uu"]))


def kiro_floor(t):
    """The UU a task budget must hold for the runs of its platforms read by runs (declared or unknown), or 0."""
    return sum(x.uu for x in t.terms if x.source in ("declared", "unknown"))
