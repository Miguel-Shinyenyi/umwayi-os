"""W21: the list of generated files (tools/generated_files.json), its strict reader, and the one helper that tells a
person the exact command that regenerates a stale file.

Standard library only. The list says, for each file a command writes: its path, the commands that write it
(`regenerate`), the commands that prove it is current (`verify`), and optionally `writes` (other paths the regenerate
commands may write, such as the part files the docs build numbers) and `block` (the file is only generated between two
marker lines, so a merge keeps the rest of it).

A command is {"argv": [...], "cwd": "ui"}. It is run without a shell. `cwd` is a plain relative folder and may be left out.
The first word `python` stands for the Python that runs the tool.

The reader is strict. A key it does not know, a repeated path, a path that is not a plain relative path, a command that
starts a shell, or a wrong type is a ListError, and `python -m tools.merge_main` turns that into exit 64.

Used by: tools/merge_main.py (to merge), and tests/test_progress_page.py, tests/test_ci_map.py, tests/test_ci_shards.py and
tests/test_docs.py (to end a stale message with the command, through `stale_message`).
"""
import json
import shlex
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIST_PATH = Path(__file__).resolve().parent / "generated_files.json"
LIST_REL = "tools/generated_files.json"
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh", "cmd", "cmd.exe", "powershell", "pwsh"})
TOP_KEYS = frozenset({"version", "files"})
ENTRY_KEYS = frozenset({"path", "regenerate", "verify", "writes", "block"})
COMMAND_KEYS = frozenset({"argv", "cwd"})
BLOCK_KEYS = frozenset({"begin", "end"})


class ListError(Exception):
    """The list is wrong. The message names the entry."""


def plain_relative(path):
    """True for a path like `docs/x.md`: a non empty text with no leading slash, no backslash, no colon, no NUL, and no
    empty, `.` or `..` part."""
    if not isinstance(path, str) or not path or "\\" in path or ":" in path or "\0" in path or path.startswith("/"):
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def _command(value, where):
    if not isinstance(value, dict) or set(value) - COMMAND_KEYS or "argv" not in value:
        raise ListError(f"{where}: a command is an object with 'argv' and optionally 'cwd'")
    argv = value["argv"]
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a and "\0" not in a for a in argv):
        raise ListError(f"{where}: 'argv' must be a list of non empty words")
    if Path(argv[0]).name.lower() in SHELLS or argv[0].startswith("-"):
        raise ListError(f"{where}: a command may not start a shell")
    cwd = value.get("cwd")
    if "cwd" in value and not plain_relative(cwd):
        raise ListError(f"{where}: 'cwd' must be a plain relative folder")
    return {"argv": list(argv), "cwd": cwd}


def _commands(value, where):
    if not isinstance(value, list) or not value:
        raise ListError(f"{where} must be a non empty list of commands")
    return [_command(c, f"{where}[{i}]") for i, c in enumerate(value)]


def parse(data):
    """The entries of a list that was read from json, in file order. Raises ListError."""
    if not isinstance(data, dict) or set(data) - TOP_KEYS or data.get("version") != 1 or not isinstance(data.get("files"), list):
        raise ListError("the list is an object with 'version' 1 and 'files' (a list), and nothing else")
    out, seen = [], set()
    for i, e in enumerate(data["files"]):
        if not isinstance(e, dict):
            raise ListError(f"files[{i}] is not an object")
        unknown = sorted(set(e) - ENTRY_KEYS)
        if unknown:
            raise ListError(f"files[{i}] has a key the reader does not know: {unknown[0]}")
        for need in ("path", "regenerate", "verify"):
            if need not in e:
                raise ListError(f"files[{i}] has no '{need}'")
        path = e["path"]
        if not plain_relative(path):
            raise ListError(f"files[{i}]: '{path}' is not a plain relative path")
        if path in seen:
            raise ListError(f"files[{i}]: '{path}' is listed twice")
        seen.add(path)
        writes = e.get("writes", [])
        if not isinstance(writes, list) or not all(plain_relative(w) for w in writes) or len(set(writes)) != len(writes):
            raise ListError(f"{path}: 'writes' must be a list of different plain relative paths")
        block = e.get("block")
        if "block" in e and (not isinstance(block, dict) or set(block) != BLOCK_KEYS
                             or not all(isinstance(v, str) and v and "\n" not in v for v in block.values())):
            raise ListError(f"{path}: 'block' must be an object with 'begin' and 'end' (one line each)")
        out.append({"path": path, "regenerate": _commands(e["regenerate"], f"{path} regenerate"),
                    "verify": _commands(e["verify"], f"{path} verify"), "writes": list(writes), "block": block})
    return out


def load(path=LIST_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ListError(f"cannot read {path}: {e}")
    return parse(data)


def entry_for(path, entries=None):
    entries = load() if entries is None else entries
    for e in entries:
        if e["path"] == path:
            return e
    raise ListError(f"{path} is not in {LIST_REL}")


def command_text(entry):
    """The regenerate commands of an entry as one line a person can paste: commands run in the same folder are
    joined with && and a folder change is written as `(cd ui && ...)`."""
    groups = []
    for c in entry["regenerate"]:
        if groups and groups[-1][0] == c["cwd"]:
            groups[-1][1].append(c["argv"])
        else:
            groups.append((c["cwd"], [c["argv"]]))
    parts = []
    for cwd, argvs in groups:
        line = " && ".join(shlex.join(a) for a in argvs)
        parts.append(f"(cd {cwd} && {line})" if cwd else line)
    return " && ".join(parts)


def regenerate_hint(path, entries=None):
    """`To fix it, run: <command>` for a generated file, from the list. Raises ListError for a path that is not listed."""
    return f"To fix it, run: {command_text(entry_for(path, entries))}"


def stale_message(path, problems, entries=None):
    """What a failing test shows: the problems, one per line, and the exact regenerate command as the last line."""
    if isinstance(problems, str):
        problems = [problems]
    return "\n".join([*problems, regenerate_hint(path, entries)])
