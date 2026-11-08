"""Layer 7: the helper base. Every AI helper uses this module.

An AI helper never acts directly. It asks for one step at a time:

    helper.step("write_draft", work, channel="linkedin")

and this module:

  1. builds the action itself, {"type": ..., "helper": NAME, ...}. A helper can
     only give an action type and a channel name. It cannot add other keys,
     so it can never set or pass an approval;
  2. sends the action through the same check as `umwayi check` (rules.yaml
     verdicts, fail closed);
  3. on No: writes one logbook entry and stops the helper with exit 2;
  4. on Ask me first (or anything that is not Yes): adds one queue item of
     kind decision for the owner (or points to the open one that already
     asks the same), writes one logbook entry and stops with exit 3;
  5. on Yes only: runs the work, then writes one logbook entry. If the work
     fails, the entry says so and the helper stops with exit 1. If the entry
     cannot be written, the work is undone and the helper stops with exit 3.

So every step that is checked adds exactly one logbook entry, written through
the checked append. Before the first step, `start` refuses to run at all if
the kill switch is on or its state cannot be read (exit 3, one entry, nothing
else), if another run holds the run lock or locking is not available (exit 3,
one entry, nothing else), if the logbook fails its tamper check (exit 1, nothing written) or if
rules.yaml cannot be loaded (exit 3, one entry, nothing else). The kill switch
is checked again before every step.

Answering the queue item is a record for the owner. It does not let the
helper go on. To allow an action, the owner adds a Yes rule in rules.yaml.
"""

from __future__ import annotations

import json
import re
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from umwayi import drafts, kill, logbook, rules, runlock, taskqueue
from umwayi.errors import UmwayiError, UsageError

HELPERS = ("steward", "social", "workflow")
# the only extra keys a helper may give; "type" and "helper" are set here. Values are plain names.
FIELD_KEYS = ("channel", "workflow", "step", "command")
_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_VALUE = re.compile(r"^[a-z][a-z0-9-]{0,19}$")
ASK_RECOMMENDATION = (
    "Keep it stopped unless you trust this action. To allow it, add a Yes rule for it in rules.yaml. "
    "Answering this item does not let the AI helper go on."
)


@dataclass
class Outcome:
    """What the work of one step returns."""

    added: str  # for the logbook: what was added or read
    not_done: str  # for the logbook: what was not done
    value: object = None  # data the helper needs next
    undo: Callable[[], None] | None = None  # removes what the work wrote


class Stop(Exception):
    """The helper stops here. code is the exit code, lines are printed."""

    def __init__(self, code: int, lines: list):
        super().__init__(f"helper stopped with exit {code}")
        self.code = code
        self.lines = lines


@dataclass(frozen=True)
class Result:
    code: int
    lines: list = field(default_factory=list)


def _why(e: BaseException) -> str:
    return str(e).rstrip(". ") if isinstance(e, UmwayiError) else "an unexpected error"


