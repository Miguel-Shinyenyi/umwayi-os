"""W19.1: guidance.yaml, a checked list of rules for the goal flow, each marked enforce, advise or owner.

- enforce: umwayi checks it in code (a registered check function) and refuses a task that breaks it.
- advise: one line that goes into an AI helper's prompt. Nothing is checked.
- owner: for the owner only. Nothing is checked and nothing is put in a prompt.

The code checks that a record exists and is well formed. It never claims that the content is true.

The loader fails closed. A file that is missing, a source that has changed, or a source that cannot be found is
Ask me first (exit 3): stop and ask the owner. A file that is malformed (an unknown kind, an enforce entry with no
registered check, a duplicate id, any key or value outside the table below) is a config error (exit 64). Messages
are fixed words and never carry text from guidance.yaml or from a source file.

Tiers. Every entry has a `tier`, a whole number from 1 to 6, and the lower number wins when two entries disagree:
1 safety (rules gate, kill switch, fail closed, Ask me first); 2 owner decisions and standing rules; 3 hub hard
rules (core-rules, understanding-first); 4 builder rules; 5 practices (agent-practices, the 111 concerns, Kiro
ten); 6 advisory prompt lines. An entry may list `overrides` (ids of other entries). A lower tier may never relax a
higher one: an entry whose `overrides` names an entry with a lower tier number, an unknown id, itself, or the same
id twice is refused. `resolve` picks the winner of two entries.

Source repo. Every entry says where its source lives, `source_repo`: `umwayi-os` (this repo) or `hub` (the owner's
private hub repo, whose files are never copied here). For `umwayi-os` the loader checks `source_hash` against the
file, as below. For `hub` the loader reads nothing: `source` is `FILE.md#N` (the hub file name and the rule number;
a few practices have a name instead of a number, such as `verification-first`) and `source_hash` is the SHA-256 of
the whole hub file, as the owner recorded it. `umwayi guidance verify --hub PATH` compares it with the real file
(Ask me first on a mismatch), and `umwayi guidance list` shows a hub entry as unverified unless it was verified in
that same run.

Source and source_hash for `umwayi-os`. `source` is `PATH#N` or `PATH#HEADING#N`: the repo relative file, optionally the section
whose heading starts with HEADING, and the numbered rule `N. ...` in it. The rule must be on exactly one line
(lines inside a code fence do not count). `source_hash` is the SHA-256 of that line, trailing spaces removed, in
lower case hex. If the line is edited, moved to another number or removed, the hash no longer matches and the
loader stops. Nobody has to re-hash by hand without reading the change: `compute_hash` prints the new value.

The file is read with the strict reader of `umwayi/miniyaml.py` (no tabs, anchors, tags, block scalars or duplicate
keys), and then every key and value is checked against the table in `parse`. Standard library only, no network.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import Path
from typing import Callable

from umwayi import fsutil, miniyaml
from umwayi.errors import ConfigError, UmwayiError, UsageError

EM_DASH = "\u2014"
FILE_NAME = "guidance.yaml"
MAX_BYTES = 256 * 1024
MAX_ENTRIES = 200
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_RECORD_BYTES = 64 * 1024
KINDS = ("enforce", "advise", "owner")
APPLIES_TO = ("goal", "task", "pr", "release")
RUN_FOR_TASK = ("goal", "task", "pr")  # a task record is checked at these levels; "release" is a later flow

_ID = re.compile(r"^[a-z][a-z0-9-]{2,47}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_NUMBER = re.compile(r"^[1-9][0-9]{0,2}$")
_COMMON = ("id", "source", "text", "kind", "applies_to", "source_hash", "tier", "source_repo")
SOURCE_REPOS = ("umwayi-os", "hub")
_HUB_SOURCE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]{0,63}\.md)#([1-9][0-9]{0,2}|[a-z][a-z0-9-]{1,47})$")
OPTIONAL = ("overrides",)
TIER_MIN, TIER_MAX = 1, 6
MAX_OVERRIDES = 20


class GuidanceError(ConfigError):
    """guidance.yaml is malformed or outside the allowed subset. The command line exits 64."""


class AskFirst(UmwayiError):
    """Stop and ask the owner: Ask me first. The command line exits 3."""


class SourceChanged(AskFirst):
    """A source file or rule no longer matches its hash, or cannot be found. Stop and ask the owner."""


@dataclasses.dataclass(frozen=True)
class Entry:
    id: str
    source: str
    text: str
    kind: str
    applies_to: str
    source_hash: str
    tier: int
    source_repo: str = "umwayi-os"
    check: str | None = None
    prompt_line: str | None = None
    overrides: tuple = ()


# ---------------------------------------------------------------- the checks

def _blank(v) -> bool:
    return not isinstance(v, str) or not v.strip()


def goal_sentence_present(record) -> str | None:
    """The task has a goal sentence: a string with something other than white space."""
    if not isinstance(record, dict) or _blank(record.get("goal")):
        return "the task has no goal sentence"
    return None


def consequences_and_undo_present(record) -> str | None:
    """Consequences and undo steps are both there and not empty."""
    if not isinstance(record, dict):
        return "the task has no consequences and no undo steps"
    if _blank(record.get("consequences")):
        return "the task has no consequences written down"
    if _blank(record.get("undo")):
        return "the task has no undo steps written down"
    return None


def acceptance_checks_present(record) -> str | None:
    """At least one acceptance check, each one a string with something in it, before any work."""
    items = record.get("acceptance_checks") if isinstance(record, dict) else None
    if not isinstance(items, list) or not items:
        return "the task has no acceptance checks"
    if any(_blank(x) for x in items):
        return "the task has an acceptance check that is empty"
    return None


def one_open_pr(record) -> str | None:
    """At most one open pull request for the task. `open_prs` is a list the caller fills (this module makes no
    network call); a missing or malformed list is refused, an empty one is fine."""
    prs = record.get("open_prs") if isinstance(record, dict) else None
    if not isinstance(prs, list):
        return "the task does not say which pull requests are open"
    for x in prs:
        if isinstance(x, bool) or not isinstance(x, (int, str)) or (isinstance(x, str) and not x.strip()):
            return "the task lists an open pull request that is not a number or a name"
    if len(prs) > 1:
        return "the task has more than one open pull request"
    return None


CHECKS: dict[str, Callable[[object], str | None]] = {
    "goal_sentence_present": goal_sentence_present,
    "consequences_and_undo_present": consequences_and_undo_present,
    "acceptance_checks_present": acceptance_checks_present,
    "one_open_pr": one_open_pr,
}


# ---------------------------------------------------------------- the sources

def _parse_source(source: str) -> tuple[str, str | None, int]:
    parts = source.split("#")
    if len(parts) not in (2, 3):
        raise GuidanceError("guidance.yaml: a source is not PATH#N or PATH#HEADING#N")
    path, number = parts[0], parts[-1]
    heading = parts[1] if len(parts) == 3 else None
    if (not path or path.startswith("/") or "\\" in path or any(c in path for c in "\x00\r\n")
            or any(p in ("", ".", "..") for p in path.split("/"))):
        raise GuidanceError("guidance.yaml: a source path is not a repo relative path")
    if heading is not None and (not heading.strip() or heading != heading.strip()):
        raise GuidanceError("guidance.yaml: a source heading is empty")
    if not _NUMBER.match(number):
        raise GuidanceError("guidance.yaml: a source rule number is not a number from 1 to 999")
    return path, heading, int(number)


def _read_source(root: Path, path: str) -> list[str]:
    base = Path(root).resolve()
    try:
        full = (base / path).resolve()
        full.relative_to(base)
        data = fsutil.read_regular(full, MAX_SOURCE_BYTES)
        return data.decode("utf-8").splitlines()
    except (OSError, ValueError):
        raise SourceChanged("a source file of guidance.yaml cannot be read or is outside the repo: "
                            "stop and ask the owner") from None


def _rule_line(root: Path, source: str) -> str:
    path, heading, n = _parse_source(source)
    lines = _read_source(root, path)
    marks: list[tuple[int, str]] = []  # (index, kind) of heading lines and rule lines outside code fences
    fence = False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if re.match(r"^#{1,6} ", ln):
            marks.append((i, "h"))
        elif ln.startswith(f"{n}. "):
            marks.append((i, "r"))
    lo, hi = 0, len(lines)
    if heading is not None:
        starts = [i for i, k in marks if k == "h"
                  and (lines[i].lstrip("#").strip() == heading or lines[i].lstrip("#").strip().startswith(heading + " "))]
        if len(starts) != 1:
            raise SourceChanged("a source section of guidance.yaml cannot be found: stop and ask the owner")
        lo = starts[0] + 1
        nxt = [i for i, k in marks if k == "h" and i > starts[0]]
        hi = nxt[0] if nxt else len(lines)
    found = [lines[i] for i, k in marks if k == "r" and lo <= i < hi]
    if len(found) != 1:
        raise SourceChanged("a source rule of guidance.yaml cannot be found exactly once: stop and ask the owner")
    return found[0].rstrip()


def compute_hash(root: Path, source: str) -> str:
    """The value `source_hash` must have for this source, as the file is now."""
    return hashlib.sha256(_rule_line(root, source).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- the loader

def _text_ok(v, lo: int = 10, hi: int = 200) -> bool:
    return (isinstance(v, str) and lo <= len(v) <= hi and v == v.strip() and EM_DASH not in v
            and all(c.isprintable() for c in v))


def parse(text: str, root: Path, registry: dict | None = None) -> list[Entry]:
    """The entries of a guidance.yaml text, checked against the sources under `root`."""
    registry = CHECKS if registry is None else registry
    if EM_DASH in text:
        raise GuidanceError("guidance.yaml: an em dash is not allowed")
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError as e:
        msg = str(e).split(":")[0] if str(e).startswith("line ") else "bad format"
        raise GuidanceError(f"guidance.yaml: not in the allowed format ({msg})") from None
    if not isinstance(data, dict) or set(data) != {"version", "guidance"}:
        raise GuidanceError("guidance.yaml: it must hold exactly the keys version and guidance")
    if data["version"] != 1 or isinstance(data["version"], bool):
        raise GuidanceError("guidance.yaml: version must be 1")
    items = data["guidance"]
    if not isinstance(items, list) or not items:
        raise GuidanceError("guidance.yaml: guidance must be a list with at least one entry")
    if len(items) > MAX_ENTRIES:
        raise GuidanceError("guidance.yaml: too many entries")
    entries: list[Entry] = []
    seen: set[str] = set()
    for it in items:
        entries.append(_entry(it, registry, seen))
    _check_overrides(entries)
    hub_hash: dict[str, str] = {}
    for e in entries:  # one hub file has one hash, whatever rule of it an entry names
        if e.source_repo == "hub":
            name = e.source.split("#")[0]
            if hub_hash.setdefault(name, e.source_hash) != e.source_hash:
                raise GuidanceError("guidance.yaml: two hub entries give different hashes for one hub file")
    for e in entries:  # sources last: a malformed file is 64 before any file is read
        if e.source_repo == "umwayi-os" and compute_hash(root, e.source) != e.source_hash:
            raise SourceChanged("a source of guidance.yaml no longer matches its source_hash: stop and ask the owner")
    return entries


def _entry(it, registry: dict, seen: set) -> Entry:
    if not isinstance(it, dict):
        raise GuidanceError("guidance.yaml: an entry is not a mapping")
    kind = it.get("kind")
    if kind not in KINDS:
        raise GuidanceError("guidance.yaml: an entry has an unknown kind")
    extra = {"enforce": "check", "advise": "prompt_line", "owner": None}[kind]
    allowed = set(_COMMON) | ({extra} if extra else set())
    if set(it) - allowed - set(OPTIONAL):
        raise GuidanceError("guidance.yaml: an entry has a key that its kind does not allow")
    if allowed - set(it):
        raise GuidanceError("guidance.yaml: an entry is missing a key")
    for k in allowed - {"tier"}:
        if not isinstance(it[k], str):
            raise GuidanceError("guidance.yaml: every value of an entry must be a string")
    tier = it["tier"]
    if isinstance(tier, bool) or not isinstance(tier, int):
        raise GuidanceError("guidance.yaml: a tier is not a whole number")
    if not TIER_MIN <= tier <= TIER_MAX:
        raise GuidanceError("guidance.yaml: a tier is not from 1 to 6")
    overrides = it.get("overrides", [])
    if (not isinstance(overrides, list) or len(overrides) > MAX_OVERRIDES
            or any(not isinstance(x, str) or not _ID.match(x) for x in overrides)):
        raise GuidanceError("guidance.yaml: overrides is not a short list of entry ids")
    if not _ID.match(it["id"]):
        raise GuidanceError("guidance.yaml: an entry id is not 3 to 48 characters of a-z, 0-9 and hyphen")
    if it["id"] in seen:
        raise GuidanceError("guidance.yaml: an id is used twice")
    seen.add(it["id"])
    if it["applies_to"] not in APPLIES_TO:
        raise GuidanceError("guidance.yaml: an entry has an unknown applies_to")
    if not _text_ok(it["text"]):
        raise GuidanceError("guidance.yaml: a text is not one printable line of 10 to 200 characters")
    if extra == "prompt_line" and not _text_ok(it["prompt_line"]):
        raise GuidanceError("guidance.yaml: a prompt_line is not one printable line of 10 to 200 characters")
    if extra == "check" and it["check"] not in registry:
        raise GuidanceError("guidance.yaml: an enforce entry names a check that is not registered")
    if it["source_repo"] not in SOURCE_REPOS:
        raise GuidanceError("guidance.yaml: source_repo is not umwayi-os or hub")
    if not _HASH.match(it["source_hash"]):
        raise GuidanceError("guidance.yaml: a source_hash is not 64 lower case hex characters")
    if it["source_repo"] == "hub":
        if not _HUB_SOURCE.match(it["source"]):
            raise GuidanceError("guidance.yaml: a hub source is not FILE.md#N")
    else:
        _parse_source(it["source"])
    return Entry(id=it["id"], source=it["source"], text=it["text"], kind=kind, applies_to=it["applies_to"],
                 source_hash=it["source_hash"], tier=tier, source_repo=it["source_repo"], check=it.get("check"),
                 prompt_line=it.get("prompt_line"), overrides=tuple(overrides))


def _check_overrides(entries: list) -> None:
    """A lower tier may never relax a higher one: `overrides` may name only entries of the same or a lower
    priority (a tier number equal or higher than the entry's own). Unknown ids, itself and repeats are refused."""
    by_id = {e.id: e for e in entries}
    for e in entries:
        if len(set(e.overrides)) != len(e.overrides):
            raise GuidanceError("guidance.yaml: an overrides list names an id twice")
        for target in e.overrides:
            t = by_id.get(target)
            if t is None:
                raise GuidanceError("guidance.yaml: overrides names an id that is not an entry")
            if t.id == e.id:
                raise GuidanceError("guidance.yaml: an entry overrides itself")
            if t.tier < e.tier:
                raise GuidanceError("guidance.yaml: overrides names an entry of a higher tier "
                                    "(a lower tier may never relax a higher one)")


def load(root: Path, registry: dict | None = None) -> list[Entry]:
    """Read `guidance.yaml` under `root`. See the module text for what each failure means."""
    path = Path(root) / FILE_NAME
    try:
        raw = fsutil.read_regular(path, MAX_BYTES)
    except FileNotFoundError:
        raise AskFirst("guidance.yaml is missing: stop and ask the owner") from None
    except fsutil.TooBig:
        raise GuidanceError("guidance.yaml: the file is too big") from None
    except OSError:
        raise AskFirst("guidance.yaml cannot be read: stop and ask the owner") from None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise GuidanceError("guidance.yaml: the file is not UTF-8") from None
    return parse(text, Path(root), registry)


# ---------------------------------------------------------------- using it

def check_task(entries: list[Entry], record) -> list[tuple[str, str]]:
    """Run every enforce entry that applies to a task record. Returns (id, reason) for each one it breaks, in
    file order. A check that raises counts as broken. advise and owner entries never refuse anything."""
    out: list[tuple[str, str]] = []
    for e in entries:
        if e.kind != "enforce" or e.applies_to not in RUN_FOR_TASK:
            continue
        try:
            reason = CHECKS[e.check](record)
        except Exception:
            reason = "the check could not run"
        if reason:
            out.append((e.id, reason))
    return out


def resolve(entries: list, id_a: str, id_b: str) -> Entry:
    """The winner of two entries. The lower tier number wins. In the same tier an enforce entry beats an advise
    entry. Anything else (two enforce entries, or any other pair in one tier, or an id that is not an entry) cannot
    be decided by the code: AskFirst, Ask me first (exit 3), with a one line reason."""
    by_id = {e.id: e for e in entries}
    a, b = by_id.get(id_a), by_id.get(id_b)
    if a is None or b is None:
        raise AskFirst("resolve: an id is not an entry of guidance.yaml: stop and ask the owner")
    if a.id == b.id:
        return a
    if a.tier != b.tier:
        return a if a.tier < b.tier else b
    kinds = {a.kind, b.kind}
    if kinds == {"enforce", "advise"}:
        return a if a.kind == "enforce" else b
    if kinds == {"enforce"}:
        raise AskFirst("two enforce rules of the same tier disagree: stop and ask the owner")
    raise AskFirst("two rules of the same tier cannot be ranked: stop and ask the owner")


@dataclasses.dataclass(frozen=True)
class Result:
    code: int  # 0 Yes, 3 Ask me first
    lines: list


def guard(root: Path, task_file: str | None) -> Result:
    """`umwayi goal guard [TASKFILE]`. Loads guidance.yaml (errors propagate: GuidanceError is 64, AskFirst is 3).
    With a task record (a JSON object in a file) it also runs the enforce checks: a broken one is Ask me first
    with one line, the first reason."""
    entries = load(root)
    if task_file is None:
        n = len(entries)
        return Result(0, [f"Yes: guidance.yaml is well formed, {n} {'entry' if n == 1 else 'entries'}, "
                          f"every source matches."])
    try:
        raw = fsutil.read_regular(Path(task_file), MAX_RECORD_BYTES)
        record = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        record = None
    if not isinstance(record, dict):
        return Result(3, ["Ask me first: the task record cannot be read as a JSON object."])
    broken = check_task(entries, record)
    if broken:
        i, reason = broken[0]
        return Result(3, [f"Ask me first: {reason} (guidance {i})."])
    return Result(0, ["Yes: the task record passes every enforce rule."])


# ---------------------------------------------------------------- the hub (owner commands)

HUB_MAX_BYTES = 4 * 1024 * 1024


def hub_status(entries: list, hub_root: Path | None) -> dict:
    """For each entry id: `verified` (a hub file whose SHA-256 equals the stored one, or an umwayi-os entry, which
    the loader already checked), `unverified` (a hub entry and no hub checkout was given), or `mismatch` (the hub
    file is missing, is not a plain file in the checkout, or has another hash). Reads only the named hub files."""
    out: dict[str, str] = {}
    cache: dict[str, str] = {}
    base = Path(hub_root).resolve() if hub_root is not None else None
    for e in entries:
        if e.source_repo != "hub":
            out[e.id] = "verified"
        elif base is None:
            out[e.id] = "unverified"
        else:
            name = e.source.split("#")[0]
            if name not in cache:
                try:
                    full = (base / name).resolve()
                    full.relative_to(base)
                    cache[name] = hashlib.sha256(fsutil.read_regular(full, HUB_MAX_BYTES)).hexdigest()
                except (OSError, ValueError):
                    cache[name] = ""
            out[e.id] = "verified" if cache[name] == e.source_hash else "mismatch"
    return out


def verify_hub(root: Path, hub_path: str) -> Result:
    """`umwayi guidance verify --hub PATH`: compare the stored hub hashes with the real files. Ask me first (3) on
    any mismatch, with one line that names entry ids and no file text. A path that is not a folder is a usage error."""
    entries = load(root)
    hub = Path(hub_path)
    if not hub.is_dir():
        raise UsageError("--hub must be the folder of a hub checkout")
    status = hub_status(entries, hub)
    hub_ids = [e.id for e in entries if e.source_repo == "hub"]
    bad = [i for i in hub_ids if status[i] != "verified"]
    if bad:
        return Result(3, [f"Ask me first: {len(bad)} of {len(hub_ids)} hub entries do not match the hub files "
                          f"({', '.join(bad)}). The hub checkout may be behind, or the file changed."])
    return Result(0, [f"Yes: all {len(hub_ids)} hub entries match the hub files."])


def listing(root: Path, hub_path: str | None = None) -> Result:
    """`umwayi guidance list [--hub PATH]`: one line per entry with kind, tier, source repo and status. A hub entry is
    unverified unless the hub checkout was given and its file matches; it is never shown as verified otherwise."""
    entries = load(root)
    hub = None
    if hub_path is not None:
        hub = Path(hub_path)
        if not hub.is_dir():
            raise UsageError("--hub must be the folder of a hub checkout")
    status = hub_status(entries, hub)
    lines = [f"{e.id}  {e.kind}  tier {e.tier}  {e.source_repo}  {status[e.id]}" for e in entries]
    n_un = sum(1 for e in entries if status[e.id] == "unverified")
    n_bad = sum(1 for e in entries if status[e.id] == "mismatch")
    lines.append(f"{len(entries)} entries, {n_un} unverified, {n_bad} mismatch.")
    return Result(3 if n_bad else 0, lines)
