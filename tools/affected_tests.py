"""W20, Part D: run only the tests a change can affect, on a laptop or in a Kiro session.

Standard library only. It reads what differs from origin/main (the commits, the edits you have not committed, the
files git does not track yet) and asks the same function the CI decider uses (tools.ci_plan.build_plan, with the same
map, tools/ci_map.json). So CI and this command cannot disagree about the same set of changed files.

  python tools/affected_tests.py                 print what is affected (the Python test modules, the Node folders)
  python tools/affected_tests.py --run           also run them
  python tools/affected_tests.py --run --python python3.10 --python python3.13   run on those interpreters too
  python tools/affected_tests.py --base origin/main --json   the plan as the CI decider prints it
  python tools/affected_tests.py --files a b     pretend these are the changed files (no git)

An unknown path, an empty or unreadable diff, and a change to the workflow, the map, the filter or the shards mean
EVERYTHING (the line says "FULL SUITE"). The command cannot tell which tests inside umwayi/, tests/ or adapters/ a
change reaches, so a change there selects the whole Python suite; for the inner loop run one module by hand
(python -m unittest tests.test_rules) and use this command before you push. GitHub CI is the record.

Exit codes: 0 done (and, with --run, every test passed), 2 a test failed or an unexpected error, 64 usage.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools import ci_map, ci_plan  # noqa: E402


def plan_for(paths, data=None, assign=None):
    """The plan for a set of changed paths: the CI decider's own function, event pull_request."""
    data = data or ci_map.load_map()
    assign = assign or json.loads(ci_plan.SHARDS_PATH.read_text(encoding="utf-8"))
    return ci_plan.build_plan(paths, "pull_request", data, assign)


def describe(plan, data):
    mods = ci_plan.test_modules(plan, data)
    lines = []
    if plan["full"]:
        lines.append(f"FULL SUITE: {plan['reason']}")
    else:
        lines.append(f"affected: {plan['reason']}")
    if not plan["python"]["run"]:
        lines.append("python: none")
    elif mods is None:
        lines.append("python: all test modules (python -m unittest discover -s tests -t .)")
    else:
        lines.append(f"python: {len(mods)} test module(s)")
        lines += [f"  {m}" for m in mods]
    dirs = ci_plan.node_dirs(plan)
    lines.append("node: " + (", ".join(f"{d}/ (node --test)" for d in dirs) if dirs else "none"))
    for text in plan["not_run"]:
        lines.append(f"not run here: {text}")
    return "\n".join(lines)


def parse(argv):
    o = {"base": "origin/main", "run": False, "json": False, "files": None, "python": []}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--run":
            o["run"] = True
        elif a == "--json":
            o["json"] = True
        elif a in ("--base", "--python") and i + 1 < len(argv):
            if a == "--base":
                o["base"] = argv[i + 1]
            else:
                o["python"].append(argv[i + 1])
            i += 1
        elif a == "--files" and o["files"] is None:
            o["files"] = []
            while i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                o["files"].append(argv[i + 1])
                i += 1
        else:
            return None
        i += 1
    if o["python"] and not o["run"]:
        return None
    return o


def run_all(plan, data, pythons):
    failed = False
    mods = ci_plan.test_modules(plan, data)
    for py in pythons:
        cmd = [py, "-m", "unittest"] + (["discover", "-s", "tests", "-t", "."] if mods is None else mods)
        if mods == []:
            continue
        print(f"== {py}: {' '.join(cmd[1:4])} ...", flush=True)
        try:
            failed |= subprocess.run(cmd, cwd=str(REPO)).returncode != 0
        except OSError as e:
            print(f"affected_tests: cannot run {py}: {e}", file=sys.stderr)
            failed = True
    for d in ci_plan.node_dirs(plan):
        print(f"== node --test in {d}/", flush=True)
        try:
            failed |= subprocess.run(["node", "--test"], cwd=str(REPO / d)).returncode != 0
        except OSError as e:
            print(f"affected_tests: cannot run node: {e}", file=sys.stderr)
            failed = True
    return 2 if failed else 0


def main(argv):
    o = parse(argv)
    if o is None:
        print("usage: python tools/affected_tests.py [--run] [--python EXE]... "
              "[--base REV] [--json] [--files PATH...]", file=sys.stderr)
        return 64
    try:
        data = ci_map.load_map()
        paths = o["files"] if o["files"] is not None else ci_plan.local_changed_paths(o["base"], REPO)
        plan = plan_for(paths, data)
        print(ci_plan.dumps(plan) if o["json"] else describe(plan, data))
        if o["run"]:
            return run_all(plan, data, o["python"] or [sys.executable])
        return 0
    except Exception as e:  # fail closed
        print(f"affected_tests: unexpected error: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