class Helper:
    def __init__(self, root: Path, name: str, today: str, label: str | None = None):
        if name not in HELPERS:
            raise UmwayiError("helper: unknown AI helper name")
        if not taskqueue.is_valid_date(today):
            raise UsageError("helper: date must be a real date YYYY-MM-DD")
        self.root = Path(root)
        self.name = name
        self.today = today
        self.source = f"umwayi {name}"
        self.label = label or f"AI helper {name}"  # how messages and the queue name this runner
        self.rules_path = self.root / "rules.yaml"
        self.steps = 0
        self._held = ExitStack()  # the run lock, released by finish()

    # ------------------------------------------------------------ logging

    def _log(self, added: str, checked: str, not_done: str) -> str | None:
        """Append one entry through the checked append. Returns None, or why it failed."""
        try:
            logbook.append(self.root, logbook.Entry(self.today, self.source, added, checked, not_done))
        except Exception as e:
            return _why(e)
        return None

    def _log_or_note(self, lines: list, added: str, checked: str, not_done: str) -> None:
        why = self._log(added, checked, not_done)
        if why is not None:
            lines.append(f"The logbook could not be written ({why}). Nothing was logged.")

    # -------------------------------------------------------------- start

    def _kill_stop(self, where: str, added: str) -> None:
        """Stop with exit 3 and one entry if the kill switch is not known to be off."""
        st = kill.state(self.root)
        if not kill.stopped(st):
            return
        lines = [rules.ASK, "Rule: (none)", f"Reason: {kill.reason(st)}", where]
        self._log_or_note(
            lines,
            f"{added}: {kill.short(st)}",
            "the kill switch was checked before anything else",
            "Nothing was read or written. No rule was asked and no queue item was added.",
        )
        raise Stop(3, lines)

    def _take_run_lock(self) -> None:
        """Hold .umwayi/run.lock until finish(). Busy or unavailable: Ask me first, one entry, nothing else."""
        try:
            self._held.enter_context(runlock.held(self.root))
            return
        except runlock.RunLockBusy:
            reason, short = runlock.BUSY_REASON, "another umwayi run holds the run lock"
        except runlock.RunLockUnavailable as e:
            reason, short = runlock.unavailable_reason(e), "the run lock could not be taken"
        lines = [rules.ASK, "Rule: (none)", f"Reason: {reason}", f"{self.label} did not start. Nothing was read or written."]
        self._log_or_note(
            lines,
            f"{self.label} did not start: {short}",
            "the kill switch, then the run lock, before anything else",
            "Nothing was read or written. No rule was asked and no queue item was added.",
        )
        raise Stop(3, lines)

    def finish(self) -> None:
        """Release the run lock. Safe to call more than once, and when it was never taken."""
        self._held.close()

    def start(self) -> None:
        """Refuse to run at all if the kill switch is on, another run is going, or the logbook or rules are broken.

        Call finish() afterwards on every path (run() below does this).
        """
        self._kill_stop(f"{self.label} did not start. Nothing was read or written.", f"{self.label} did not start")
        self._take_run_lock()
        try:
            logbook.read_checked(self.root)
        except UmwayiError as e:
            raise UmwayiError(f"{self.label} did not start: {e} Nothing was written.") from None
        try:
            rules.load_rules(self.rules_path)
        except UmwayiError as e:
            lines = [
                rules.ASK,
                "Rule: (none)",
                f"Reason: Rules could not be loaded ({e}).",
                f"{self.label} did not start. Nothing was read or written.",
            ]
            self._log_or_note(
                lines,
                f"{self.label} did not start: rules.yaml could not be loaded",
                "the logbook passed its tamper check; rules.yaml was loaded and failed",
                "No step ran. Nothing was read, written, posted or sent. No queue item was added.",
            )
            raise Stop(3, lines)

    # --------------------------------------------------------------- step

    def _action(self, type_: str, fields: dict) -> dict:
        if not isinstance(type_, str) or not _TYPE.match(type_):
            raise UmwayiError("helper: an action type must be one plain lowercase word")
        extra = set(fields) - set(FIELD_KEYS)
        if extra:
            raise UmwayiError("helper: an AI helper may only give an action type and the fields channel, workflow, step and command")
        for v in fields.values():
            if not isinstance(v, str) or not _VALUE.match(v):
                raise UmwayiError("helper: channel, workflow, step and command must each be one plain lowercase name")
        return {"type": type_, "helper": self.name, **fields}

    def step(self, type_: str, work: Callable[[], Outcome], **fields) -> Outcome:
        action = self._action(type_, fields)
        self.steps += 1
        n = self.steps
        head = f"Step {n} ({type_})"
        stopped = f"{self.label} stopped at step {n} ({type_})."
        self._kill_stop(stopped, f"{head} stopped before it ran")
        decision = rules.check(json.dumps(action), self.rules_path)
        who = f"rule {decision.rule_id}" if decision.rule_id else "no rule"
        checked = f"{who} gave {decision.answer} for action type {type_} from {self.label}"
        verdict = [decision.answer, f"Rule: {decision.rule_id or '(none)'}", f"Reason: {decision.reason}"]

        if decision.answer == rules.NO:
            lines = verdict + [stopped]
            self._log_or_note(
                lines,
                f"{head} stopped: {who} gave No",
                checked,
                "The step did not run and the AI helper stopped. Nothing was posted, sent or published.",
            )
            raise Stop(2, lines)

        if decision.answer != rules.YES:  # Ask me first, or anything unknown
            note, short = self._ask_owner(type_, fields.get("command"))
            lines = verdict + [stopped, note]
            self._log_or_note(
                lines,
                f"{head} stopped: {who} gave Ask me first; {short}",
                checked,
                "The step did not run and the AI helper stopped. Answering the queue item does not let it go on.",
            )
            raise Stop(3, lines)

        try:
            outcome = work()
        except Exception as e:
            lines = [f"{stopped[:-1]}: {_why(e)}."]
            self._log_or_note(
                lines,
                f"{head} failed after {who} gave Yes",
                checked,
                "The step did not finish and the AI helper stopped. Nothing was posted, sent or published.",
            )
            raise Stop(1, lines) from None

        why = self._log(f"{head}: {outcome.added}", checked, outcome.not_done)
        if why is not None:
            if outcome.undo is not None:
                try:
                    outcome.undo()
                except Exception:
                    raise UmwayiError(
                        f"the logbook write failed AND step {n} could not be undone, check drafts/ by hand"
                    ) from None
            raise Stop(3, [
                rules.ASK,
                "Rule: (none)",
                f"Reason: The logbook could not be written ({why}). Nothing was logged, so the work was undone. {stopped}",
            ])
        return outcome

    # ----------------------------------------------------------- the queue

    def _ask_owner(self, type_: str, command: str | None = None) -> tuple[str, str]:
        """Add one open decision for the owner, or point to the one already open."""
        title = f"{self.label} asks first: may it do {type_}" + (f" ({command})" if command else "") + "?"
        try:
            if (self.root / taskqueue.QUEUE_NAME).exists():
                for r in taskqueue.list_rows(self.root, status="open", kind="decision"):
                    if r.title == title:
                        return (f"Queue item {r.id} already asks the owner about this. Nothing was added.",
                                f"queue item {r.id} was already open")
            row = taskqueue.add(self.root, "decision", title, ASK_RECOMMENDATION, self.today)
        except Exception as e:
            return (f"The queue item could not be added ({_why(e)}).", "the queue item could not be added")
        return (f"Added queue item {row.id} (decision) for the owner. Answer it with: "
                f"umwayi queue answer {row.id} --answer TEXT", f"queue item {row.id} added")

    # ------------------------------------------------------------- drafts

    def draft(self, prefix: str, text: str, what: str) -> Outcome:
        """Work for a write_draft step: one new numbered file under drafts/, nowhere else."""
        d = drafts.create(self.root, prefix, text)
        return Outcome(
            added=f"wrote {d.rel} ({what})",
            not_done="Nothing was posted, sent or published. Only this one draft file was written.",
            value=d,
            undo=lambda: drafts.remove(self.root, d),
        )


def run(helper: Helper, body: Callable[[], list]) -> Result:
    """Start the helper, run its body, and turn a Stop into a Result. The run lock is released on every path."""
    try:
        helper.start()
        lines = body()
    except Stop as s:
        return Result(s.code, s.lines)
    finally:
        helper.finish()
    return Result(0, lines)
