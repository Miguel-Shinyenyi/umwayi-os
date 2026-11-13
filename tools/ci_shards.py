"""W20, Part C: split the Python suite into shards by test file, run one shard, and prove that every test ran.

Standard library only.

  python -m tools.ci_shards run --shard N --python-version V --report FILE [--root DIR] [--assignments FILE]
      Runs the tests of shard N (all of its files, or the files the plan selected: the JSON plan in the environment
      variable CI_PLAN). It finds every test the way `python -m unittest discover -s tests -t .` does, and records
      which test ids exist, which belong to this shard, and which really started. It fails (exit 2) when a test
      failed, when a test of the shard did not start (a silently dropped test), when a test file is in no shard,
      or when the shard has nothing to run. The report is written even on failure.
  python -m tools.ci_shards verify --reports DIR [--assignments FILE]
      The final check. Reads the plan (CI_PLAN) and the results of the jobs (PLAN_RESULT, TEST_RESULT, NODE_RESULT)
      from the environment and the shard reports from DIR. Fails (exit 2) when any shard failed, did not run or has
      no report, when a planned job was skipped or cancelled, when the shards disagree about which tests exist, or
      when the tests the shards ran are not all the tests discovery found in the files the plan selected.
  python -m tools.ci_shards balance --times FILE [--shards N] [--root DIR] [--out FILE]
      Writes the assignment: every test file to a shard, balanced by the measured seconds in FILE (a JSON object
      {file: seconds}), longest first onto the lightest shard. The result is deterministic.
  python -m tools.ci_shards check [--assignments FILE] [--root DIR]
      Fails (exit 2) when a test file is in no shard or a listed file is gone.
  python -m tools.ci_shards assign-missing [--assignments FILE] [--root DIR]
      W21. The small repair: each test file under tests/ that is in no shard goes to the shard with the least total
      seconds (a file with no seconds counts as the average of the others, ties go to the lowest shard, files in name
      order), and the entry of a file that is gone is removed. Every other entry is kept as it is. The file is written in
      the layout `balance` writes, the same bytes for the same input, and only when its bytes change. It never
      rebalances; `balance` stays the full rebalance.

Exit codes: 0 done, 2 failed or an unexpected error, 64 usage.
"""
import json
import os
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSIGN_PATH = Path(__file__).resolve().parent / "ci_shards.json"
SCHEMA = 1
STATES = ("success", "skipped", "failure", "cancelled")


class UsageError(Exception):
    pass


def regenerate_hint():
    """The last line of a failed check: the command from tools/generated_files.json that repairs the assignment file."""
    try:
        from tools import generated_files
        return generated_files.regenerate_hint("tools/ci_shards.json")
    except Exception:  # the hint must never hide the real problem
        return "To fix it, run: python -m tools.ci_shards assign-missing"


# ---------------------------------------------------------------- the assignment file

def find_test_files(root):
    """Every test file discovery can reach: tests/**/test*.py below packages (folders with an __init__.py)."""
    root = Path(root)
    out = []
    for p in sorted((root / "tests").rglob("test*.py")):
        rel = p.relative_to(root)
        if all((root / Path(*rel.parts[:i]) / "__init__.py").is_file() for i in range(1, len(rel.parts))):
            out.append(rel.as_posix())
    return out


def balance(seconds, n):
    """{file: shard}, longest first onto the lightest shard; ties go to the lower shard and the earlier name."""
    totals = [0.0] * n
    out = {}
    for name in sorted(seconds, key=lambda f: (-seconds[f], f)):
        k = min(range(n), key=lambda i: (totals[i], i))
        totals[k] += seconds[name]
        out[name] = k + 1
    return out


def assignment_problems(assign, root):
    problems = []
    if not isinstance(assign, dict) or not isinstance(assign.get("shards"), int) or isinstance(assign.get("shards"), bool) \
            or assign["shards"] < 1 or not isinstance(assign.get("files"), dict):
        return ["the assignment file needs 'shards' (a number) and 'files' (an object)"]
    n = assign["shards"]
    used = set()
    for name, v in sorted(assign["files"].items()):
        shard = v.get("shard") if isinstance(v, dict) else None
        sec = v.get("seconds") if isinstance(v, dict) else None
        if not isinstance(shard, int) or isinstance(shard, bool) or not 1 <= shard <= n:
            problems.append(f"{name}: shard must be a whole number from 1 to {n}")
        else:
            used.add(shard)
        if isinstance(sec, bool) or not isinstance(sec, (int, float)) or sec < 0:
            problems.append(f"{name}: seconds must be a number")
    have = set(find_test_files(root))
    for name in sorted(have - set(assign["files"])):
        problems.append(f"{name} is in no shard")
    for name in sorted(set(assign["files"]) - have):
        problems.append(f"{name} is listed in a shard but is not a test file any more")
    for k in range(1, n + 1):
        if k not in used:
            problems.append(f"shard {k} is empty")
    return problems


