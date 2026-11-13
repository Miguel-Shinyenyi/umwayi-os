"""Layer 2: rules and the check decision.

Fail closed: anything unknown, missing or broken gives "Ask me first".
`check()` never raises.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import date as _date
from pathlib import Path
from typing import Any, Callable

from umwayi import logbook, miniyaml, rulelog
from umwayi.errors import UmwayiError
from umwayi.fsutil import NotRegular, TooBig, read_regular

YES = "Yes"
NO = "No"
ASK = "Ask me first"
EXIT_CODES = {YES: 0, NO: 2, ASK: 3}
_VERDICTS = {"yes": YES, "no": NO, "ask": ASK}
_STRENGTH = {NO: 2, ASK: 1, YES: 0}

MAX_ACTION_BYTES = 64 * 1024
MAX_RULES_BYTES = 1 << 20  # a rules file larger than 1 MB is refused unread
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_RULE_KEYS = {"id", "title", "text", "cause", "verdict", "matchers", "review_by", "autonomy"}
_CLASS = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
MAX_COST_UU = 1000000
# 13.R9.3: action types that graded autonomy may never move (money, publishing, an install that runs by itself, a
# spending approval, the start or permission of an agent, the start of an AI helper by a goal). A rule whose type
# matcher names one cannot opt in.
NEVER_AUTONOMY = frozenset({"payment", "transfer", "purchase", "withdraw", "deposit", "publish", "post", "send",
                            "publish_draft", "schedule_install", "budget_check", "agent_run", "agent_login",
                            "acp_permission", "serve_request", "goal_start"})
MAX_NAMED_FALLBACKS = 10  # the entry of a check names at most this many lapsed rules, then counts the rest


@dataclass(frozen=True)
class Matcher:
    field: str
    op: str  # "equals" | "contains" | "exists"
    values: tuple[Any, ...]


@dataclass(frozen=True)
class Autonomy:
    """The opt-in of an Ask me first rule (13.R9.2): the class it gives, and the owner's declarations."""
    cls: str
    reversible: bool
    cost_uu: int


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    text: str
    verdict: str  # YES / NO / ASK
    cause: str | None = None
    matchers: tuple[Matcher, ...] = ()
    review_by: str | None = None  # layer 13.R2: a Yes rule is in force through this day (YYYY-MM-DD), then it asks
    autonomy: Autonomy | None = None  # layer 13.R9.2: the opt-in of an Ask me first rule, or None


@dataclass
class Decision:
    answer: str
    rule_id: str | None
    reason: str
    matched: list[str] = field(default_factory=list)
    # facts for the logbook entry (never the action itself)
    action_ok: bool = False
    rules_ok: bool = False
    rules_count: int = 0
    action_type: str | None = None
    # set by the command line when it was asked to honour the kill switch (layer 9 adapters)
    kill_state: str | None = None
    stopped_by: str | None = None
    # layer 13.R2: (rule id, review_by) of every matching Yes rule that was past its date and counted as Ask me first
    lapsed: list[tuple[str, str]] = field(default_factory=list)
    # layer 13.R7: the SHA-256 of the rules.yaml bytes this answer came from (never in the JSON or the entry)
    rules_sha256: str | None = None
    # layer 13.R10: set only while graded autonomy is on and an opt-in rule matched: the JSON part, and the end of
    # the entry's Checked line. None keeps the JSON and the entry the bytes of before.
    autonomy: dict | None = None
    autonomy_text: str | None = None

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.answer]

    def to_dict(self) -> dict:
        """The --json answer. Adapters (layer 9) read answer, rule_id and rules_ok, never the reason text."""
        data = {
            "answer": self.answer,
            "rule_id": self.rule_id,
            "reason": self.reason,
            "matched": list(self.matched),
            "rules_ok": self.rules_ok,  # true only when rules.yaml was read and is valid
            "action_ok": self.action_ok,  # true only when the action was a readable JSON object
        }
        if self.lapsed:  # only when a rule fell back: without one the answer is the same bytes as before layer 13
            data["election_fallbacks"] = [rid for rid, _ in self.lapsed]
        if self.autonomy is not None:  # only while graded autonomy is on and an opt-in rule matched (13.R12.2)
            data["autonomy"] = dict(self.autonomy)
        return data

    def render(self) -> str:
        text = f"{self.answer}\nRule: {self.rule_id or '(none)'}\nReason: {self.reason}\n"
        if self.lapsed:
            text += f"Election fallbacks: {', '.join(f'{rid} (review_by {day})' for rid, day in self.lapsed)}\n"
        return text


