"""G7, the read only part: `pr-queue.md`, `umwayi pr queue list` and `umwayi pr queue next`.

pr-queue.md is plain Markdown with one setting line and exactly one table, like queue.md. A person can read and edit it. The parser is
strict: anything unexpected is an error with a line number (never the text of the line), and nothing is changed. These commands only
READ. They never push, merge, open a pull request, call `gh` or touch the network. See docs/pr-queue-design.md.

    keep_ready: 2

    | branch | title | order | stops | status | pr | head |
    |---|---|---|---|---|---|---|
    | muse-budget-provider-line | M4 a, the providers section | 1 | yes: units.yaml | open | 215 | 8029c7c |
    | pr-queue-keep-ready | G7 keep_ready note | 2 | no | local | - | f35cb3d |

Columns: branch (a git branch name), title (one line), order (a whole number, the push order), stops (`no`, or `yes: ` and a reason),
status (`local`, `open`, `merged` or `closed`), pr (a number, or `-` while local), head (7 to 40 hex characters, or `-`).
An `open` row needs a pr number. At most ONE row is open: one pull request at a time (docs/pr-queue-design.md). `keep_ready` (0 to 9,
default 2) is the number of built, tested, unpushed branches to hold while tasks are pending (the queue is never left empty).

`next` says what to do, in this order: wait (a row is open, and it names the pull request); push (the first local row by order, with
the steps and whether it stops for the owner); nothing to push. When fewer than keep_ready rows are local and tasks are pending in
queue.md, it adds a `queue low` line that names the next pending task. Each line starts with a fixed word.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from umwayi import fsutil, taskqueue
from umwayi.errors import ConfigError

FILE_NAME = "pr-queue.md"
MAX_BYTES = 64 * 1024
STATUSES = ("local", "open", "merged", "closed")
COLUMNS = ("branch", "title", "order", "stops", "status", "pr", "head")
DEFAULT_KEEP = 2
MAX_ROWS = 200

_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
_HEAD = re.compile(r"^[0-9a-f]{7,40}$")
_KEEP = re.compile(r"^keep_ready:\s*([0-9])\s*$")
EM_DASH = "—"

STEPS = ("python -m tools.merge_main   (merge origin/main and repair the generated files)",
         "python -m tools.pre_push     (the tests this change can break)",
         "git push -u origin BRANCH, then open the pull request with its story",
         "python -m tools.pr_number --pr N   (name the pull request in the status part), then push again",
         "python -m tools.pr_green N   (green only for the exact head), then wait for the merge")


class PrQueueError(ConfigError):
    """pr-queue.md is malformed. The command line exits 64. The message never carries text from the file."""


@dataclass(frozen=True)
class Row:
    branch: str
    title: str
    order: int
    stops: str
    status: str
    pr: int | None
    head: str | None

    @property
    def owner_stop(self) -> bool:
        return self.stops.startswith("yes")


@dataclass(frozen=True)
class Doc:
    keep_ready: int = DEFAULT_KEEP
    rows: tuple = field(default_factory=tuple)


def _cells(line: str, n: int) -> list:
    if not (line.startswith("|") and line.rstrip().endswith("|")):
        raise PrQueueError(f"{FILE_NAME}: line {n} is not a table row")
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _text(value: str, what: str, n: int, limit: int) -> str:
    if not value or len(value) > limit or not all(c.isprintable() for c in value) or EM_DASH in value:
        raise PrQueueError(f"{FILE_NAME}: line {n}: {what} is empty, too long, or has a character that is not allowed")
    return value


def _row(cells: list, n: int) -> Row:
    if len(cells) != len(COLUMNS):
        raise PrQueueError(f"{FILE_NAME}: line {n} does not have {len(COLUMNS)} columns")
    branch, title, order, stops, status, pr, head = cells
    if not _BRANCH.match(branch) or ".." in branch or branch.endswith(("/", ".lock")):
        raise PrQueueError(f"{FILE_NAME}: line {n}: the branch is not a plain git branch name")
    _text(title, "the title", n, 200)
    if not re.fullmatch(r"[0-9]{1,4}", order):
        raise PrQueueError(f"{FILE_NAME}: line {n}: the order is not a whole number")
    if stops != "no" and not (stops.startswith("yes: ") and len(stops) > 5):
        raise PrQueueError(f"{FILE_NAME}: line {n}: stops is `no` or `yes: ` and a reason")
    _text(stops, "stops", n, 200)
    if status not in STATUSES:
        raise PrQueueError(f"{FILE_NAME}: line {n}: the status is not one of {', '.join(STATUSES)}")
    if pr != "-" and not re.fullmatch(r"[1-9][0-9]{0,6}", pr):
        raise PrQueueError(f"{FILE_NAME}: line {n}: pr is a number or -")
    if head != "-" and not _HEAD.match(head):
        raise PrQueueError(f"{FILE_NAME}: line {n}: head is 7 to 40 hex characters or -")
    if status in ("open", "merged") and pr == "-":
        raise PrQueueError(f"{FILE_NAME}: line {n}: a row that is {status} needs its pr number")
    if status == "local" and pr != "-":
        raise PrQueueError(f"{FILE_NAME}: line {n}: a local row has no pr number yet")
    return Row(branch, title, int(order), stops, status, None if pr == "-" else int(pr), None if head == "-" else head)


def parse(text: str) -> Doc:
    """The doc of a pr-queue.md text. Raises PrQueueError for anything it does not expect."""
    if EM_DASH in text:
        raise PrQueueError(f"{FILE_NAME}: an em dash is not allowed")
    keep, rows, table, state = None, [], False, 0  # state: 0 before the header, 1 after it, 2 in the rows, 3 after the table
    for n, line in enumerate(text.split("\n"), 1):
        if "\t" in line or "\r" in line:
            raise PrQueueError(f"{FILE_NAME}: line {n} has a tab or a carriage return")
        s = line.strip()
        if s.startswith("|"):
            if state == 3:
                raise PrQueueError(f"{FILE_NAME}: line {n}: there is more than one table")
            cells = _cells(s, n)
            if state == 0:
                if tuple(cells) != COLUMNS:
                    raise PrQueueError(f"{FILE_NAME}: line {n}: the header is not {' | '.join(COLUMNS)}")
                state = 1
            elif state == 1:
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells) or len(cells) != len(COLUMNS):
                    raise PrQueueError(f"{FILE_NAME}: line {n}: the line under the header is not the separator")
                state = 2
            else:
                rows.append(_row(cells, n))
                if len(rows) > MAX_ROWS:
                    raise PrQueueError(f"{FILE_NAME}: too many rows")
        else:
            if state == 2:
                state = 3
            m = _KEEP.match(s)
            if m:
                if keep is not None:
                    raise PrQueueError(f"{FILE_NAME}: line {n}: keep_ready is set twice")
                keep = int(m.group(1))
            elif s.lower().startswith("keep_ready"):
                raise PrQueueError(f"{FILE_NAME}: line {n}: keep_ready is a whole number from 0 to 9")
    if state == 0:
        raise PrQueueError(f"{FILE_NAME}: there is no table")
    if state == 1:
        raise PrQueueError(f"{FILE_NAME}: the table has no separator line")
    names = [r.branch for r in rows]
    if len(set(names)) != len(names):
        raise PrQueueError(f"{FILE_NAME}: a branch is listed twice")
    orders = [r.order for r in rows if r.status == "local"]
    if len(set(orders)) != len(orders):
        raise PrQueueError(f"{FILE_NAME}: two local rows have the same order")
    if sum(1 for r in rows if r.status == "open") > 1:
        raise PrQueueError(f"{FILE_NAME}: more than one row is open: one pull request at a time")
    return Doc(DEFAULT_KEEP if keep is None else keep, tuple(rows))


def read(root) -> Doc | None:
    """The queue of `root`, or None when there is no pr-queue.md."""
    path = Path(root) / FILE_NAME
    try:
        raw = fsutil.read_regular(path, MAX_BYTES)
    except FileNotFoundError:
        return None
    except fsutil.TooBig:
        raise PrQueueError(f"{FILE_NAME}: the file is too big") from None
    except OSError:
        raise PrQueueError(f"{FILE_NAME} cannot be read") from None
    try:
        return parse(raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise PrQueueError(f"{FILE_NAME}: the file is not UTF-8") from None


def list_lines(doc: Doc | None) -> list:
    if doc is None:
        return [f"There is no {FILE_NAME}. Nothing is queued."]
    if not doc.rows:
        return [f"{FILE_NAME} has no rows. keep_ready is {doc.keep_ready}."]
    lines = [f"{r.order:>3}  {r.status:<6}  {r.branch}  {'PR ' + str(r.pr) if r.pr else 'no PR yet':<10}  "
             f"{'owner stop' if r.owner_stop else 'no stop':<10}  {r.title}" for r in sorted(doc.rows, key=lambda r: (r.status != "open", r.order))]
    lines.append(f"{len(doc.rows)} rows, {sum(1 for r in doc.rows if r.status == 'local')} local, keep_ready {doc.keep_ready}.")
    return lines


def next_lines(doc: Doc | None, pending: list) -> list:
    """What to do now, as lines that each start with a fixed word. `pending` is the titles of the open tasks of queue.md."""
    if doc is None:
        return [f"nothing: there is no {FILE_NAME}."] + _low(0, DEFAULT_KEEP, pending)
    out = []
    local = sorted((r for r in doc.rows if r.status == "local"), key=lambda r: r.order)
    opened = [r for r in doc.rows if r.status == "open"]
    if opened:
        r = opened[0]
        out.append(f"wait: pull request {r.pr} ({r.branch}) is open. Check it with: python -m tools.pr_green {r.pr}")
    elif local:
        r = local[0]
        out.append(f"push: {r.branch} ({'stops for the owner: ' + r.stops[5:] if r.owner_stop else 'no owner stop'}). Steps:")
        out += ["  " + str(i) + ". " + s.replace("BRANCH", r.branch) for i, s in enumerate(STEPS, 1)]
    else:
        out.append("nothing: no row is local and none is open.")
    out += _low(len(local), doc.keep_ready, pending)
    return out


def _low(ready: int, keep: int, pending: list) -> list:
    if ready >= keep or not pending:
        return []
    return [f"queue low: {ready} of {keep} branches ready, {len(pending)} task(s) pending: build "
            f"{pending[0]} next. Nothing is started by this command."]


def pending_titles(root) -> list:
    """The titles of the open tasks of queue.md, in file order. A missing queue.md is no tasks."""
    try:
        return [r.title for r in taskqueue.list_rows(Path(root), status="open", kind="task")]
    except Exception:  # a broken queue.md is the queue's own error, not this command's
        return []
