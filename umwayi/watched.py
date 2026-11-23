"""W78 build step 3 (W41 C1): the watched files, read before a helper starts and again after it ends.

A helper that changes one of these files has changed what decides for it: the rules, the agents, the budget, the guidance, the
mode, the steering or the tools. Nothing here undoes a change or stops a helper while it runs; it turns a silent change into a
visible one at the end of the run, and the caller stops the task (W78 Q5). A change that is made and undone inside one run is
not seen, and neither is a change to a file that is not on the list.

The list is fixed in this file. A name in a report is always one of its entries, never a path or a word a helper wrote.
Standard library only. Reads files; writes nothing, starts nothing, follows no link.
"""

import hashlib
import os
import stat

# Files, or a folder (the steering entry may be either): relative to the umwayi root.
FILES = (".umwayi/enforcement.yaml", "guidance.yaml", "units.yaml", "agents.yaml", "rules.yaml", "autonomy.yaml",
         ".kiro/steering/umwayi")
# Folders: every regular file below, by name and content.
TREES = ("tools",)
NAMES = FILES + TREES

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TREE_FILES = 2000

ABSENT = "absent"
UNREADABLE = "unreadable"


def _file_digest(path) -> str:
    """The SHA-256 of a regular file's bytes; `absent`, a link (by its target text), another kind of file, or `unreadable`."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return ABSENT
    except OSError:
        return UNREADABLE
    if stat.S_ISLNK(st.st_mode):
        try:
            return "link:" + hashlib.sha256(os.readlink(path).encode("utf-8", "replace")).hexdigest()
        except OSError:
            return UNREADABLE
    if not stat.S_ISREG(st.st_mode):
        return "kind:" + stat.filemode(st.st_mode)[0]
    if st.st_size > MAX_FILE_BYTES:
        return f"big:{st.st_size}"
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return UNREADABLE
    return h.hexdigest()


def _tree_digest(path) -> str:
    """One digest for a folder: each file's name and content, in name order. Links are not followed."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return ABSENT
    except OSError:
        return UNREADABLE
    if not stat.S_ISDIR(st.st_mode):
        return _file_digest(path)
    h = hashlib.sha256()
    count = 0
    try:
        for folder, dirs, files in os.walk(path, followlinks=False):
            dirs.sort()
            for name in sorted(files):
                count += 1
                if count > MAX_TREE_FILES:
                    return f"many:{MAX_TREE_FILES}"
                full = os.path.join(folder, name)
                h.update(os.path.relpath(full, path).encode("utf-8", "replace") + b"\0")
                h.update(_file_digest(full).encode("ascii") + b"\0")
    except OSError:
        return UNREADABLE
    return h.hexdigest()


def snapshot(root) -> dict:
    """{name: digest} for every entry of NAMES. Never raises: a file that cannot be read has the digest `unreadable`."""
    out = {}
    for name in NAMES:
        path = os.path.join(os.fspath(root), *name.split("/"))
        out[name] = _tree_digest(path) if name in TREES or name == ".kiro/steering/umwayi" else _file_digest(path)
    return out


def changed(before: dict, after: dict) -> list:
    """The names, in the order of NAMES, whose digest differs. A name missing on one side counts as changed."""
    return [n for n in NAMES if before.get(n) != after.get(n)]
