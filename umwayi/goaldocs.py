"""W9.9 (W9.R14): the shared docs builder. `umwayi goal docs build` and `umwayi goal docs check`.

Two files are edited by nearly every pull request and so conflict: docs/status-log.md and docs/KNOWN-LIMITS.md. Here
each task writes only its own part files, and this module builds the two files from them:

  docs-parts/status-log/00-head.md, 00-rows.md, 00-tail.md   the frozen text of the status log (head up to and
        including the table header, the old rows, the text from "A blank count means" on)
  docs-parts/known-limits/00-base.md                         the frozen text of KNOWN-LIMITS.md
  docs-parts/status-log/ID.md                                one status part per task (date, pr, what, tests)
  docs-parts/known-limits/ID.md                              one limits part per task (section, title, number)

The status log is head, then the rows of the status parts newest first, then the old rows, one blank line, the tail.
KNOWN-LIMITS is the base, then each new section (in the order of the first part that uses it) with its entries.

Strict and fail closed: a part that does not parse, a file in a parts folder that is not a part, a number the build
did not give, a link that does not resolve or an em dash in the output refuses the whole build with a fixed message
that names the file. A bad part is never skipped. Nothing is written unless everything is valid; the parts' numbers
are written first, then the two files, each through a temporary file (a build that stops half way is finished by
running it again, because a number once written is kept). Standard library only. Exit codes: 0, 2 (a refusal or
a difference), 64 (usage, in the command line); never 1 or 3.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, replace
from pathlib import Path

from umwayi import fsutil, taskqueue
from umwayi.errors import UmwayiError

STATUS_DIR = "docs-parts/status-log"
LIMITS_DIR = "docs-parts/known-limits"
STATUS_FILE = "docs/status-log.md"
LIMITS_FILE = "docs/KNOWN-LIMITS.md"
STATUS_BASE = ("00-head.md", "00-rows.md", "00-tail.md")
LIMITS_BASE = ("00-base.md",)
RESERVED_PREFIX = "00-"
FIRST_NUMBER_AFTER = 212  # entries 1 to 212 are the old ones; the W9 spec took 213 on (W9.R14.4)
MAX_PART_BYTES = 65536
MAX_BASE_BYTES = 4 * 1024 * 1024
MAX_STATUS_LINES = 300  # a doc must have fewer lines than this (tests/test_docs.py)
PR_NONE_TEXT = "see the pull request"
EM_DASH = "\u2014"
DOC_PARTS = ("Purpose", "Current state", "Decisions log", "Open questions")

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_KV = re.compile(r"([a-z]+): (\S(?:.*\S)?)")
_NUMBER = re.compile(r"[1-9][0-9]{0,5}")
_TABLE_HEAD = "| date | PR |"
_TABLE_SEP = "| --- | --- | --- | --- |"
_TAIL_START = "A blank count means"
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BODY_HEADING = re.compile(r"^#{1,3}(\s|$)")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_CODE_SPAN = re.compile(r"`+[^`]*`+")


class PartError(UmwayiError):
    """One part does not follow its format. The message is fixed text and never holds the part's content."""


