"""W49: the provenance record of a goal task. The record, its storage and the sealed entry; no signing, no key.

One record per task, made when the task reaches `in review`, from the worktree at the tip the scope check saw: the SHA-256 of
every added or modified file, and for a `.py` file the SHA-256 of its parsed structure, deleted files by path only. It is kept
beside the work in `.umwayi/provenance/GOAL/TASK.json` and never inside it. One entry of source `umwayi provenance` in the
hash-chained logbook holds the hash of the record. No path and no content is in the entry.

Off by default (`umwayi.json`: `"provenance": {"record": true}`), because a record needs the hash chain and the owner's choice.
Not built here: the signature of the record and `umwayi verify` (they need the owner's key; see docs/provenance-design.md).
Without a signature the record is a record only: nothing may call a file "made by umwayi" from it.

Standard library only. Reads only the files the task changed, with O_NOFOLLOW. Writes one file, once, 0600 in a 0700 folder.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from umwayi import logbook
from umwayi.errors import UmwayiError

SOURCE = "umwayi provenance"
MAX_FILES = 2000
MAX_BYTES = 64 * 1024 * 1024
FINGERPRINT = "python-ast-v1"
FOLDER = ".umwayi/provenance"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_ID_G = re.compile(r"^G-\d{4,}$")
_ID_T = re.compile(r"^T-\d{2,}$")
_SHA = re.compile(r"^[0-9a-f]{40,64}$")

# the reasons a record is not made, in fixed words (the task goes to needs owner, cause `config`, or stops on a log failure)
REASONS = ("too_many", "too_big", "unreadable", "no_chain", "exists", "moved", "log")


class ProvenanceError(UmwayiError):
    def __init__(self, reason: str):
        assert reason in REASONS
        super().__init__(f"provenance: no record was made ({reason})")
        self.reason = reason


def structure_hash(raw: bytes) -> str | None:
    """SHA-256 of the parsed structure of Python source bytes, or None when they do not parse. Parsing the bytes, not decoded
    text, keeps the encoding line and a byte order mark meaning what Python reads."""
    try:
        tree = ast.parse(raw)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode("utf-8")).hexdigest()


def read_file(worktree: str, rel: str, left: int) -> bytes:
    """The bytes of one produced file, from the worktree, never through a link. `left` is the byte budget that remains."""
    path = os.path.join(worktree, *rel.split("/"))
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        raise ProvenanceError("unreadable") from None
    try:
        st = os.fstat(fd)
        if not (st.st_mode & 0o170000) == 0o100000:
            raise ProvenanceError("unreadable")
        if st.st_size > left:
            raise ProvenanceError("too_big")
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(left + 1)
    finally:
        os.close(fd)
    if len(data) > left:
        raise ProvenanceError("too_big")
    return data


def build(goal: str, task: str, base: str, tip: str, packet_sha256: str, changed: list, worktree: str, made_at: str) -> dict:
    """The record. `changed` is [(status letter, path)] from `git diff --name-status`: A and M get hashes, D is listed by path."""
    if len(changed) > MAX_FILES:
        raise ProvenanceError("too_many")
    files, removed, left = [], [], MAX_BYTES
    for code, rel in sorted(changed, key=lambda c: c[1]):
        if code.startswith("D"):
            removed.append(rel)
            continue
        raw = read_file(worktree, rel, left)
        left -= len(raw)
        files.append({"ast_sha256": structure_hash(raw) if rel.endswith(".py") else None, "bytes": len(raw), "path": rel,
                      "sha256": hashlib.sha256(raw).hexdigest()})
    return {"base": base, "files": files, "fingerprint": FINGERPRINT, "goal": goal, "kind": "umwayi-provenance",
            "made_at": made_at, "packet_sha256": packet_sha256, "python": f"{sys.version_info[0]}.{sys.version_info[1]}",
            "removed": removed, "task": task, "tip": tip, "version": 1}


def canonical(record: dict) -> bytes:
    return (json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def record_path(root, goal: str, task: str) -> Path:
    if not (_ID_G.match(goal) and _ID_T.match(task)):
        raise ValueError("goal or task id")
    return Path(root) / FOLDER / goal / f"{task}.json"


def store(root, goal: str, task: str, data: bytes) -> Path:
    """Write the record once: folders 0700, file 0600, through a temporary file and a link that fails when the record exists.
    An existing record is never overwritten."""
    path = record_path(root, goal, task)
    try:
        for d in (Path(root) / ".umwayi", Path(root) / FOLDER, path.parent):
            d.mkdir(mode=0o700, exist_ok=True)
        tmp = path.with_name(f".{task}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(tmp, path)  # fails when the record exists: never overwritten
            except FileExistsError:
                raise ProvenanceError("exists") from None
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except ProvenanceError:
        raise
    except OSError:
        raise ProvenanceError("unreadable") from None
    return path


def written_entry(when: str, goal: str, task: str, record: dict, data: bytes) -> logbook.Entry:
    """The entry that seals the record, in a fixed shape: ids, the record's hash and four counts. No path, no content."""
    sha = hashlib.sha256(data).hexdigest()
    with_fp = sum(1 for f in record["files"] if f["ast_sha256"])
    return logbook.Entry(
        when, SOURCE,
        f"record {goal} {task} written (sha256 {sha}); files {len(record['files'])}; with a fingerprint {with_fp}; "
        f"removed {len(record['removed'])}; python {record['python']}",
        f"the hash chain was intact before this entry; the task reached in review at tip {record['tip']}; the record was read back "
        "and its hash matched",
        "No produced file was changed, moved or written. The record is not signed. No path or content is in this entry.")