# ---------------------------------------------------------------- loading


def _is_scalar(v: object) -> bool:
    return isinstance(v, (str, int, float, bool)) and v is not None


def _norm(v: object) -> str | None:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v.strip().casefold()
    return None


def _parse_matchers(raw: object, rid: str) -> tuple[Matcher, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise UmwayiError(f"rule '{rid}': matchers must be a mapping")
    out = []
    for key, value in raw.items():
        if not isinstance(key, str) or not key:
            raise UmwayiError(f"rule '{rid}': bad matcher name")
        field_name, op = key, "equals"
        if key.endswith("__contains"):
            field_name, op = key[: -len("__contains")], "contains"
        elif key.endswith("__exists"):
            field_name, op = key[: -len("__exists")], "exists"
        if not field_name:
            raise UmwayiError(f"rule '{rid}': bad matcher name")
        if op == "exists":
            if not isinstance(value, bool):
                raise UmwayiError(f"rule '{rid}': __exists needs true or false")
            vals: tuple = (value,)
        else:
            items = value if isinstance(value, list) else [value]
            if not items or not all(_is_scalar(i) for i in items):
                raise UmwayiError(f"rule '{rid}': matcher values must be plain values")
            if op == "contains" and not all(isinstance(i, str) and i.strip() for i in items):
                raise UmwayiError(f"rule '{rid}': __contains needs non-empty text")
            vals = tuple(_norm(i) for i in items)
        out.append(Matcher(field_name, op, vals))
    return tuple(out)


def _req_str(d: dict, key: str, rid: str) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise UmwayiError(f"rule '{rid}': '{key}' is required and must be text")
    return v.strip()


def _parse_review_by(raw: object, verdict: str, rid: str, opted_in: bool = False) -> str:
    """13.R2.1 and 13.R2.2: a real date YYYY-MM-DD, on a Yes rule, or on an Ask rule with the opt-in of 13.R9."""
    if verdict != YES and not (verdict == ASK and opted_in):
        raise UmwayiError(f"rule '{rid}': review_by is allowed on a Yes rule, or on an ask rule with autonomy, only")
    if not isinstance(raw, str) or "\n" in raw or not logbook.real_date(raw):
        raise UmwayiError(f"rule '{rid}': review_by must be a real date in the form YYYY-MM-DD")
    return raw


def _parse_autonomy(raw: object, verdict: str, matchers: tuple, rid: str) -> Autonomy:
    """13.R9.2 and 13.R9.3: exactly class, reversible and cost_uu, on an ask rule with a type matcher (equals) that
    names no type of the never list."""
    if verdict != ASK:
        raise UmwayiError(f"rule '{rid}': autonomy is allowed on an ask rule only")
    if not isinstance(raw, dict) or set(raw) != {"class", "reversible", "cost_uu"}:
        raise UmwayiError(f"rule '{rid}': autonomy must have exactly class, reversible and cost_uu")
    cls, rev, cost = raw["class"], raw["reversible"], raw["cost_uu"]
    if not isinstance(cls, str) or not _CLASS.match(cls):
        raise UmwayiError(f"rule '{rid}': autonomy class must be a lowercase letter, then up to 39 lowercase "
                          "letters, digits, _ or -")
    if not isinstance(rev, bool):
        raise UmwayiError(f"rule '{rid}': autonomy reversible must be true or false")
    if isinstance(cost, bool) or not isinstance(cost, int) or not 0 <= cost <= MAX_COST_UU:
        raise UmwayiError(f"rule '{rid}': autonomy cost_uu must be a whole number from 0 to {MAX_COST_UU}")
    types = [m for m in matchers if m.field == "type"]
    if len(types) != 1 or types[0].op != "equals":
        raise UmwayiError(f"rule '{rid}': a rule with autonomy needs a type matcher (equals, one or more values)")
    if set(types[0].values) & NEVER_AUTONOMY:
        raise UmwayiError(f"rule '{rid}': autonomy is never allowed for this action type")
    return Autonomy(cls, rev, cost)


def parse_rules(text: str) -> list[Rule]:
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError as e:
        raise UmwayiError(f"rules.yaml: {e}") from None
    if not isinstance(data, dict) or set(data) != {"rules"}:
        raise UmwayiError("rules.yaml: top level must be a single 'rules' list")
    items = data["rules"]
    if items is None:
        items = []
    if not isinstance(items, list):
        raise UmwayiError("rules.yaml: 'rules' must be a list")
    rules: list[Rule] = []
    seen: set[str] = set()
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise UmwayiError(f"rules.yaml: rule #{idx} must be a mapping")
        rid = item.get("id")
        if not isinstance(rid, str) or not _ID.match(rid):
            raise UmwayiError(f"rules.yaml: rule #{idx} has a missing or bad id")
        if rid in seen:
            raise UmwayiError(f"rules.yaml: duplicate rule id '{rid}'")
        seen.add(rid)
        if set(item) - _RULE_KEYS:
            raise UmwayiError(f"rule '{rid}': unknown field(s)")
        verdict_raw = item.get("verdict")
        if not isinstance(verdict_raw, str) or verdict_raw.strip().lower() not in _VERDICTS:
            raise UmwayiError(f"rule '{rid}': verdict must be yes, no or ask")
        cause = item.get("cause")
        if cause is not None and (not isinstance(cause, str) or not cause.strip()):
            raise UmwayiError(f"rule '{rid}': cause must be text")
        verdict = _VERDICTS[verdict_raw.strip().lower()]
        matchers = _parse_matchers(item.get("matchers"), rid)
        autonomy = _parse_autonomy(item["autonomy"], verdict, matchers, rid) if "autonomy" in item else None
        review_by = (_parse_review_by(item["review_by"], verdict, rid, autonomy is not None)
                     if "review_by" in item else None)
        rules.append(
            Rule(
                id=rid,
                title=_req_str(item, "title", rid),
                text=_req_str(item, "text", rid),
                verdict=verdict,
                cause=cause.strip() if cause else None,
                matchers=matchers,
                review_by=review_by,
                autonomy=autonomy,
            )
        )
    declared: dict = {}
    for r in rules:  # 13.R9.2: two opt-in rules that give one class must declare it the same way
        if r.autonomy is not None:
            seen = declared.setdefault(r.autonomy.cls, r.autonomy)
            if (seen.reversible, seen.cost_uu) != (r.autonomy.reversible, r.autonomy.cost_uu):
                raise UmwayiError(f"rule '{r.id}': another rule gives class {r.autonomy.cls} a different reversible "
                                  "or cost_uu")
    return rules


class RuleList(list):
    """The rules of one read of rules.yaml, with the SHA-256 of the exact bytes they were parsed from (13.R7)."""

    sha256: str = ""


def load_rules(path: Path) -> RuleList:
    """The rules of a regular file of at most MAX_RULES_BYTES (a link to one is followed). Anything else, /dev/zero
    or a FIFO among them, is a broken rules file: Ask me first, never a hang (S.2). The list also carries the
    SHA-256 of the bytes it was parsed from, for the rules change log."""
    try:
        data = read_regular(Path(path), MAX_RULES_BYTES)
        text = data.decode("utf-8")
    except TooBig:
        raise UmwayiError(f"rules.yaml: the file is larger than {MAX_RULES_BYTES} bytes") from None
    except NotRegular:
        raise UmwayiError("rules.yaml: not a regular file") from None
    except OSError:
        raise UmwayiError("rules.yaml: cannot read the file") from None
    except UnicodeDecodeError:
        raise UmwayiError("rules.yaml: not valid UTF-8") from None
    out = RuleList(parse_rules(text))
    out.sha256 = hashlib.sha256(data).hexdigest()
    return out


# --------------------------------------------------------------- matching


def _matches_one(m: Matcher, action: dict) -> bool:
    present = m.field in action
    if m.op == "exists":
        return present == m.values[0]
    if not present:
        return False
    value = action[m.field]
    candidates = value if isinstance(value, list) else [value]
    for c in candidates:
        n = _norm(c)
        if n is None:
            continue
        if m.op == "equals" and n in m.values:
            return True
        if m.op == "contains" and any(v in n for v in m.values):
            return True
    return False


def rule_matches(rule: Rule, action: dict) -> bool:
    if not rule.matchers:
        return False
    return all(_matches_one(m, action) for m in rule.matchers)


def _reason(rule: Rule) -> str:
    r = rule.text
    if rule.cause:
        r += f" Cause: {rule.cause}"
    return r


def system_today() -> str:
    """The system date, YYYY-MM-DD. One place, so a test can set the clock of a child process."""
    return _date.today().isoformat()


def _newest_logbook_date(root: Path) -> str | None:
    """The newest date in the logbook, or None when there is no logbook or it cannot be read (it is read like any
    other reader does, so a hand edited or broken logbook gives None; the write of the entry then fails)."""
    try:
        entries = logbook.read_checked(Path(root))
    except Exception:
        return None
    dates = [e.date for e in entries if logbook.real_date(e.date)]
    return max(dates) if dates else None


def election_clock(root: Path | None, *dates: str | None) -> str:
    """The date of a check for 13.R2.4: the latest of the system date, the dates given (--date) and the newest date
    in the logbook. A past --date, or a clock set back, cannot bring a lapsed rule back."""
    days = [system_today()] + [d for d in dates if d]
    if root is not None:
        days.append(_newest_logbook_date(root))
    return max(d for d in days if d and logbook.real_date(d))


def decide(rules: list[Rule], action: dict, today: str | Callable[[], str] | None = None) -> Decision:
    """The strongest matching rule wins. A Yes rule past its review_by counts as an Ask me first rule (13.R2.3).
    `today` is a date, or a function that gives it (called only when a matching rule has a review_by), or None for
    the system date."""
    matched = [r for r in rules if rule_matches(r, action)]
    if not matched:
        return Decision(ASK, None, "No rule matches this action.")
    lapsed_rules: list[Rule] = []
    if any(r.review_by for r in matched):
        day = today() if callable(today) else (today or system_today())
        # only a Yes rule lapses (13.R2.3); an opt-in Ask rule past its date is held by its own gate (13.R10.3.7)
        lapsed_rules = [r for r in matched if r.verdict == YES and r.review_by is not None and r.review_by < day]
    lapsed_ids = {r.id for r in lapsed_rules}
    strength = {r.id: _STRENGTH[ASK] if r.id in lapsed_ids else _STRENGTH[r.verdict] for r in matched}
    top = max(strength.values())
    winner = next(r for r in matched if strength[r.id] == top)
    lapsed = [(r.id, r.review_by) for r in lapsed_rules]
    if winner.id in lapsed_ids:
        reason = f"Rule {winner.id} is past its review_by date ({winner.review_by}), so it counts as Ask me first."
        return Decision(ASK, winner.id, reason, [r.id for r in matched], lapsed=lapsed)
    return Decision(winner.verdict, winner.id, _reason(winner), [r.id for r in matched], lapsed=lapsed)


# ------------------------------------------------------------ action JSON


def _no_dupes(pairs: list[tuple[str, Any]]) -> dict:
    d: dict = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("duplicate key")
        d[k] = v
    return d


def _bad_const(_name: str) -> None:
    raise ValueError("non-finite number")


def parse_action(text: str) -> dict:
    if len(text.encode("utf-8", "replace")) > MAX_ACTION_BYTES:
        raise UmwayiError("action: input is too large")
    try:
        data = json.loads(text, object_pairs_hook=_no_dupes, parse_constant=_bad_const)
    except (ValueError, RecursionError):
        raise UmwayiError("action: not valid JSON, or it has duplicate keys") from None
    if not isinstance(data, dict):
        raise UmwayiError("action: must be a JSON object")
    return data


_PLAIN_TYPE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")


def safe_action_type(action: dict) -> str | None:
    """The action's type, only if it is a short plain string. Nothing else of the action is kept."""
    t = action.get("type")
    return t if isinstance(t, str) and _PLAIN_TYPE.match(t) else None


def check(action_text: str | None, rules_path: Path, today: str | Callable[[], str] | None = None) -> Decision:
    """Return the Decision for an action. `today` is the date for the review_by of Yes rules (default: the system
    date); the callers without a root (jobs, helpers, publish, workflow steps) use the default.

    Anything unknown, missing or broken (the action, rules.yaml) is Ask me first.
    An unexpected error (a bug, not a bad input) is not hidden as Ask me first:
    it is raised, and the command line exits 2, so a hook always blocks on it.
    """
    if action_text is None:
        return Decision(ASK, None, "No action was given.")
    try:
        action = parse_action(action_text)
    except UmwayiError as e:
        return Decision(ASK, None, str(e))
    action_type = safe_action_type(action)
    try:
        rules = load_rules(rules_path)
    except UmwayiError as e:
        return Decision(ASK, None, f"Rules could not be loaded ({e}).", action_ok=True, action_type=action_type)
    decision = decide(rules, action, today)
    decision.action_ok = True
    decision.rules_ok = True
    decision.rules_count = len(rules)
    decision.action_type = action_type
    decision.rules_sha256 = getattr(rules, "sha256", None)
    return decision


# ------------------------------------------------------- the rules change log (layer 13.R7)


def log_rules_change(action_text: str | None, rules_path: Path, root: Path, when: str) -> tuple[str | None, str | None]:
    """Step 4 of the verdict order: log the rules before they are used. (the SHA-256 that is the logged version,
    why it could not be logged). Both None when the action cannot be read or rules.yaml cannot be read: then the
    rules are not used, so they are not logged, and the check gives Ask me first as before."""
    if action_text is None:
        return None, None
    try:
        parse_action(action_text)
        loaded = load_rules(rules_path)
    except UmwayiError:
        return None, None
    return loaded.sha256, rulelog.ensure_logged(Path(root), loaded.sha256, list(loaded), when)


def only_if_logged(decision: Decision, logged_sha256: str | None, why: str | None) -> Decision:
    """13.R7.3: rules that are not the logged version give No and Ask me first only; a Yes becomes Ask me first.
    This also covers a file that changed again between the entry and the check."""
    if decision.answer != YES or not decision.rules_ok:
        return decision
    if why is None and logged_sha256 is not None and logged_sha256 == decision.rules_sha256:
        return decision
    why = why or "rules.yaml changed again while its change was being logged"
    return Decision(ASK, decision.rule_id, f"Rule {decision.rule_id} gave Yes, but rules.yaml changed and the change "
                    f"could not be logged before use ({why}), so the answer is {ASK}.", list(decision.matched),
                    action_ok=decision.action_ok, rules_ok=decision.rules_ok, rules_count=decision.rules_count,
                    action_type=decision.action_type, lapsed=list(decision.lapsed),
                    rules_sha256=decision.rules_sha256)


def check_in_root(action_text: str | None, rules_path: Path, root: Path, when: str) -> Decision:
    """`check` for a caller that asks the rules in a root without logging its own check (a job, an AI helper,
    publish-draft, the inner check of a workflow): the rules change is logged first (13.R7.1)."""
    logged, why = log_rules_change(action_text, rules_path, root, when)
    return only_if_logged(check(action_text, rules_path), logged, why)


def _fallback_text(lapsed: list[tuple[str, str]]) -> str:
    """The end of the Checked line when a Yes rule fell back (13.R2.5); nothing when none did."""
    if not lapsed:
        return ""
    named = ", ".join(f"{rid} (review_by {day})" for rid, day in lapsed[:MAX_NAMED_FALLBACKS])
    more = len(lapsed) - MAX_NAMED_FALLBACKS
    return f"; election fallbacks: {named}" + (f", and {more} more" if more > 0 else "")


def log_entry(decision: Decision, when: str) -> logbook.Entry:
    """The logbook entry for one check. It never contains the action JSON."""
    if decision.stopped_by:
        who = f"{decision.stopped_by[0].upper()}{decision.stopped_by[1:]} gave {decision.answer}"
    elif decision.autonomy and decision.autonomy.get("moved"):
        who = f"Rule {decision.rule_id} gave {ASK} and autonomy moved it to {YES}"
    else:
        who = f"Rule {decision.rule_id} gave {decision.answer}" if decision.rule_id else f"No rule gave {decision.answer}"
    what = f"action type: {decision.action_type}" if decision.action_type else "action type not recorded"
    matched = ", ".join(decision.matched) if decision.matched else "none"
    return logbook.Entry(
        date=when,
        source="umwayi check",
        added=f"{who}; {what}",
        checked=(
            f"action read as a JSON object without duplicate keys: {'yes' if decision.action_ok else 'no'}; "
            f"rules.yaml loaded: {'yes' if decision.rules_ok else 'no'}"
            + (f" ({decision.rules_count} rules)" if decision.rules_ok else "")
            + f"; rules matched: {matched}"
            + (f"; kill switch: {decision.kill_state}" if decision.kill_state else "")
            + _fallback_text(decision.lapsed)
            + (decision.autonomy_text or "")
        ),
        not_done="The action was not run. The action JSON was not stored in the logbook.",
    )


def check_and_log(
    action_text: str | None, rules_path: Path, root: Path, when: str, log: bool = True,
    kill_state: str | None = None, stop_reason: str | None = None,
) -> tuple[Decision, bool]:
    """Check an action and append one logbook entry. Returns (decision, logged).

    If the entry cannot be written (lock held, tamper check failed, bad date,
    any error), nothing that was refused is let through:
      * No stays No (exit 2), with the rule id, and the reason says nothing was logged.
      * Yes becomes Ask me first (exit 3): a Yes is never given without its entry.
      * Ask me first stays Ask me first (exit 3).

    kill_state is recorded in the entry. stop_reason (the kill switch is on, or its
    state is unknown) turns any answer into No, with no rule, before it is logged.
    """
    # the election clock (13.R2.4): the system date, `when` and the newest logbook date, read only if a rule needs it
    # the rules change log (13.R7) comes before the rules are used; a dry run writes nothing (L13-Q19, proposal used)
    logged, why = log_rules_change(action_text, rules_path, root, when) if log else (None, None)
    decision = check(action_text, rules_path, lambda: election_clock(root, when))
    if log:
        decision = only_if_logged(decision, logged, why)
    # graded autonomy (13.R10, step 8): only a logged check, only an Ask me first that the rules gave, never a No,
    # never after the kill switch stopped the answer. Off by default: with no opt-in rule matching, no autonomy.yaml
    # or enabled false, the decision is returned unchanged.
    if log and stop_reason is None and decision.answer == ASK and decision.rules_ok:
        from umwayi import autonomy  # here, not at the top: autonomy imports this module
        rules_logged = why is None and logged is not None and logged == decision.rules_sha256
        decision = autonomy.consider(Path(root), when, decision, rules_path, rules_logged)
    decision.kill_state = kill_state
    if stop_reason is not None:
        decision = replace(decision, answer=NO, rule_id=None, reason=stop_reason, matched=[], lapsed=[],
                           stopped_by="the kill switch")
    if not log:
        return decision, False
    try:
        logbook.append(root, log_entry(decision, when))
    except UmwayiError as e:  # a known logbook failure; an unexpected error goes on to exit 2
        why = str(e).rstrip(". ")
        note = f"The logbook could not be written ({why}). Nothing was logged"
        if decision.answer == NO:
            return Decision(NO, decision.rule_id, f"{decision.reason} {note}.", list(decision.matched),
                            lapsed=list(decision.lapsed)), False
        return Decision(ASK, None, f"{note}, so the answer is {ASK}.", lapsed=list(decision.lapsed)), False
    return decision, True
