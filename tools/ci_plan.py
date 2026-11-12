"""W20, Part B: the CI decider. It reads the changed paths of a pull request and prints which jobs must run.

Standard library only. Rules, in this order:
  1. Anything that is not a pull request (a push to main, a manual run) runs everything.
  2. An unreadable diff, an empty diff, a path that is not a plain relative path, a path that matches no route in
     tools/ci_map.json, and any change under .github/ or tools/ (the workflow, this script, the map, the shards)
     run everything.
  3. Otherwise each changed path follows the longest route that matches it: the whole Python suite, only the Python
     test files that read that path (the map), or none; and the Node job, always, never, or only if a Node test reads it.
     The answers of all paths are added together.
  4. The Python versions are 3.10 to 3.13 unless the Python part is a selection of files; then 3.10 and 3.13 only.

Usage: python -m tools.ci_plan --event EVENT [--base REV] [--head REV] [--github-output FILE]
Prints the plan as one line of JSON. Exit codes: 0 plan printed, 2 unexpected error (nothing is skipped by a crash,
the always-on final job fails), 64 usage.

The plan holds no changed path: only counts, area names and test file names from the map reach the outputs.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from tools import ci_map

REPO = Path(__file__).resolve().parent.parent
SHARDS_PATH = Path(__file__).resolve().parent / "ci_shards.json"
ALL_VERSIONS = ["3.10", "3.11", "3.12", "3.13"]
REDUCED_VERSIONS = ["3.10", "3.13"]
SCHEMA = 1
REV = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._/~^@{}-]{0,200}$")


def normalize(path):
    """The path if it is a plain relative path with no '.', '..' or empty parts, else None."""
    if not isinstance(path, str) or not path or "\0" in path or "\\" in path or path.startswith("/"):
        return None
    if any(part in ("", ".", "..") for part in path.split("/")):
        return None
    return path


def route_for(path, data):
    best = None
    for r in data["routes"]:
        m = r["match"]
        hit = path.startswith(m) if m.endswith("/") else path == m
        if hit and (best is None or len(m) > len(best["match"])):
            best = r
    return best if best is not None else data["default"]


def parse_name_status(raw):
    """The paths in the output of `git diff --name-status -z -M`. A rename or copy gives both sides."""
    parts = raw.decode("utf-8", "surrogateescape").split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    out, i = [], 0
    while i < len(parts):
        status = parts[i]
        if not status or status[0] not in "ACDMRTUXB":
            raise ValueError(f"unknown status {status!r}")
        need = 2 if status[0] in "RC" else 1
        names = parts[i + 1:i + 1 + need]
        if len(names) != need or not all(names):
            raise ValueError("a status without its path")
        out.extend(names)
        i += 1 + need
    return out


def changed_paths(base, head, cwd):
    """The changed paths between two revisions, or None if they cannot be read (which runs everything)."""
    try:
        for rev in (base, head) if head else (base,):
            if not isinstance(rev, str) or not REV.match(rev):
                return None
            r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", rev + "^{commit}"], cwd=str(cwd),
                               capture_output=True, timeout=60)
            if r.returncode != 0:
                return None
        cmd = ["git", "diff", "--name-status", "-z", "-M", "--no-ext-diff", base] + ([head] if head else []) + ["--"]
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, timeout=120)
        if r.returncode != 0:
            return None
        return parse_name_status(r.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def local_changed_paths(base, cwd):
    """For a laptop or a session: everything that differs from `base` (say origin/main): the commits since the merge
    base, the staged and unstaged edits, and the files git does not track yet. None if any part cannot be read."""
    try:
        if not isinstance(base, str) or not REV.match(base):
            return None
        r = subprocess.run(["git", "merge-base", base, "HEAD"], cwd=str(cwd), capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not r.stdout.strip():
            return None
        fork = r.stdout.strip()
        committed = changed_paths(fork, "HEAD", cwd)
        working = changed_paths("HEAD", None, cwd)
        u = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=str(cwd), capture_output=True,
                           timeout=60)
        if committed is None or working is None or u.returncode != 0:
            return None
        new = [x for x in u.stdout.decode("utf-8", "surrogateescape").split("\0") if x]
        return committed + working + new
    except (OSError, subprocess.SubprocessError):
        return None


def test_modules(plan, data):
    """The dotted names of the Python test modules a plan runs, or None for all of them (plain discovery)."""
    files = plan["python"]["files"]
    if not plan["python"]["run"]:
        return []
    return None if files is None else [f[:-3].replace("/", ".") for f in files]


def node_dirs(plan):
    return ["ui", "site"] if plan["node"] else []


def _shards_for(files, assign):
    n = assign["shards"]
    if files is None:
        return list(range(1, n + 1))
    return sorted({assign["files"][f]["shard"] for f in files if f in assign["files"]})


def build_plan(paths, event, data, assign):
    """The plan. `paths` is the list of changed paths, or None when the diff could not be read."""
    full, reasons = False, []
    py_all, py_files, node = False, set(), False
    if event != "pull_request":
        full = True
        reasons.append(f"event {event}: everything runs")
    elif paths is None:
        full = True
        reasons.append("the diff could not be read: everything runs")
    elif not paths:
        full = True
        reasons.append("the diff is empty: everything runs")
    else:
        areas = set()
        for raw in sorted(set(paths if isinstance(paths, list) else [])):
            path = normalize(raw)
            if path is None:
                full = True
                reasons.append("a changed path is not a plain relative path: everything runs")
                continue
            route = route_for(path, data)
            if route is data["default"]:
                reasons.append("a changed path matches no route: everything runs")
            if route.get("full"):
                full = True
                if route is not data["default"]:
                    reasons.append("the workflow, the filter or its data changed: everything runs")
            areas.add(route.get("match", "other"))
            if route["python"] == "all":
                py_all = True
            elif route["python"] == "map":
                py_files |= {f for f, toks in data["python"].items() if any(ci_map.reads_match(t, path) for t in toks)}
            if route["node"] is True:
                node = True
            elif route["node"] == "map":
                node = node or any(ci_map.reads_match(t, path) for toks in data["node"].values() for t in toks)
        if not full:
            reasons.append("changed areas: " + ", ".join(sorted(areas)))
    if full:
        py_all, node = True, True
    files = None if py_all else sorted(py_files)
    run_python = py_all or bool(py_files)
    versions = (ALL_VERSIONS if py_all else REDUCED_VERSIONS) if run_python else []
    shards = _shards_for(files, assign) if run_python else []
    n = assign["shards"]
    matrix = [{"python-version": v, "shard": s, "of": n} for v in versions for s in shards]
    not_run = []
    if not run_python:
        not_run.append("python tests: not run on this pull request, they run on main")
    else:
        if versions != ALL_VERSIONS:
            skipped = [v for v in ALL_VERSIONS if v not in versions]
            not_run.append("python " + " and ".join(skipped) + ": not run on this pull request, they run on main")
        if files is not None:
            total = len(data["python"])
            not_run.append(f"python test files: {len(files)} of {total} run, {total - len(files)} not run on this pull "
                           "request, they run on main")
    if not node:
        not_run.append("node tests of ui/ and site/: not run on this pull request, they run on main")
    ev = event if re.fullmatch(r"[a-z_]{1,40}", event or "") else "unknown"
    return {"schema": SCHEMA, "event": ev, "full": full, "reason": "; ".join(dict.fromkeys(reasons)),
            "python": {"run": run_python, "files": files, "versions": versions, "shards": shards, "of": n},
            "node": node, "matrix": {"include": matrix}, "not_run": not_run}


def dumps(plan):
    return json.dumps(plan, sort_keys=True, separators=(",", ":"))


def _usage():
    print("usage: python -m tools.ci_plan --event EVENT [--base REV] [--head REV] [--github-output FILE]", file=sys.stderr)
    return 64


def parse_args(argv):
    opts, i = {}, 0
    while i < len(argv):
        key = argv[i]
        if key not in ("--event", "--base", "--head", "--github-output") or i + 1 >= len(argv) or key in opts:
            return None
        opts[key] = argv[i + 1]
        i += 2
    return opts if "--event" in opts else None


def main(argv):
    opts = parse_args(argv)
    if opts is None:
        return _usage()
    try:
        data = ci_map.load_map()
        assign = json.loads(SHARDS_PATH.read_text(encoding="utf-8"))
        event = opts["--event"]
        paths = None
        if event == "pull_request" and "--base" in opts:
            paths = changed_paths(opts["--base"], opts.get("--head", "HEAD"), REPO)
        plan = build_plan(paths, event, data, assign)
        line = dumps(plan)
        print(line)
        print(f"ci_plan: {plan['reason']}", file=sys.stderr)
        for text in plan["not_run"]:
            print(f"ci_plan: NOT RUN: {text}", file=sys.stderr)
        if "--github-output" in opts:
            with open(opts["--github-output"], "a", encoding="utf-8") as f:
                f.write(f"plan={line}\n")
                f.write(f"matrix={json.dumps(plan['matrix'], sort_keys=True, separators=(',', ':'))}\n")
                f.write(f"python={'true' if plan['python']['run'] else 'false'}\n")
                f.write(f"node={'true' if plan['node'] else 'false'}\n")
        return 0
    except Exception as e:  # fail closed: no plan, so the final job fails and nothing is skipped by accident
        print(f"ci_plan: unexpected error: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
