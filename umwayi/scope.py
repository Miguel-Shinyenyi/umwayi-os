"""W9.16: the scope of a task, checked while its helper runs (an overlay on the rules gate).

The goal supervisor writes one small JSON file per role run: the worktree, the files the packet allows and the task's two own files.
A Claude Code hook that was given `--scope FILE` passes it to `umwayi check --scope FILE`. For a tool call that writes a file (Write,
Edit, MultiEdit, NotebookEdit) whose path is not allowed, the answer is No, written in the entry as `The scope of the task gave No`.
The overlay only adds a No. It never turns a No or an Ask me first into a Yes, and a call that is not a file write is left to the rules.

  * A path is allowed when it is inside the worktree and `goalpacket.scope_violations` allows it (the same function as the scope check
    after the run: the files and folders of the packet, the two own files, nothing protected, no `..`, no absolute path outside).
  * A tester, a guide's check and a planning run get no files, so every file write of theirs is No.
  * Fail closed: a scope file that is missing, a link, too big or not of this shape makes every file write No.
  * Paths are compared as written (made absolute against the call's `cwd`, then normalised). A link in the worktree that points out is
    not followed here, so it is not caught: Landlock (step 6) is what stops that. A `Bash` command is not read: `sed -i` or `>` is not
    covered. The scope check after the run still finds both.
  * The file is written by the supervisor next to the goal's records; a helper that can write there can widen its scope. That is the
    same cooperative limit as every file the helper could reach until confinement is on.

Standard library only. Reads one small file; writes nothing.
"""
from __future__ import annotations

import json
import os
import posixpath
import stat

from umwayi import goalpacket as gp

MAX_BYTES = 64 * 1024
WRITE_TYPES = ("tool_write", "tool_edit", "tool_multiedit", "tool_notebookedit")
PATH_FIELDS = ("path",)
KEYS = ("version", "worktree", "files", "own")
STOPPED_BY = "the scope of the task"
REASON = "The scope of the task gave No: this file is outside the files of the packet."
UNREADABLE = "The scope of the task could not be read, so no file may be written."


class ScopeError(Exception):
    pass


def make(worktree: str, files, own) -> bytes:
    """The bytes of a scope file (what the supervisor writes). Raises ValueError for a worktree that is not an absolute path."""
    if not (isinstance(worktree, str) and worktree.startswith("/") and "\x00" not in worktree):
        raise ValueError("worktree")
    doc = {"version": 1, "worktree": posixpath.normpath(worktree), "files": [str(f) for f in files], "own": [str(o) for o in own]}
    return (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load(path) -> dict:
    """The scope of a file, strict. Raises ScopeError."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise ScopeError("missing") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
            raise ScopeError("not a small regular file")
        data = os.read(fd, MAX_BYTES + 1)
    finally:
        os.close(fd)
    try:
        doc = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ScopeError("not JSON") from None
    if not (isinstance(doc, dict) and tuple(sorted(doc)) == tuple(sorted(KEYS)) and doc["version"] == 1
            and isinstance(doc["worktree"], str) and doc["worktree"].startswith("/")
            and all(isinstance(doc[k], list) and all(isinstance(x, str) for x in doc[k]) for k in ("files", "own"))):
        raise ScopeError("wrong shape")
    return doc


def _relative(scope: dict, action: dict):
    """The path of a file-writing action relative to the worktree, or None when it is outside it or cannot be read."""
    raw = next((action[f] for f in PATH_FIELDS if isinstance(action.get(f), str)), None)
    if not raw or "\x00" in raw:
        return None
    base = action.get("cwd") if isinstance(action.get("cwd"), str) and action["cwd"].startswith("/") else scope["worktree"]
    full = posixpath.normpath(raw if raw.startswith("/") else posixpath.join(base, raw))
    wt = scope["worktree"].rstrip("/")
    if full == wt or not full.startswith(wt + "/"):
        return None
    return full[len(wt) + 1:]


def writes_a_file(action: dict) -> bool:
    return isinstance(action, dict) and action.get("type") in WRITE_TYPES


def violates(scope: dict, action: dict) -> bool:
    """True when `action` writes a file that the scope does not allow. A call that is not a file write is never a violation."""
    if not writes_a_file(action):
        return False
    rel = _relative(scope, action)
    if rel is None:
        return True
    return bool(gp.scope_violations([rel], scope["files"], own=scope["own"]))