class PartsRefused(UmwayiError):
    """The build is refused. `problems` are fixed messages, each naming the file."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True)
class StatusPart:
    id: str
    date: str
    pr: str  # a whole number or "none"
    what: str
    tests: str  # text or "none"
    text: str
    rel: str = ""


@dataclass(frozen=True)
class LimitsPart:
    id: str
    section: str
    title: str
    number: int | None
    body: str
    rel: str = ""


@dataclass(frozen=True)
class Plan:
    status: str
    limits: str
    numbered: dict  # relative path of a limits part -> its new bytes, for the parts that had no number
    status_parts: int
    limits_parts: int


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


# ---------------------------------------------------------------- the strict reader of one part

def _decode(raw: bytes) -> str:
    """The text of a part without its one final newline."""
    if len(raw) > MAX_PART_BYTES:
        raise PartError(f"is larger than {MAX_PART_BYTES} bytes")
    if not raw:
        raise PartError("is empty")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise PartError("is not UTF-8 text") from None
    if text.startswith("\ufeff") or any((ord(c) < 32 and c not in "\n\t") or ord(c) == 127 for c in text):
        raise PartError("has a byte order mark, a carriage return or another control character")
    if EM_DASH in text:
        raise PartError("has an em dash")
    if not text.endswith("\n") or text.endswith("\n\n"):
        raise PartError("does not end with exactly one newline")
    return text[:-1]


def _header_and_rest(text: str):
    """(header lines, the text after the one blank line or None)."""
    lines = text.split("\n")
    n = 0
    while n < len(lines) and lines[n] != "":
        n += 1
    header, after = lines[:n], lines[n + 1:]
    if n == len(lines):
        return header, None
    if not after or after[0] == "":
        raise PartError("has a blank line that is not followed by text, or more than one blank line")
    return header, "\n".join(after)


def _pairs(header: list, order: tuple, required: tuple) -> dict:
    pairs = []
    for line in header:
        m = _KV.fullmatch(line)
        if not m:
            raise PartError("has a header line that is not 'key: value' (a lower case key, one space, a value "
                            "with no space at either end)")
        pairs.append(m.groups())
    keys = [k for k, _v in pairs]
    if any(k not in order for k in keys):
        raise PartError("has an unknown key (the keys are " + ", ".join(order) + ")")
    if len(set(keys)) != len(keys):
        raise PartError("has a key twice")
    for k in required:
        if k not in keys:
            raise PartError(f"has no key {k}")
    if keys != [k for k in order if k in keys]:
        raise PartError("has its keys out of order (expected: " + ", ".join(order) + ")")
    return dict(pairs)


def read_status_part(name: str, raw: bytes) -> StatusPart:
    """W9.R14.2. A status part: date, pr, what, tests, then optionally one blank line and free text."""
    text = _decode(raw)
    header, free = _header_and_rest(text)
    v = _pairs(header, ("date", "pr", "what", "tests"), ("date", "pr", "what", "tests"))
    if not taskqueue.is_valid_date(v["date"]):
        raise PartError("has a date that is not a real date in the form YYYY-MM-DD")
    if v["pr"] != "none" and not _NUMBER.fullmatch(v["pr"]):
        raise PartError("has a pr that is not a whole number or none")
    for key, limit in (("what", 2000), ("tests", 200)):
        if "|" in v[key]:
            raise PartError(f"has a pipe in {key}")
        if len(v[key]) > limit:
            raise PartError(f"has a {key} longer than {limit} characters")
    return StatusPart(_part_id(name), v["date"], v["pr"], v["what"], v["tests"], free or "")


def read_limits_part(name: str, raw: bytes) -> LimitsPart:
    """W9.R14.2. A limits part: section, title, optionally number (written by the build), a blank line, the body."""
    text = _decode(raw)
    header, body = _header_and_rest(text)
    v = _pairs(header, ("section", "title", "number"), ("section", "title"))
    for key, limit in (("section", 120), ("title", 200)):
        if "|" in v[key]:
            raise PartError(f"has a pipe in {key}")
        if len(v[key]) > limit:
            raise PartError(f"has a {key} longer than {limit} characters")
    if v["section"].startswith("#"):
        raise PartError("has a section that starts with #")
    number = None
    if "number" in v:
        if not _NUMBER.fullmatch(v["number"]):
            raise PartError("has a number that is not a whole number from 1 without a leading zero")
        number = int(v["number"])
    if body is None or not body.strip():
        raise PartError("has no body")
    fence = None
    for line in body.split("\n"):
        m = _FENCE.match(line)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            continue
        if fence is None and _BODY_HEADING.match(line):
            raise PartError("has a heading of level 1 to 3 in the body (the build writes those)")
    return LimitsPart(_part_id(name), v["section"], v["title"], number, body)


def _part_id(name: str) -> str:
    return name[:-3] if name.endswith(".md") else name


def _check_name(name: str) -> None:
    if not name.endswith(".md") or not _ID.fullmatch(name[:-3]):
        raise PartError("is not a part file (a name is letters, digits, hyphens and underscores, then .md)")
    if name.startswith(RESERVED_PREFIX):
        raise PartError(f"has a name that starts with {RESERVED_PREFIX}, which is kept for the frozen base")


# ---------------------------------------------------------------- reading the folders

def list_names(directory: Path) -> list:
    """The names in a folder in one fixed order, whatever order the file system lists them in."""
    return sorted(os.listdir(directory))


def _read_file(path: Path, limit: int) -> bytes:
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise PartError("is not a regular file (a link, a folder or a device)")
    try:
        return fsutil.read_regular(path, limit + 1)
    except OSError:
        raise PartError("could not be read") from None


def parse_dir(root: Path, kind: str):
    """(parts, problems) of one parts folder. Every file that is not the frozen base must be a good part."""
    rel = STATUS_DIR if kind == "status" else LIMITS_DIR
    base = STATUS_BASE if kind == "status" else LIMITS_BASE
    reader = read_status_part if kind == "status" else read_limits_part
    folder = Path(root) / rel
    try:
        ok = stat.S_ISDIR(os.lstat(folder).st_mode)
    except OSError:
        ok = False
    if not ok:
        return [], [f"{rel}: the folder is missing or is a link"]
    parts, problems, seen = [], [], {}
    for name in list_names(folder):
        if name in base:
            continue
        where = f"{rel}/{name}"
        try:
            _check_name(name)
            folded = name.casefold()
            if folded in seen:
                raise PartError(f"has the same id as {seen[folded]} apart from letter case")
            seen[folded] = name
            part = reader(name, _read_file(folder / name, MAX_PART_BYTES))
            parts.append(replace(part, rel=where))
        except PartError as e:
            problems.append(f"{where}: {e}")
        except OSError:
            problems.append(f"{where}: could not be read")
    return parts, problems


# ---------------------------------------------------------------- the frozen base and its migration

def split_status_log(text: str):
    """The migration (once): today's docs/status-log.md as (head, rows, tail). head ends with the table header, rows
    are the data rows, tail starts at "A blank count means"; head + rows + "\\n" + tail is the text, byte for byte."""
    if not text.endswith("\n"):
        raise PartError("the status log does not end with a newline")
    lines = [line + "\n" for line in text.split("\n")[:-1]]
    try:
        i = next(n for n, line in enumerate(lines) if line.startswith(_TABLE_HEAD))
    except StopIteration:
        raise PartError("the status log has no table of pull requests") from None
    if i + 1 >= len(lines) or lines[i + 1] != _TABLE_SEP + "\n":
        raise PartError("the table of pull requests has no separator line")
    j = i + 2
    while j < len(lines) and lines[j].startswith("| ") and lines[j].endswith("|\n"):
        j += 1
    if j + 1 >= len(lines) or lines[j] != "\n" or not lines[j + 1].startswith(_TAIL_START):
        raise PartError("the rows are not followed by a blank line and the text 'A blank count means'")
    return "".join(lines[:i + 2]), "".join(lines[i + 2:j]), "".join(lines[j + 1:])


def _validate_status_base(head: str, rows: str, tail: str) -> list:
    problems = []
    if not head.endswith(_TABLE_SEP + "\n") or _TABLE_HEAD not in head:
        problems.append(f"{STATUS_DIR}/00-head.md: does not end with the table header and its separator line")
    if any(not (r.startswith("| ") and r.endswith("|")) for r in rows.split("\n")[:-1]) or (rows and not rows.endswith("\n")):
        problems.append(f"{STATUS_DIR}/00-rows.md: holds a line that is not a table row")
    if not tail.startswith(_TAIL_START) or not tail.endswith("\n"):
        problems.append(f"{STATUS_DIR}/00-tail.md: does not start with '{_TAIL_START}' or does not end with a newline")
    return problems


def _read_base_text(root: Path, rel: str, problems: list):
    try:
        raw = _read_file(Path(root) / rel, MAX_BASE_BYTES)
        return raw.decode("utf-8")
    except PartError as e:
        problems.append(f"{rel}: {e}")
    except UnicodeDecodeError:
        problems.append(f"{rel}: is not UTF-8 text")
    except OSError:
        problems.append(f"{rel}: is missing")
    return None


# ---------------------------------------------------------------- order and numbers

def status_key(part: StatusPart) -> tuple:
    """Newest first when sorted in reverse: the date, then the pull request number (none is lowest), then the id."""
    return (part.date, int(part.pr) if part.pr.isdigit() else 0, part.id)


def limits_key(part: LimitsPart, date: str) -> tuple:
    """The order in which parts without a number get theirs: the date of the task's status part, then the id."""
    return (date, part.id)