_WRITTEN = re.compile(r"record (G-\d{4,}) (T-\d{2,}) written \(sha256 ([0-9a-f]{64})\); files (\d{1,4}); with a fingerprint "
                      r"(\d{1,4}); removed (\d{1,4}); python (\d{1,2}\.\d{1,2})")


def parse_written(entry) -> dict | None:
    """The fields of a written entry, or None when the entry is not exactly of that shape (a hand edit is refused)."""
    if getattr(entry, "source", None) != SOURCE:
        return None
    m = _WRITTEN.fullmatch(getattr(entry, "added", "") or "")
    if not m:
        return None
    return {"goal": m.group(1), "task": m.group(2), "sha256": m.group(3), "files": int(m.group(4)),
            "fingerprints": int(m.group(5)), "removed": int(m.group(6)), "python": m.group(7)}


def has_chain(root) -> bool:
    try:
        return logbook.read_checked_chain(Path(root))[1] > 0
    except UmwayiError:
        return False


def make(root, goal: str, task: str, base: str, tip: str, packet_sha256: str, changed: list, worktree: str, when: str) -> dict:
    """Make, store and seal the record of one task. Needs the hash chain. Writes the file before the entry, and reads the file
    back and checks its hash before it appends the entry. Returns the parsed written entry. Raises ProvenanceError with a fixed
    reason; a record file already made is then left, never deleted."""
    if not has_chain(root):
        raise ProvenanceError("no_chain")
    record = build(goal, task, base, tip, packet_sha256, changed, worktree, when + "T00:00:00Z")
    data = canonical(record)
    path = store(root, goal, task, data)
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashlib.sha256(data).hexdigest():
            raise ProvenanceError("unreadable")
        entry = written_entry(when, goal, task, record, data)
        logbook.append(Path(root), entry)
    except ProvenanceError:
        raise
    except (OSError, UmwayiError):
        raise ProvenanceError("log") from None
    return parse_written(entry)


def compare(record: dict, path: str, raw: bytes, python: str | None = None) -> str:
    """How the bytes `raw` of `path` stand against a record that names it: `unchanged` (the bytes hash the same), `structure`
    (a `.py` file whose parsed structure is the same under the same Python minor version), `changed`, or `unnamed` (the record
    does not name the path). No signature is checked here: this is a comparison, not a proof of origin."""
    for f in record.get("files", ()):
        if f.get("path") != path:
            continue
        if hashlib.sha256(raw).hexdigest() == f.get("sha256"):
            return "unchanged"
        py = python or f"{sys.version_info[0]}.{sys.version_info[1]}"
        if f.get("ast_sha256") and path.endswith(".py") and record.get("python") == py and structure_hash(raw) == f["ast_sha256"]:
            return "structure"
        return "changed"
    return "unnamed"
