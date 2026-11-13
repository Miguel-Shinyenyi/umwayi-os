"""The command line of the mutation pass (W6.10). See tests/serve/mutation.py for how a fault is run and tests/serve/faults.py for the
catalogue. This module copies and hashes the whole tree, which is why it is separate from the library: the tests of the library
(tests/serve/test_mutation.py) import only the library.

    python -m tests.serve.mutation                 run every fault of tests/serve/faults.py and print the report
    python -m tests.serve.mutation --list          list the faults
    python -m tests.serve.mutation --only R5 G3    run these faults only
    python -m tests.serve.mutation --timeout 180   seconds one fault may take (default 240)
    python -m tests.serve.mutation --report FILE   also write the report to FILE
    python -m tests.serve.mutation --strict        exit 1 when a survivor is not marked equivalent

Before the first fault every test that is used is run once on the unchanged copy and must pass. At the end the real tree is
compared with its hashes from the start; any difference is an error (exit 2).

Exit codes: 0 done (a survivor is a result, not an error, unless --strict), 1 --strict and a survivor that is not marked
`equivalent`, 2 an unexpected error or a changed real tree, 64 usage.
"""

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

from tests.serve import mutation as lib

REPO = lib.REPO


def snapshot_root(root: Path) -> dict:
    """SHA-256 of every file of the checkout (without .git, node_modules and caches)."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in lib.SKIP]
        for n in filenames:
            p = Path(dirpath) / n
            try:
                out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                out[p.relative_to(root).as_posix()] = "unreadable"
    return out


def copy_all(src: Path, dst: Path) -> None:
    """The whole tree, without .git, node_modules and caches."""
    dst.mkdir(parents=True)
    for entry in sorted(src.iterdir()):
        if entry.name not in lib.SKIP:
            lib.copy_entry(entry, dst / entry.name)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.serve.mutation")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--timeout", type=float, default=lib.DEFAULT_TIMEOUT)
    ap.add_argument("--prop-n", type=int, default=400, help="cases per property in the property tests (UMWAYI_PROP_N)")
    ap.add_argument("--report", default=None)
    ap.add_argument("--strict", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 64 if e.code else 0
    from tests.serve.faults import FAULTS
    faults = [f for f in FAULTS if args.only is None or f.id in args.only]
    if args.only and len(faults) != len(set(args.only)):
        print("unknown fault id in --only", file=sys.stderr)
        return 64
    if args.list:
        for f in faults:
            print(f"{f.id}\t{f.file}\t{f.name}")
        return 0
    before = snapshot_root(REPO)
    work = Path(tempfile.mkdtemp(prefix="umwayi-mutation-"))
    try:
        copy = work / "tree"
        if REPO in copy.resolve().parents or copy.resolve() == REPO:
            print("the copy must not be inside the real tree", file=sys.stderr)
            return 2
        copy_all(REPO, copy)
        # a test that fails on the unchanged copy would "catch" every fault, so each test used must pass first
        env = lib.test_env(copy, args.prop_n)
        for test in sorted({x for f in faults for x in f.tests}):
            code, tail = lib.run_group(lib.command_for(test), copy, env, args.timeout * 4)
            print(f"baseline {test}: {'passes' if code == 0 else 'FAILS'}", flush=True)
            if code != 0:
                print(tail, file=sys.stderr)
                print("ERROR: a test fails on the unchanged copy, so the pass would mean nothing", file=sys.stderr)
                return 2
        outcomes = []
        for f in faults:
            o = lib.run_fault(f, copy, args.timeout, args.prop_n)
            outcomes.append(o)
            print(f"{f.id:5} {o.status:9} {o.seconds:6.1f}s  {f.name}  [{o.detail[:80]}]", flush=True)
        text = lib.report(outcomes)
        print("\n" + text)
        if args.report:
            Path(args.report).write_text(text + "\n", encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if snapshot_root(REPO) != before:
        print("ERROR: the real tree changed during the mutation pass", file=sys.stderr)
        return 2
    if args.strict and any(o.status in ("survived", "invalid", "notfound") and o.fault.expect != "equivalent" for o in outcomes):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
