"""The mutation pass for `umwayi serve` (W6.10, W6.R16.10). A test tool: it lives in tests/ and is not shipped.

    python -m tests.serve.mutation                 run every fault of tests/serve/faults.py and print the report
    python -m tests.serve.mutation --list          list the faults
    python -m tests.serve.mutation --only R5 G3    run these faults only
    python -m tests.serve.mutation --timeout 180   seconds one fault may take (default 240)
    python -m tests.serve.mutation --report FILE   also write the report to FILE

How it works. The source tree is copied once to a throwaway folder in the system's temporary place (never inside the real tree).
For each fault ONE file of the copy is changed (exact text to exact text, found exactly once), the copy is checked to still compile,
and only the tests named for the fault are run in a child process against the copy, cheapest first, stopping at the first that fails.
The child gets its own process group; when the time limit passes, the whole group is killed and the fault counts as CAUGHT (a
hang is a failure of the tests to finish, and a changed server that hangs is not a server that works). A fault that does not
compile is INVALID and counted on its own, not as caught. After each fault the file of the copy is put back from the bytes read
before. At the end the real tree is compared with its hashes from the start; any difference is an error (exit 2).

Before the first fault every test that is used is run once on the unchanged copy and must pass.

Exit codes: 0 done (a survivor is a result, not an error, unless --strict), 1 --strict and a survivor that is not marked
`equivalent`, 2 an unexpected error or a changed real tree, 64 usage.
"""

import argparse
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKIP = {".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
DEFAULT_TIMEOUT = 240.0


@dataclass(frozen=True)
class Outcome:
    fault: object
    status: str  # caught, survived, invalid, notfound
    detail: str  # the test that caught it, or why not
    seconds: float


def path_of(rel: str) -> Path:
    """A file of the real tree, by its path from the root (used by the tests of the tool)."""
    return REPO / rel


def tree_hashes(root: Path, only=None) -> dict:
    """SHA-256 of every file under the places a fault can touch (the four source files and everything else the tests read)."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for n in filenames:
            p = Path(dirpath) / n
            rel = p.relative_to(root).as_posix()
            if only is not None and rel not in only:
                continue
            try:
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                out[rel] = "unreadable"
    return out


def copy_entry(src: Path, dst: Path) -> None:
    """Copy a file, or a folder without .git, node_modules and caches."""
    src = Path(src)
    if src.is_dir():
        shutil.copytree(src, dst, ignore=lambda _d, names: [n for n in names if n in SKIP], symlinks=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def apply_edits(text: str, edits) -> tuple:
    """(the changed text, "") or (None, why). Each old text must be found exactly once."""
    for old, new in edits:
        n = text.count(old)
        if n != 1:
            return None, f"the text to change was found {n} times, not once"
        text = text.replace(old, new)
    return text, ""


def compiles(path: Path, work: Path) -> bool:
    """A Python file must still compile; a JavaScript file is checked by Node (--check) when Node is there."""
    if path.suffix == ".py":
        r = subprocess.run([sys.executable, "-c", "import sys; compile(open(sys.argv[1], encoding='utf-8').read(), sys.argv[1], 'exec')",
                            str(path)], capture_output=True, timeout=60)
        return r.returncode == 0
    node = shutil.which("node")
    if path.suffix == ".js" and node:
        r = subprocess.run([node, "--check", "--input-type=module", "-"], input=path.read_bytes(), capture_output=True, timeout=60)
        return r.returncode == 0
    return True


def command_for(test: str, python=sys.executable) -> list:
    if test.startswith("node:"):
        return [shutil.which("node") or "node", "--test", test[5:]]
    return [python, "-m", "unittest", "-f", test]


def run_group(cmd, cwd, env, timeout) -> tuple:
    """(exit code or None on a time out, the tail of the output). The child and everything it started are killed on a time out."""
    proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out.decode("utf-8", "replace")[-600:]
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            out, _ = proc.communicate(timeout=10)
        except Exception:
            out = b""
        return None, out.decode("utf-8", "replace")[-300:]


def test_env(copy: Path, prop_n: int) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(copy)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["UMWAYI_PROP_N"] = str(prop_n)
    env["UMWAYI_FUZZ_N"] = "400"
    return env


def run_fault(fault, copy: Path, timeout: float, prop_n: int = 400, python=sys.executable) -> Outcome:
    """One fault against the copy. The file of the copy is always put back."""
    t0 = time.monotonic()
    path = copy / fault.file
    original = path.read_bytes()
    try:
        changed, why = apply_edits(original.decode("utf-8"), fault.edits)
        if changed is None:
            return Outcome(fault, "notfound", why, time.monotonic() - t0)
        path.write_bytes(changed.encode("utf-8"))
        if not compiles(path, copy):
            return Outcome(fault, "invalid", "the changed file does not compile", time.monotonic() - t0)
        env = test_env(copy, prop_n)
        for test in fault.tests:
            code, tail = run_group(command_for(test, python), copy, env, timeout)
            if code is None:
                return Outcome(fault, "caught", f"{test} (did not finish in {int(timeout)} s: a hang counts as caught)", time.monotonic() - t0)
            if code != 0:
                return Outcome(fault, "caught", test, time.monotonic() - t0)
        return Outcome(fault, "survived", "all of " + ", ".join(fault.tests) + " passed", time.monotonic() - t0)
    finally:
        path.write_bytes(original)


def report(outcomes) -> str:
    lines = ["| id | fault | file | result | by |", "| --- | --- | --- | --- | --- |"]
    for o in outcomes:
        lines.append(f"| {o.fault.id} | {o.fault.name} | {o.fault.file} | {o.status} | {o.detail} |")
    n = len(outcomes)
    caught = sum(o.status == "caught" for o in outcomes)
    survived = [o for o in outcomes if o.status == "survived"]
    invalid = sum(o.status in ("invalid", "notfound") for o in outcomes)
    lines.append("")
    lines.append(f"planted {n}, caught {caught}, survived {len(survived)}, invalid {invalid}")
    for o in survived:
        reason = o.fault.why or "no reason recorded: a gap in the tests, to be closed or shown equivalent"
        lines.append(f"survivor {o.fault.id} ({o.fault.name}): {reason}")
    return "\n".join(lines)


if __name__ == "__main__":
    # the command line is in its own module: it is the one part that copies and hashes the whole tree, and the map of the
    # tests (tools/ci_map.py) would then say that every test that imports this library reads the whole tree
    import importlib

    sys.exit(importlib.import_module("tests.serve.mutation_cli").main())