def load_assignments(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise UsageError(f"cannot read the assignment file {path}: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict) or not isinstance(data.get("shards"), int):
        raise UsageError(f"{path} is not an assignment file")
    return data


# ---------------------------------------------------------------- finding and running tests

def _flatten(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _flatten(t)
        else:
            yield t


def discover_all(root):
    """The ids discovery finds, exactly as `python -m unittest discover -s tests -t .` does."""
    return sorted(t.id() for t in _flatten(unittest.TestLoader().discover(str(Path(root) / "tests"), top_level_dir=str(root))))


def load_by_file(root, files):
    """{file: [test cases]} loading each file by its module name."""
    loader = unittest.TestLoader()
    out = {}
    for f in files:
        mod = f[:-3].replace("/", ".")
        out[f] = list(_flatten(loader.loadTestsFromName(mod)))
    return out


class Recording(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.started = []
        self.file_of = {}
        self.seconds = {}
        self._t0 = 0.0

    def startTest(self, test):
        self.started.append(test.id())
        self._t0 = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        f = self.file_of.get(test.id())
        if f:
            self.seconds[f] = self.seconds.get(f, 0.0) + time.monotonic() - self._t0
        super().stopTest(test)


class Runner(unittest.TextTestRunner):
    resultclass = Recording
    file_of = {}

    def _makeResult(self):
        result = super()._makeResult()
        result.file_of = self.file_of
        return result


def run_shard(root, assign, shard, version, selected=None, stream=None):
    """Run one shard. Returns the report (a dict). Nothing is printed except by the test runner."""
    root = Path(root)
    stream = stream or sys.stderr
    sys.path.insert(0, str(root))
    os.chdir(root)
    files = find_test_files(root)
    by_file = load_by_file(root, files)
    discovered = {f: sorted(t.id() for t in tests) for f, tests in by_file.items()}
    all_ids = discover_all(root)
    mapped = {i for ids in discovered.values() for i in ids}
    unmapped = sorted(set(all_ids) - mapped)  # found by discovery but in no file we loaded: an import failure, say
    listed = assign["files"]
    unassigned = sorted(f for f in files if f not in listed)
    problems = []
    if selected is not None:
        for f in selected:
            if f not in by_file:
                problems.append(f"the plan selects {f}, which is not a test file")
    chosen = [f for f in files if f in listed and listed[f]["shard"] == shard and (selected is None or f in selected)]
    expected = sorted(i for f in chosen for i in discovered[f])
    suite = unittest.TestSuite()
    result_files = {}
    for f in chosen:
        suite.addTests(by_file[f])
        for t in by_file[f]:
            result_files[t.id()] = f
    runner = Runner(stream=stream, verbosity=2)
    runner.file_of = result_files
    t0 = time.monotonic()
    started = []
    counts = {"run": 0, "failures": 0, "errors": 0, "skipped": 0}
    ok_run = True
    seconds = {}
    if chosen:
        result = runner.run(suite)
        started = result.started
        counts = {"run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                  "skipped": len(result.skipped)}
        ok_run = result.wasSuccessful()
        seconds = {k: round(v, 3) for k, v in sorted(result.seconds.items())}
    missing = sorted(set(expected) - set(started))
    if not chosen:
        problems.append("this shard has nothing to run")
    if missing:
        problems.append(f"{len(missing)} test(s) did not run: " + ", ".join(missing[:10]))
    if unassigned:
        problems.append("test file(s) in no shard: " + ", ".join(unassigned))
    if unmapped:
        problems.append("test(s) found by discovery but not in any test file: " + ", ".join(unmapped[:10]))
    ok = ok_run and not problems
    return {"schema": SCHEMA, "python": version, "shard": shard, "of": assign["shards"], "ok": ok, "problems": problems,
            "counts": counts, "expected": expected, "executed": sorted(started), "missing": missing,
            "unassigned_files": unassigned, "unmapped": unmapped, "discovered": discovered,
            "selected": selected, "seconds": seconds, "duration": round(time.monotonic() - t0, 1)}


# ---------------------------------------------------------------- the final check

def _state(results, key):
    return results.get(key, "")


def verify_all(plan, results, reports, assign):
    """Every reason the run cannot be called complete. Empty means every planned job ran and every test ran."""
    problems = []
    for key in ("plan", "test", "node"):
        if _state(results, key) not in STATES:
            problems.append(f"the result of the {key} job is {_state(results, key)!r}, which is not a known result")
    if _state(results, "plan") != "success":
        problems.append(f"the plan job did not succeed ({_state(results, 'plan') or 'no result'})")
        return problems
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA or not isinstance(plan.get("python"), dict):
        return problems + ["the plan is missing or is not a plan"]
    py = plan["python"]
    if plan.get("full") and not py.get("run"):
        problems.append("a full plan must run the python tests")
    if plan.get("full") and not plan.get("node"):
        problems.append("a full plan must run the node tests")
    # node
    if plan.get("node"):
        if _state(results, "node") != "success":
            problems.append(f"the node job was planned but its result is {_state(results, 'node') or 'none'}")
    elif _state(results, "node") != "skipped":
        problems.append(f"the node job was not planned but its result is {_state(results, 'node') or 'none'}")
    # python
    if not py.get("run"):
        if _state(results, "test") != "skipped":
            problems.append(f"no python job was planned but the test job result is {_state(results, 'test') or 'none'}")
        return problems
    if _state(results, "test") != "success":
        problems.append(f"the python test jobs were planned but their result is {_state(results, 'test') or 'none'} "
                        "(a shard failed, did not run or was cancelled)")
    include = plan.get("matrix", {}).get("include", [])
    if not include:
        problems.append("the plan runs python but its matrix is empty")
    files = py.get("files")
    listed = assign["files"]
    n = assign["shards"]
    versions = []
    for cell in include:
        if cell["python-version"] not in versions:
            versions.append(cell["python-version"])
    for v in versions:
        cells = [(c["python-version"], c["shard"]) for c in include if c["python-version"] == v]
        reps = []
        for cell in cells:
            rep = reports.get(cell)
            if rep is None:
                problems.append(f"python {cell[0]} shard {cell[1]}: no report (the shard did not run or did not finish)")
                continue
            reps.append(rep)
            tag = f"python {cell[0]} shard {cell[1]}"
            if rep.get("python") != cell[0] or rep.get("shard") != cell[1] or rep.get("of") != n:
                problems.append(f"{tag}: the report is for another shard or version")
            if rep.get("ok") is not True:
                problems.append(f"{tag}: the shard reports failure ({'; '.join(rep.get('problems', [])) or 'a test failed'})")
            if rep.get("missing"):
                problems.append(f"{tag}: {len(rep['missing'])} test(s) did not run")
            if rep.get("unassigned_files"):
                problems.append(f"{tag}: test file(s) in no shard: {', '.join(rep['unassigned_files'])}")
        if not reps:
            continue
        disc = reps[0].get("discovered", {})
        if any(r.get("discovered") != disc for r in reps):
            problems.append(f"python {v}: the shards disagree about which tests exist")
            continue
        for f in sorted(disc):
            if f not in listed:
                problems.append(f"python {v}: {f} is in no shard")
        scope = sorted(disc) if files is None else list(files)
        for f in scope:
            if f not in disc:
                problems.append(f"python {v}: the plan selects {f} but discovery did not find it")
        expected_ids = {i for f in scope for i in disc.get(f, [])}
        if not expected_ids:
            problems.append(f"python {v}: discovery found no tests to run")
        ran = {i for r in reps for i in r.get("executed", [])}
        dropped = sorted(expected_ids - ran)
        if dropped:
            problems.append(f"python {v}: {len(dropped)} test(s) were not run by any shard: " + ", ".join(dropped[:10]))
        for r in reps:
            want = sorted(i for f in scope if f in listed and listed[f]["shard"] == r.get("shard") for i in disc.get(f, []))
            if r.get("expected") != want:
                problems.append(f"python {v} shard {r.get('shard')}: the shard's own list of tests differs from the assignment")
    return problems


def summary(plan, problems, reports):
    lines = [f"## tests: {'PASS' if not problems else 'FAIL'}", ""]
    if plan.get("reason"):
        lines += [f"Plan: {plan['reason']}", ""]
    by_version = {}
    for (v, _s), rep in sorted(reports.items()):
        by_version.setdefault(v, []).append(rep)
    for v, reps in by_version.items():
        total = sum(len(r.get("executed", [])) for r in reps)
        skipped = sum(r.get("counts", {}).get("skipped", 0) for r in reps)
        lines.append(f"- python {v}: {total} tests in {len(reps)} shard(s), {skipped} skipped by their own decorators")
    lines.append(f"- node tests of ui/ and site/: {'planned' if plan.get('node') else 'not planned'}")
    if plan.get("not_run"):
        lines += ["", "NOT RUN on this pull request (they run on main):", ""] + [f"- {t}" for t in plan["not_run"]]
    if problems:
        lines += ["", "Problems:", ""] + [f"- {p}" for p in problems]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- command line

def parse_opts(argv, allowed):
    opts, i = {}, 0
    while i < len(argv):
        key = argv[i]
        if key not in allowed or i + 1 >= len(argv) or key in opts:
            raise UsageError(f"bad option {key!r}")
        opts[key] = argv[i + 1]
        i += 2
    return opts


def read_plan_env():
    raw = os.environ.get("CI_PLAN")
    if raw is None:
        return None
    try:
        plan = json.loads(raw)
    except ValueError:
        raise UsageError("CI_PLAN is not JSON")
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise UsageError("CI_PLAN is not a plan of schema 1")
    return plan


def cmd_run(argv):
    o = parse_opts(argv, ("--shard", "--python-version", "--report", "--root", "--assignments"))
    for key in ("--shard", "--python-version", "--report"):
        if key not in o:
            raise UsageError(f"{key} is required")
    root = Path(o.get("--root", REPO))
    if not (root / "tests").is_dir():
        raise UsageError(f"{root} has no tests folder")
    assign = load_assignments(o.get("--assignments", ASSIGN_PATH))
    try:
        shard = int(o["--shard"])
    except ValueError:
        raise UsageError("--shard must be a number")
    if not 1 <= shard <= assign["shards"]:
        raise UsageError(f"--shard must be from 1 to {assign['shards']}")
    selected = None
    plan = read_plan_env()
    if plan is not None:
        files = (plan.get("python") or {}).get("files")
        if files is not None:
            if not isinstance(files, list) or not all(isinstance(x, str) for x in files):
                raise UsageError("CI_PLAN python.files must be a list of file names or null")
            selected = files
    report = run_shard(root, assign, shard, o["--python-version"], selected)
    out = Path(o["--report"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    c = report["counts"]
    print(f"ci_shards: python {report['python']} shard {shard}/{assign['shards']}: {c['run']} run, {c['failures']} failed, "
          f"{c['errors']} errors, {c['skipped']} skipped, {len(report['expected'])} expected, {report['duration']} s")
    for p in report["problems"]:
        print(f"ci_shards: {p}")
    return 0 if report["ok"] else 2


def load_reports(directory):
    reports, problems = {}, []
    for p in sorted(Path(directory).rglob("*.json")):
        try:
            rep = json.loads(p.read_text(encoding="utf-8"))
            key = (rep["python"], rep["shard"])
        except (OSError, ValueError, KeyError, TypeError):
            problems.append(f"{p.name}: the report cannot be read")
            continue
        if key in reports:
            problems.append(f"{p.name}: a second report for python {key[0]} shard {key[1]}")
        reports[key] = rep
    return reports, problems


def cmd_verify(argv):
    o = parse_opts(argv, ("--reports", "--assignments", "--summary"))
    if "--reports" not in o:
        raise UsageError("--reports is required")
    assign = load_assignments(o.get("--assignments", ASSIGN_PATH))
    problems = []
    plan = None
    raw = os.environ.get("CI_PLAN")
    try:
        plan = json.loads(raw) if raw else None
    except ValueError:
        plan = None
    results = {"plan": os.environ.get("PLAN_RESULT", ""), "test": os.environ.get("TEST_RESULT", ""),
               "node": os.environ.get("NODE_RESULT", "")}
    reports, rproblems = load_reports(o["--reports"]) if Path(o["--reports"]).is_dir() else ({}, [])
    problems += rproblems
    problems += verify_all(plan, results, reports, assign)
    text = summary(plan if isinstance(plan, dict) else {}, problems, reports)
    print(text)
    target = o.get("--summary") or os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(text)
    return 0 if not problems else 2


def cmd_balance(argv):
    o = parse_opts(argv, ("--times", "--shards", "--root", "--out"))
    if "--times" not in o:
        raise UsageError("--times is required")
    root = Path(o.get("--root", REPO))
    try:
        times = json.loads(Path(o["--times"]).read_text(encoding="utf-8"))
        n = int(o.get("--shards", 3))
    except (OSError, ValueError) as e:
        raise UsageError(f"cannot use the times: {e}")
    if not isinstance(times, dict) or n < 1:
        raise UsageError("--times must be an object {file: seconds} and --shards a positive number")
    files = find_test_files(root)
    seconds = {f: float(times.get(f, 1.0)) for f in files}
    shards = balance(seconds, n)
    data = {"shards": n, "files": {f: {"shard": shards[f], "seconds": round(seconds[f], 1)} for f in files}}
    # balance again from the rounded numbers so the file is a fixed point of this command
    again = balance({f: v["seconds"] for f, v in data["files"].items()}, n)
    data["files"] = {f: {"shard": again[f], "seconds": v["seconds"]} for f, v in data["files"].items()}
    text = json.dumps(data, indent=1, sort_keys=True) + "\n"
    if "--out" in o:
        Path(o["--out"]).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


def assign_missing(assign, root):
    """W21. (new assignment, list of what was done). The new assignment is a copy; `assign` is not changed."""
    n = assign["shards"]
    have = find_test_files(root)
    kept = {f: dict(v) for f, v in assign["files"].items() if f in set(have)}
    done = [f"removed {f}, it is not a test file any more" for f in sorted(set(assign["files"]) - set(kept))]
    known = [v["seconds"] for v in kept.values() if isinstance(v.get("seconds"), (int, float)) and not isinstance(v.get("seconds"), bool)]
    average = round(sum(known) / len(known), 1) if known else 1.0
    totals = [0.0] * n
    for v in kept.values():
        if isinstance(v.get("shard"), int) and not isinstance(v.get("shard"), bool) and 1 <= v["shard"] <= n:
            totals[v["shard"] - 1] += v["seconds"] if isinstance(v.get("seconds"), (int, float)) else average
    for name in sorted(f for f in have if f not in kept):
        k = min(range(n), key=lambda i: (totals[i], i))
        totals[k] += average
        kept[name] = {"shard": k + 1, "seconds": average}
        done.append(f"assigned {name} to shard {k + 1} ({average} s counted)")
    return {"shards": n, "files": kept}, done


def cmd_assign_missing(argv):
    o = parse_opts(argv, ("--assignments", "--root"))
    path = Path(o.get("--assignments", ASSIGN_PATH))
    assign = load_assignments(path)
    if assign["shards"] < 1:
        raise UsageError(f"{path} has no shards")
    if not all(isinstance(v, dict) for v in assign["files"].values()):
        raise UsageError(f"{path} has an entry that is not an object")
    new, done = assign_missing(assign, Path(o.get("--root", REPO)))
    text = json.dumps(new, indent=1, sort_keys=True) + "\n"
    if path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    for line in done:
        print(f"ci_shards: {line}")
    if not done:
        print("ci_shards: nothing to assign")
    return 0


def cmd_check(argv):
    o = parse_opts(argv, ("--assignments", "--root"))
    assign = load_assignments(o.get("--assignments", ASSIGN_PATH))
    problems = assignment_problems(assign, Path(o.get("--root", REPO)))
    for p in problems:
        print(f"ci_shards: {p}", file=sys.stderr)
    if problems:
        print(f"ci_shards: {regenerate_hint()}", file=sys.stderr)
    if not problems:
        print("ci_shards: every test file is in exactly one shard")
    return 2 if problems else 0


COMMANDS = {"run": cmd_run, "verify": cmd_verify, "balance": cmd_balance, "check": cmd_check,
            "assign-missing": cmd_assign_missing}


def main(argv):
    try:
        if not argv or argv[0] not in COMMANDS:
            raise UsageError("usage: python -m tools.ci_shards run | verify | balance | check | assign-missing")
        return COMMANDS[argv[0]](argv[1:])
    except UsageError as e:
        print(f"ci_shards: {e}", file=sys.stderr)
        return 64
    except Exception as e:  # fail closed
        print(f"ci_shards: unexpected error: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
