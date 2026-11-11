"""Layer 8: workflows.

A workflow is a named file, workflows/NAME.yaml, read with the existing
miniyaml reader:

    name: content-loop
    steps:
      - name: collect
        command: queue-list
        status: open
      - name: brief
        command: steward
        waiting_days: 7
      - name: draft
        command: social-draft
        article: articles/week-45.md
      - name: approve
        command: approve

Each step is one command word from the fixed allow list below, with fixed
arguments written in the file. There is no shell string, no program name and
no way to pass an argument from the command line. `approve` is not a command:
it is a fixed last step built into the runner that never approves anything.

    umwayi workflow validate NAME   every problem with a line number, exit 64 on a bad file
    umwayi workflow run NAME        run the steps in order

`run` uses the helper base (umwayi/helpers/base.py) as the runner "workflow":
the kill switch, the logbook tamper check and the rules are checked before
anything, and every step is one checked action
{"type": "workflow_step", "helper": "workflow", "workflow": NAME,
 "step": STEP, "command": WORD} that adds one logbook entry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from umwayi import drafts, logbook, miniyaml, report, rules, taskqueue
from umwayi.config import load_config
from umwayi.errors import ConfigError, UmwayiError, UsageError
from umwayi.helpers import social, steward
from umwayi.helpers.base import Helper, Outcome, Result, Stop

WORKFLOWS_DIR = "workflows"
COMMANDS = ("report", "steward", "social-draft", "queue-list", "check")  # the allow list
APPROVE = "approve"  # a fixed step built into the runner, always last, never approves
STEP_WORDS = COMMANDS + (APPROVE,)
# each step word runs exactly this method of _Run, and nothing else
STEP_FUNCTIONS = {
    "report": "report",
    "steward": "steward",
    "social-draft": "social_draft",
    "queue-list": "queue_list",
    "check": "check",
    APPROVE: "approve",
}
STEP_TYPE = "workflow_step"
OPTIONS = {
    "report": {"since_days"},
    "steward": {"waiting_days"},
    "social-draft": {"article"},
    "queue-list": {"status"},
    "check": {"action_type"},
    APPROVE: set(),
}
REQUIRED = {"report": {"since_days"}, "social-draft": {"article"}, "check": {"action_type"}}
MAX_STEPS = 20
MAX_FILE_BYTES = 64 * 1024
MAX_ARTICLE_PATH = 200
MAX_RECOMMENDATION = taskqueue.MAX_RECOMMENDATION
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,19}$")
_TYPE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")
_PLAIN_KEY = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_YAML_LINE = re.compile(r"^line (\d+): (.*)$")


@dataclass(frozen=True)
class Step:
    name: str
    command: str
    options: dict
    line: int


@dataclass(frozen=True)
class Workflow:
    name: str
    steps: tuple


@dataclass(frozen=True)
class Problem:
    line: int
    message: str

    def render(self) -> str:
        return f"line {self.line}: {self.message}"


# ------------------------------------------------------------- the file


def check_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME.match(name):
        raise UsageError("workflow: the name must be lowercase letters, digits and '-' (up to 20), for example content-loop")
    return name


def read_file(root: Path, name: str) -> str:
    """The text of workflows/NAME.yaml. Anything unsafe or missing is a config error (exit 64)."""
    name = check_name(name)
    folder = Path(root) / WORKFLOWS_DIR
    path = folder / f"{name}.yaml"
    rel = f"{WORKFLOWS_DIR}/{name}.yaml"
    if folder.is_symlink() or path.is_symlink():
        raise ConfigError(f"workflow: {rel} and the {WORKFLOWS_DIR} folder must not be symbolic links")
    if not path.is_file():
        raise ConfigError(f"workflow: {rel} was not found")
    try:
        data = path.read_bytes()
    except OSError:
        raise ConfigError(f"workflow: {rel} cannot be read") from None
    if len(data) > MAX_FILE_BYTES:
        raise ConfigError(f"workflow: {rel} is larger than {MAX_FILE_BYTES} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError(f"workflow: {rel} is not valid UTF-8") from None


def _line_map(text: str) -> dict:
    """Where each top key, each step and each step key is, as 1-based line numbers.

    Only called after miniyaml.loads has accepted the text, so the structure is regular.
    """
    toks = miniyaml._tokenize(text)
    found: dict = {}
    if not toks:
        return found
    top = toks[0][0]
    i = 0
    while i < len(toks):
        ind, t, n = toks[i]
        kv = miniyaml._split_key(t) if ind == top and not miniyaml._is_item(t) else None
        if kv is None:
            i += 1
            continue
        found[(kv[0],)] = n
        i += 1
        if kv[0] != "steps":
            continue
        idx, item_ind = 0, None
        while i < len(toks) and (toks[i][0] > top or (toks[i][0] == top and miniyaml._is_item(toks[i][1]))):
            jind, jt, jn = toks[i]
            if miniyaml._is_item(jt) and (item_ind is None or jind == item_ind):
                item_ind = jind
                idx += 1
                found[("steps", idx)] = jn
                rest = jt[1:].strip()
                kv2 = miniyaml._split_key(rest) if rest else None
                if kv2:
                    found[("steps", idx, kv2[0])] = jn
            elif idx:
                kv2 = miniyaml._split_key(jt)
                if kv2:
                    found.setdefault(("steps", idx, kv2[0]), jn)
            i += 1
    return found


def _key_text(key) -> str:
    return f"'{key}'" if isinstance(key, str) and _PLAIN_KEY.match(key) else "a key"


def _whole(value, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _article_shape(value) -> str | None:
    """None if the article path looks right, else what is wrong with it."""
    if not isinstance(value, str) or not value.strip():
        return "article must be a path to one local file"
    if len(value) > MAX_ARTICLE_PATH or not value.isprintable():
        return f"article must be a plain path of at most {MAX_ARTICLE_PATH} characters"
    if "\\" in value or value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        return "article must be a relative path with forward slashes"
    if ".." in PurePosixPath(value).parts:
        return "article must not contain '..'"
    return None


def check_text(text: str, name: str, root: Path | None = None) -> tuple:
    """(Workflow or None, problems). Every problem has a line number.

    With a root, social-draft steps are also checked against umwayi.json and the article file.
    """
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError as e:
        m = _YAML_LINE.match(str(e))
        return None, [Problem(int(m.group(1)), m.group(2)) if m else Problem(1, str(e))]
    where = _line_map(text)

    def line(*path) -> int:
        for k in range(len(path), 0, -1):
            if path[:k] in where:
                return where[path[:k]]
        return 1

    problems: list = []

    def problem(message: str, *path) -> None:
        problems.append(Problem(line(*path), message))

    if not isinstance(data, dict):
        return None, [Problem(1, "the file must be a mapping with the keys name and steps")]
    for key in data:
        if key not in ("name", "steps"):
            problem(f"{_key_text(key)} is not allowed at the top, only name and steps", key)
    if "name" not in data:
        problem("the workflow needs a name")
    elif not isinstance(data["name"], str) or not _NAME.match(data["name"]):
        problem("name must be lowercase letters, digits and '-' (up to 20)", "name")
    elif data["name"] != name:
        problem(f"name must be the file name without .yaml ({name})", "name")
    steps = data.get("steps")
    if "steps" not in data:
        problem("the workflow needs a list of steps")
        steps = []
    elif not isinstance(steps, list) or not steps:
        problem("steps must be a list with at least one step", "steps")
        steps = []
    elif len(steps) > MAX_STEPS:
        problem(f"a workflow has at most {MAX_STEPS} steps", "steps")

    parsed: list = []
    names: set = set()
    approves = [i for i, s in enumerate(steps, 1) if isinstance(s, dict) and s.get("command") == APPROVE]
    for i, item in enumerate(steps, 1):
        if not isinstance(item, dict):
            problem(f"step {i} must be a mapping with name and command", "steps", i)
            continue
        sname = item.get("name")
        if "name" not in item:
            problem(f"step {i} needs a name", "steps", i)
        elif not isinstance(sname, str) or not _NAME.match(sname):
            problem(f"step {i}: name must be lowercase letters, digits and '-' (up to 20)", "steps", i, "name")
        elif sname in names:
            problem(f"step {i}: the step name is used twice", "steps", i, "name")
        else:
            names.add(sname)
        label = f"step {i}"
        cmd = item.get("command")
        if "command" not in item:
            problem(f"{label} needs a command", "steps", i)
            continue
        if cmd not in STEP_WORDS:
            problem(f"{label}: the command is not on the allow list ({', '.join(COMMANDS)}, or approve as the last step)",
                    "steps", i, "command")
            continue
        for key in item:
            if key not in ({"name", "command"} | OPTIONS[cmd]):
                problem(f"{label}: {_key_text(key)} is not allowed for {cmd}", "steps", i, key)
        for key in sorted(REQUIRED.get(cmd, set()) - set(item)):
            problem(f"{label}: {cmd} needs {key}", "steps", i)
        opts: dict = {}
        if cmd == "report" and "since_days" in item:
            if not _whole(item["since_days"], 1, 366):
                problem(f"{label}: since_days must be a whole number from 1 to 366", "steps", i, "since_days")
            opts["since_days"] = item["since_days"]
        if cmd == "steward":
            v = item.get("waiting_days", steward.DEFAULT_WAITING_DAYS)
            if not _whole(v, 1, steward.MAX_WAITING_DAYS):
                problem(f"{label}: waiting_days must be a whole number from 1 to {steward.MAX_WAITING_DAYS}",
                        "steps", i, "waiting_days")
            opts["waiting_days"] = v
        if cmd == "queue-list" and "status" in item:
            if item["status"] not in taskqueue.STATUSES:
                problem(f"{label}: status must be one of: {', '.join(taskqueue.STATUSES)}", "steps", i, "status")
            opts["status"] = item["status"]
        if cmd == "check" and "action_type" in item:
            if not isinstance(item["action_type"], str) or not _TYPE.match(item["action_type"]):
                problem(f"{label}: action_type must be one plain word (up to 40)", "steps", i, "action_type")
            opts["action_type"] = item["action_type"]
        if cmd == "social-draft" and "article" in item:
            wrong = _article_shape(item["article"])
            if wrong:
                problem(f"{label}: {wrong}", "steps", i, "article")
            elif root is not None:
                for message in _social_problems(root, item["article"]):
                    problem(f"{label}: {message}", "steps", i, "article")
            opts["article"] = item["article"]
        if cmd == APPROVE:
            if approves and i != approves[0]:
                problem(f"{label}: a workflow has at most one approve step", "steps", i, "command")
            elif i != len(steps):
                problem(f"{label}: approve must be the last step", "steps", i, "command")
        parsed.append(Step(sname if isinstance(sname, str) else "", cmd, opts, line("steps", i)))
    if problems:
        return None, sorted(problems, key=lambda p: p.line)
    return Workflow(name, tuple(parsed)), []


def _social_problems(root: Path, article: str) -> list:
    try:
        config = load_config(root)
    except ConfigError as e:
        return [str(e)]
    if not config.social_channels:
        return ["umwayi.json has no social_channels, so there is no channel to draft for"]
    try:
        social.resolve_article(root, article, config.private_paths)
    except UmwayiError as e:
        return [str(e).removeprefix("social: ")]
    return []


def load(root: Path, name: str) -> Workflow:
    """A valid workflow, or a config error (exit 64) that says how many problems the file has."""
    wf, problems = check_text(read_file(root, name), name, root)
    if problems:
        raise ConfigError(
            f"workflow: {WORKFLOWS_DIR}/{name}.yaml has {len(problems)} problem(s), "
            f"see 'umwayi workflow validate {name}'. Nothing was run."
        )
    return wf


def validate_file(root: Path, name: str) -> Result:
    """`umwayi workflow validate NAME`. Reads only. Exit 0 when valid, 64 with every problem otherwise."""
    wf, problems = check_text(read_file(root, name), name, Path(root))
    if problems:
        lines = [f"problem: {p.render()}" for p in problems]
        return Result(64, lines + [f"{len(problems)} problem(s) found in {WORKFLOWS_DIR}/{name}.yaml"])
    steps = ", ".join(f"{s.name} ({s.command})" for s in wf.steps)
    return Result(0, [f"ok: workflow {name} has {len(wf.steps)} steps: {steps}"])


# ------------------------------------------------------------------ run


def waits_title(name: str) -> str:
    return f"Workflow {name} waits for the owner:"


def _rows_or_empty(root: Path, status: str | None = None) -> list:
    if not (Path(root) / taskqueue.QUEUE_NAME).exists() and not (Path(root) / taskqueue.QUEUE_NAME).is_symlink():
        return []
    return taskqueue.list_rows(root, status=status)


def _drafts_text(written: list) -> str:
    if not written:
        return "No drafts were written in this run."
    head, shown = "Drafts: ", []
    for k, rel in enumerate(written):
        rest = len(written) - k - 1
        tail = f" and {rest} more" if rest else ""
        if len(head + ", ".join(shown + [rel]) + tail) > 300:
            return head + ", ".join(shown) + f" and {len(written) - k} more."
        shown.append(rel)
    return head + ", ".join(shown) + "."


@dataclass
class _Run:
    root: Path
    wf: Workflow
    today: str
    helper: Helper
    written: list = field(default_factory=list)
    done: list = field(default_factory=list)

    def outcome(self, step: Step, k: int, added: str, not_done: str, lines: list, made=None) -> Outcome:
        made = made or []

        def undo():
            for d in reversed(made):
                drafts.remove(self.root, d)
        return Outcome(
            added=f"{step.name} ({step.command}): {added}",
            not_done=not_done,
            value={"lines": [f"Step {k} {step.name} ({step.command}): {lines[0]}"] + lines[1:],
                   "drafts": [d.rel for d in made]},
            undo=undo if made else None,
        )

    # -- the work of each command

    def queue_list(self, step: Step, k: int) -> Outcome:
        status = step.options.get("status")
        rows = _rows_or_empty(self.root, status)
        what = f"{len(rows)} rows" + (f" with status {status}" if status else "")
        return self.outcome(step, k, f"listed {what}", "queue.md was only read, nothing was changed.",
                            [what + "."] + [f"  {r.id}  {r.kind:<8}  {r.status:<8}  {r.title}" for r in rows])

    def steward(self, step: Step, k: int) -> Outcome:
        rows = _rows_or_empty(self.root)
        entries = logbook.read_checked(self.root)
        text = steward.proposal(rows, entries, self.today, step.options["waiting_days"])
        d = drafts.create(self.root, "steward", text)
        return self.outcome(step, k, f"wrote {d.rel} from {len(rows)} queue rows",
                            "The queue was only read. Nothing was answered, posted, sent or published.",
                            [f"wrote {d.rel}."], [d])

    def social_draft(self, step: Step, k: int) -> Outcome:
        config = load_config(self.root)
        if not config.social_channels:
            raise ConfigError("social: umwayi.json has no social_channels")
        path, rel = social.resolve_article(self.root, step.options["article"], config.private_paths)
        _article, post = social.read_article(path, rel).value
        made: list = []
        try:
            for channel in config.social_channels:
                made.append(drafts.create(self.root, f"post-{channel}", post))
        except Exception:
            for d in reversed(made):
                drafts.remove(self.root, d)
            raise
        names = ", ".join(d.rel for d in made)
        return self.outcome(step, k, f"wrote {names} from {rel} with the fixed template",
                            "Nothing was posted, sent or published. No model and no network were used.",
                            [f"wrote {names}."], made)

    def report(self, step: Step, k: int) -> Outcome:
        since = report.days_before(self.today, step.options["since_days"])
        rep = report.build(self.root, since, self.today)
        d = drafts.create(self.root, "report", rep.text)
        return self.outcome(step, k, f"wrote {d.rel} with {len(rep.commits)} commits from {since} to {self.today}",
                            "Nothing was published or pushed. No git command that writes was used.",
                            [f"wrote {d.rel} ({len(rep.commits)} commits)."], [d])

    def check(self, step: Step, k: int) -> Outcome:
        t = step.options["action_type"]
        inner = rules.check(json.dumps({"type": t}), self.root / "rules.yaml", root=self.root, when=self.today)
        who = f"rule {inner.rule_id}" if inner.rule_id else "no rule"
        o = self.outcome(step, k, f"{who} gave {inner.answer} for action type {t}",
                         "The checked action was not run.", [f"{who} gave {inner.answer} for action type {t}."])
        o.value["inner"] = inner
        return o

    def approve(self, step: Step, k: int) -> Outcome:
        n = len(self.written)
        title = f"{waits_title(self.wf.name)} review {n} draft{'s' if n != 1 else ''} from {self.today}"
        rec = (f"{_drafts_text(self.written)} This item approves nothing. To publish a draft, the owner runs "
               "umwayi publish-draft DRAFT, which is Ask me first. Answer or close this item to let the next run "
               "of this workflow start.")
        row = taskqueue.add(self.root, "decision", title, rec[:MAX_RECOMMENDATION], self.today)
        o = self.outcome(step, k, f"added queue item {row.id} (decision) listing {n} drafts; it gives no approval",
                         "No approval was given. Nothing was published, posted or sent. The workflow stops here.",
                         [f"added queue item {row.id} (decision) for the owner."])
        o.value["row"] = row
        return o


def run(root: Path, name: str, today: str) -> Result:
    root = Path(root)
    name = check_name(name)
    helper = Helper(root, "workflow", today, label=f"Workflow {name}")
    r = None
    try:
        helper.start()  # kill switch, run lock, logbook tamper check, rules: before anything else
        wf = load(root, name)
        r = _Run(root, wf, today, helper)

        for row in _rows_or_empty(root, "open"):
            if row.kind == "decision" and row.title.startswith(waits_title(name)):
                lines = [rules.ASK, "Rule: (none)",
                         f"Reason: Queue item {row.id} from an earlier run still waits for the owner. "
                         f"Answer or close it first: umwayi queue answer {row.id} --answer TEXT --revisit-if TEXT",
                         f"Workflow {name} did not start. Nothing was read or written."]
                helper._log_or_note(lines, f"Workflow {name} did not start: queue item {row.id} still waits for the owner",
                                    "the kill switch, the logbook, the rules and the workflow file were checked",
                                    "No step ran. Nothing was written or published, and no approval was given.")
                raise Stop(3, lines)

        for k, step in enumerate(wf.steps, 1):
            work = getattr(r, STEP_FUNCTIONS[step.command])
            o = helper.step(STEP_TYPE, lambda s=step, n=k, w=work: w(s, n),
                            workflow=name, step=step.name, command=step.command)
            r.done.extend(o.value["lines"])
            r.written.extend(o.value["drafts"])
            if step.command == APPROVE:
                row = o.value["row"]
                raise Stop(3, [
                    rules.ASK,
                    "Rule: (none)",
                    f"Reason: The approve step never approves. It added queue item {row.id} (decision) for the owner.",
                    f"Workflow {name} stopped at step {k} ({step.name}). It will not start again until the owner "
                    f"answers or closes {row.id}.",
                    "To publish a draft, the owner runs: umwayi publish-draft DRAFT (Ask me first).",
                ])
            inner = o.value.get("inner")
            if inner is not None and inner.answer != rules.YES:
                raise Stop(inner.exit_code, [
                    inner.answer, f"Rule: {inner.rule_id or '(none)'}", f"Reason: {inner.reason}",
                    f"Workflow {name} stopped after step {k} ({step.name}): the check gave {inner.answer}.",
                ])
    except Stop as s:
        return Result(s.code, (r.done if r else []) + s.lines)
    finally:
        helper.finish()  # the run lock, on every path
    return Result(0, r.done + [f"Workflow {name} finished {len(wf.steps)} steps. Everything it wrote is a draft. "
                               "Nothing was published."])