def assign_numbers(ids: list, start: int) -> dict:
    """Consecutive numbers from `start`, in the order given."""
    return {i: start + n for n, i in enumerate(ids)}


def _base_numbers(text: str):
    """(largest entry number, the `## ` section headings) of the limits base, outside code blocks."""
    biggest, sections, fence = 0, set(), None
    for line in text.split("\n"):
        m = _FENCE.match(line)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            continue
        if fence:
            continue
        n = re.match(r"^### (\d+)\. ", line)
        if n:
            biggest = max(biggest, int(n.group(1)))
        h = re.match(r"^## (.+?)\s*$", line)
        if h:
            sections.add(h.group(1))
    return biggest, sections


# ---------------------------------------------------------------- composing the two files

def status_row(part: StatusPart) -> str:
    pr = PR_NONE_TEXT if part.pr == "none" else part.pr
    row = f"| {part.date} | {pr} | {part.what} |"
    return row + (f" {part.tests} |" if part.tests != "none" else " |")


def compose_status(head: str, rows: str, tail: str, parts: list) -> str:
    new = "".join(status_row(p) + "\n" for p in sorted(parts, key=status_key, reverse=True))
    return head + new + rows + "\n" + tail


def compose_limits(base: str, parts: list) -> str:
    """The base, then each section in the order of the first part (by number) that uses it."""
    ordered = sorted(parts, key=lambda p: p.number)
    sections = []
    for p in ordered:
        if p.section not in sections:
            sections.append(p.section)
    out = [base]
    for s in sections:
        out.append(f"\n## {s}\n")
        for p in ordered:
            if p.section == s:
                out.append(f"\n### {p.number}. {p.title}\n\n{p.body}\n")
    return "".join(out)


def _limits_text(part: LimitsPart) -> bytes:
    return f"section: {part.section}\ntitle: {part.title}\nnumber: {part.number}\n\n{part.body}\n".encode("utf-8")


# ---------------------------------------------------------------- the checker of the output

def _outside_code(text: str) -> list:
    out, fence = [], None
    for n, line in enumerate(text.split("\n"), 1):
        m = _FENCE.match(line)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            continue
        if fence is None:
            out.append((n, line))
    return out


def _slug(heading: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).strip().lower()
    return "".join(c for c in text if c.isalnum() or c in " -_").replace(" ", "-")


def _anchors(text: str) -> set:
    seen, out = {}, set()
    for _n, line in _outside_code(text):
        m = _HEADING.match(line)
        if m:
            base = _slug(m.group(2))
            k = seen.get(base, 0)
            out.add(base if k == 0 else f"{base}-{k}")
            seen[base] = k + 1
    return out


def _links(text: str) -> list:
    """(line number, target) of every Markdown link outside code blocks and code spans."""
    return [(n, m.group(1)) for n, line in _outside_code(text) for m in _LINK.finditer(_CODE_SPAN.sub("", line))]


def check_output(root: Path, status: str, limits: str) -> list:
    """The documentation rules of tests/test_docs.py for the two built files, on the text before it is written:
    no em dash, the four parts and under 300 lines for the status log, every relative link and #anchor resolves
    (a link to one of the two files reads the built text). Empty list when all is well."""
    root = Path(root).resolve()
    built = {(root / STATUS_FILE).resolve(): status, (root / LIMITS_FILE).resolve(): limits}
    names = {(root / STATUS_FILE).resolve(): STATUS_FILE, (root / LIMITS_FILE).resolve(): LIMITS_FILE}
    problems = []
    for path, text in built.items():
        rel = names[path]
        for n, line in enumerate(text.split("\n"), 1):
            if EM_DASH in line:
                problems.append(f"{rel} line {n}: an em dash")
        for n, target in _links(text):
            problems.extend(_link_problem(root, path, rel, n, target, built))
    found = [h for lvl, h in ((len(m.group(1)), m.group(2)) for _n, line in _outside_code(status)
                              for m in [_HEADING.match(line)] if m) if lvl == 2 and h in DOC_PARTS]
    if found != list(DOC_PARTS):
        problems.append(f"{STATUS_FILE}: the parts are {found}, not {list(DOC_PARTS)} in this order")
    lines = len(status.rstrip("\n").split("\n"))
    if lines >= MAX_STATUS_LINES:
        problems.append(f"{STATUS_FILE} has {lines} lines, not under {MAX_STATUS_LINES}")
    return problems


def _link_problem(root, path, rel, n, target, built) -> list:
    if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # http, https, mailto: never fetched
        return []
    target_path, _, anchor = target.partition("#")
    dest = (path.parent / target_path).resolve() if target_path else path
    try:
        dest.relative_to(root)
    except ValueError:
        return [f"{rel} line {n}: the link {target} points outside the repo"]
    if dest not in built and not dest.exists():
        return [f"{rel} line {n}: the link {target} does not resolve"]
    if anchor and dest.suffix == ".md":
        try:
            text = built[dest] if dest in built else dest.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return [f"{rel} line {n}: the link {target} does not resolve"]
        if anchor not in _anchors(text):
            return [f"{rel} line {n}: the anchor #{anchor} is not a heading of {target_path or rel}"]
    return []


# ---------------------------------------------------------------- plan, build, check

def plan(root) -> Plan:
    """Everything the build would do, in memory. Raises PartsRefused, and writes nothing."""
    root = Path(root)
    problems = []
    head = _read_base_text(root, f"{STATUS_DIR}/00-head.md", problems)
    rows = _read_base_text(root, f"{STATUS_DIR}/00-rows.md", problems)
    tail = _read_base_text(root, f"{STATUS_DIR}/00-tail.md", problems)
    base = _read_base_text(root, f"{LIMITS_DIR}/00-base.md", problems)
    if None not in (head, rows, tail):
        problems += _validate_status_base(head, rows, tail)
    if base is not None and not base.endswith("\n"):
        problems.append(f"{LIMITS_DIR}/00-base.md: does not end with a newline")
    status_parts, p1 = parse_dir(root, "status")
    limits_parts, p2 = parse_dir(root, "limits")
    problems += p1 + p2
    for rel in (STATUS_FILE, LIMITS_FILE):
        try:
            if stat.S_ISLNK(os.lstat(Path(root) / rel).st_mode):
                problems.append(f"{rel}: is a link, and the build does not write through links")
        except OSError:
            pass
    if not (Path(root) / "docs").is_dir():
        problems.append("docs: the folder is missing")
    if problems:
        raise PartsRefused(problems)

    dates = {p.id: p.date for p in status_parts}
    for p in limits_parts:
        if p.id not in dates:
            problems.append(f"{p.rel}: has no status part with the same id ({STATUS_DIR}/{p.id}.md)")
    biggest, base_sections = _base_numbers(base)
    for p in limits_parts:
        if p.section in base_sections:
            problems.append(f"{p.rel}: has a section the frozen base already has (name a new section)")
    numbered = [p for p in limits_parts if p.number is not None]
    floor = max(FIRST_NUMBER_AFTER, biggest)  # the first number a part gets is floor + 1
    expected = set(range(floor + 1, floor + 1 + len(numbered)))
    counts = {}
    for p in numbered:
        counts[p.number] = counts.get(p.number, 0) + 1
    for p in numbered:
        if p.number <= floor:
            problems.append(f"{p.rel}: has a number below the first free one (the base or the W9 spec uses it)")
        elif counts[p.number] > 1:
            problems.append(f"{p.rel}: has a number that another part also has")
        elif p.number not in expected:
            problems.append(f"{p.rel}: has a number the build did not give (numbers go on without a gap)")
    if problems:
        raise PartsRefused(problems)

    fresh = sorted((p for p in limits_parts if p.number is None), key=lambda p: limits_key(p, dates[p.id]))
    start = floor + len(numbered) + 1
    given = assign_numbers([p.id for p in fresh], start)
    final, written = [], {}
    for p in limits_parts:
        if p.number is None:
            p = replace(p, number=given[p.id])
            written[p.rel] = _limits_text(p)
        final.append(p)
    numbers = [p.number for p in final]
    if len(set(numbers)) != len(numbers):
        raise PartsRefused(["docs-parts/known-limits: two entries would get the same number"])

    status = compose_status(head, rows, tail, status_parts)
    limits = compose_limits(base, final)
    found = check_output(root, status, limits)
    if found:
        raise PartsRefused(found)
    return Plan(status, limits, written, len(status_parts), len(limits_parts))


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _current(root: Path, rel: str):
    path = Path(root) / rel
    try:
        return path.read_bytes()
    except OSError:
        return None


def build(root) -> Result:
    """Write the numbers into the parts that lack one, then docs/status-log.md and docs/KNOWN-LIMITS.md."""
    root = Path(root)
    try:
        p = plan(root)
    except PartsRefused as e:
        return Result(2, ["docs: the build is refused and nothing was written:"] + e.problems)
    for rel, data in p.numbered.items():
        fsutil.atomic_write(root / rel, data)
    changed = []
    for rel, text in ((STATUS_FILE, p.status), (LIMITS_FILE, p.limits)):
        data = text.encode("utf-8")
        if _current(root, rel) != data:
            fsutil.atomic_write(root / rel, data)
            changed.append(rel)
    if not changed and not p.numbered:
        return Result(0, [f"docs: up to date ({_count(p.status_parts, 'status part')}, {_count(p.limits_parts, 'limits part')}). "
                          "Nothing was written."])
    lines = [f"docs: built from {_count(p.status_parts, 'status part')} and {_count(p.limits_parts, 'limits part')}."]
    lines += [f"Wrote {rel}." for rel in changed]
    if p.numbered:
        lines.append(f"Gave a number to {_count(len(p.numbered), 'limits part')} and wrote it into the part file.")
    return Result(0, lines)


def check(root) -> Result:
    """0 when the two files equal the build and every limits part has its number; 2 otherwise. Writes nothing."""
    root = Path(root)
    try:
        p = plan(root)
    except PartsRefused as e:
        return Result(2, ["docs: the parts are refused:"] + e.problems)
    lines = []
    for rel, text in ((STATUS_FILE, p.status), (LIMITS_FILE, p.limits)):
        if _current(root, rel) != text.encode("utf-8"):
            lines.append(f"docs: {rel} differs from the build of the parts")
    n = len(p.numbered)
    if n:
        lines.append(f"docs: {_count(n, 'part')} not yet built (no number yet)")
    if lines:
        return Result(2, lines + ["Run 'umwayi goal docs build'."])
    return Result(0, [f"docs: up to date ({_count(p.status_parts, 'status part')}, {_count(p.limits_parts, 'limits part')})."])
