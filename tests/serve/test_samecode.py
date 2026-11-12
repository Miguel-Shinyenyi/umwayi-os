"""Same code, never a second copy (W6.R1.1, W6.R16.3): spies, a differential test against the command line, and a code guard."""

import ast
import io
import json
import re
import shutil
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from tests.serve.support import (DATE, REPO, SENTINEL, TOKEN, InProc, RootCase, logbook_entries, make_logbook, make_root,
                                 write_agents)
from umwayi import agents, budget, kill, logbook, rules, taskqueue, view
from umwayi.cli import main

SERVE_EXTRA_SOURCES = {"umwayi serve", "umwayi check", "umwayi rules"}


def run_cli(root, *argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("umwayi.cli._today", return_value=DATE), redirect_stderr(err):
        code = main(["--root", str(root), *argv], out=out)
    return code, out.getvalue()


def plain_entries(root):
    """The command's own entries: without the rules check of the web door and the request entry."""
    return [(e.date, e.source, e.added, e.checked, e.not_done) for e in logbook_entries(root)
            if e.source not in SERVE_EXTRA_SOURCES]


# ----------------------------------------------------------------------------------------------- the spies

ROUTES = [
    # id, method, path, body, class, the core calls expected (name, positional arguments after root)
    ("status", "GET", "/v1/status", None, "read", [("kill.state", None)]),
    ("snapshot", "GET", "/v1/snapshot", None, "read", [("logbook.read_checked_chain", ()), ("view.gather", None)]),
    ("queue.list", "GET", "/v1/queue?status=open&kind=task", None, "read", [("taskqueue.list_rows", None)]),
    ("logbook.verify", "GET", "/v1/logbook", None, "read", [("logbook.verify", (None,))]),
    ("budget.status", "GET", "/v1/budget", None, "read", [("budget.status", (DATE, DATE))]),
    ("agents.list", "GET", "/v1/agents", None, "read", [("agents.load", (None,))]),
    ("agents.check", "POST", "/v1/agents/helper/check", {}, "run", [("agents.check_agent", ("helper", None, None))]),
    ("queue.add", "POST", "/v1/queue", {"kind": "task", "title": "T", "recommendation": "R"}, "write",
     [("taskqueue.add", ("task", "T", "R", DATE))]),
    ("queue.answer", "POST", "/v1/queue/Q-0001/answer", {"answer": "A"}, "write",
     [("taskqueue.answer", ("Q-0001", "A", DATE))]),
    ("queue.close", "POST", "/v1/queue/Q-0001/close", {}, "write", [("taskqueue.close", ("Q-0001", DATE))]),
    ("kill.on", "POST", "/v1/kill/on", {}, "write", [("kill.turn_on", (DATE, None))]),
]


class Spy:
    """Wraps functions of the core and records every call, in order, in one list."""

    def __init__(self, names):
        self.calls = []
        self.patches = []
        for dotted in names:
            mod, _, fn = dotted.partition(".")
            module = {"kill": kill, "rules": rules, "logbook": logbook, "taskqueue": taskqueue, "view": view,
                      "budget": budget, "agents": agents}[mod]
            real = getattr(module, fn)
            self.patches.append(mock.patch.object(module, fn, side_effect=self._wrap(dotted, real)))

    def _wrap(self, dotted, real):
        def inner(*a, **kw):
            if dotted == "logbook.append":
                if a[1].source != "umwayi serve":
                    return real(*a, **kw)
                self.calls.append(("logbook.append(request)", a, kw))
                return real(*a, **kw)
            self.calls.append((dotted, a, kw))
            return real(*a, **kw)
        return inner

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()

    def names(self):
        return [c[0] for c in self.calls]


CORE = ["kill.state", "rules.check_and_log", "logbook.append", "taskqueue.list_rows", "taskqueue.add", "taskqueue.add_once",
        "taskqueue.answer", "taskqueue.close", "kill.turn_on", "logbook.read_checked_chain", "view.gather",
        "logbook.verify", "budget.status", "agents.load", "agents.check_agent"]


class SpyTests(RootCase):
    def setUp(self):
        super().setUp()
        make_logbook(self.root)
        write_agents(self.root, self.tmp / "work")
        taskqueue.add(self.root, "task", "Seed task", "", DATE)
        self.web = InProc(self.root)

    def test_each_route_calls_the_named_core_functions_once_in_the_order_of_w6_r7(self):
        for rid, method, path, body, cls, expected in ROUTES:
            with self.subTest(route=rid), Spy(CORE) as spy:
                r = self.web.request(method, path, body)
                self.assertIn(r.status, (200, 400, 409, 500), (rid, r))
                names = spy.names()
                for name, _args in expected:
                    self.assertIn(name, names)
                    if name != "kill.state":
                        self.assertEqual(names.count(name), 1, (rid, names))
                self.assertIn("logbook.append(request)", names)
                self.assertEqual(names.count("logbook.append(request)"), 1)
                self.assertEqual(names[-1], "logbook.append(request)")
                self.assertIn("kill.state", names)
                if rid == "kill.on":
                    self.assertNotIn("rules.check_and_log", names)
                    self.assertEqual(names.count("kill.turn_on"), 1)
                    continue
                self.assertEqual(names.count("rules.check_and_log"), 1)
                self.assertLess(names.index("kill.state"), names.index("rules.check_and_log"))
                for name, _a in expected:
                    if name != "kill.state":
                        self.assertLess(names.index("rules.check_and_log"), names.index(name), (rid, names))
                        self.assertLess(names.index(name), names.index("logbook.append(request)"))

    def test_the_arguments_of_the_core_calls(self):
        for rid, method, path, body, cls, expected in ROUTES:
            with self.subTest(route=rid), Spy(CORE) as spy:
                self.web.request(method, path, body)
                for name, args in expected:
                    if args is None:
                        continue
                    call = next(c for c in spy.calls if c[0] == name)
                    self.assertEqual(tuple(call[1][1:]), args, (rid, name))
                    self.assertEqual(call[1][0], self.root)

    def test_the_rules_check_gets_the_action_the_server_builds_from_the_route(self):
        for rid, method, path, body, cls, expected in ROUTES:
            if rid == "kill.on":
                continue
            with self.subTest(route=rid), Spy(["rules.check_and_log"]) as spy:
                self.web.request(method, path, body)
                call = spy.calls[0]
                self.assertEqual(json.loads(call[1][0]), {"type": "serve_request", "route": rid, "class": cls,
                                                          "platform": "web"})
                self.assertEqual(call[2].get("kill_state"), "off")
                self.assertIsNone(call[2].get("stop_reason"))
                self.assertTrue(call[2].get("log", True))

    def test_the_action_never_holds_text_from_the_request(self):
        with Spy(["rules.check_and_log"]) as spy:
            self.web.post("/v1/queue/Q-0001/answer", {"answer": SENTINEL})
            self.web.post("/v1/queue", {"kind": "task", "title": SENTINEL})
        for call in spy.calls:
            self.assertNotIn(SENTINEL, call[1][0])
            self.assertNotIn("Q-0001", call[1][0])

    def test_if_not_open_calls_add_once_and_not_add(self):
        with Spy(CORE) as spy:
            self.web.post("/v1/queue", {"kind": "task", "title": "T", "if_not_open": True})
        self.assertEqual(spy.names().count("taskqueue.add_once"), 1)

    def test_a_refused_request_never_reaches_the_core(self):
        with Spy(CORE) as spy:
            self.web.post("/v1/queue", {"kind": "task", "title": "T"}, token="umt1_" + "A" * 43)
            self.web.post("/v1/queue", {"kind": "task", "title": "T"}, origin=False)
            self.web.request("OPTIONS", "/v1/queue")
        self.assertEqual([n for n in spy.names() if n not in ("logbook.append(request)", "kill.state")], [])

    def test_a_pipeline_that_is_called_with_a_refused_request_raises(self):
        # W6.R5.5: the pipeline cannot be entered from a Refuse verdict; the server passes an Allow only
        from tests.serve.support import servegate, serve
        with self.assertRaises(Exception):
            serve.Backend.run_pipeline(self.web.backend, servegate.Refuse(403, "host"), None, None)


# --------------------------------------------------------------------------------------- the differential


def add(kind, title, rec=None, once=False):
    argv = ["queue", "add", "--kind", kind, title] + (["--recommendation", rec] if rec is not None else []) \
        + (["--if-not-open"] if once else [])
    body = {"kind": kind, "title": title}
    if rec is not None:
        body["recommendation"] = rec
    if once:
        body["if_not_open"] = True
    return argv, ("POST", "/v1/queue", body)


def answer(qid, text, revisit=None):
    argv = ["queue", "answer", qid, "--answer", text] + (["--revisit-if", revisit] if revisit is not None else [])
    body = {"answer": text}
    if revisit is not None:
        body["revisit_if"] = revisit
    return argv, ("POST", f"/v1/queue/{qid}/answer", body)


def close(qid):
    return ["queue", "close", qid], ("POST", f"/v1/queue/{qid}/close", {})


T = add("task", "T")
D = add("decision", "D", "Do it")
KILL = (["kill", "on"], ("POST", "/v1/kill/on", {}))

# name -> (setup steps, [steps]); a step is (cli argv, (method, path, body)). Setup runs the command line on both roots.
SCENARIOS = {
    "add a task": ([], [add("task", "Buy milk")]),
    "add a task with a recommendation": ([], [add("task", "Buy milk", "Today")]),
    "add a decision": ([], [add("decision", "Which one?")]),
    "add a decision with a recommendation": ([], [add("decision", "Which one?", "The first")]),
    "add once on an empty queue": ([], [add("task", "T", once=True)]),
    "add once when the same row is open": ([T], [add("task", "T", once=True)]),
    "add once when the same title is open as a decision": ([add("decision", "T")], [add("task", "T", once=True)]),
    "add once after the same row was closed": ([T, close("Q-0001")], [add("task", "T", once=True)]),
    "add twice without once": ([T], [add("task", "T")]),
    "title with a pipe": ([], [add("task", "a|b")]),
    "title of 200 characters": ([], [add("task", "x" * 200)]),
    "title of 201 characters": ([], [add("task", "x" * 201)]),
    "empty title": ([], [add("task", "")]),
    "title of spaces": ([], [add("task", "   ")]),
    "title with accents": ([], [add("task", "caf\u00e9 \u00fcber")]),
    "recommendation of 500 characters": ([], [add("task", "T", "r" * 500)]),
    "recommendation of 501 characters": ([], [add("task", "T", "r" * 501)]),
    "kind that does not exist": ([], [(["queue", "add", "--kind", "nope", "T"], ("POST", "/v1/queue",
                                                                              {"kind": "nope", "title": "T"}))]),
    "answer an open task": ([T], [answer("Q-0001", "Yes please")]),
    "answer an open decision with revisit_if": ([D], [answer("Q-0001", "Yes", "a cheaper offer")]),
    "answer a decision with revisit_if none": ([D], [answer("Q-0001", "No", "none")]),
    "answer a decision without revisit_if": ([D], [answer("Q-0001", "Yes")]),
    "answer a task with revisit_if": ([T], [answer("Q-0001", "Yes", "never")]),
    "answer a row that does not exist": ([], [answer("Q-0099", "Yes")]),
    "answer a row that is answered": ([T, answer("Q-0001", "Yes")], [answer("Q-0001", "Again")]),
    "answer a row that is closed": ([T, close("Q-0001")], [answer("Q-0001", "Late")]),
    "answer with a pipe": ([T], [answer("Q-0001", "a|b")]),
    "answer of 500 characters": ([T], [answer("Q-0001", "a" * 500)]),
    "answer of 501 characters": ([T], [answer("Q-0001", "a" * 501)]),
    "revisit_if of 201 characters": ([D], [answer("Q-0001", "Yes", "w" * 201)]),
    "close an open task": ([T], [close("Q-0001")]),
    "close an answered decision": ([D, answer("Q-0001", "Yes", "none")], [close("Q-0001")]),
    "close a closed row": ([T, close("Q-0001")], [close("Q-0001")]),
    "close a row that does not exist": ([], [close("Q-0042")]),
    "kill on": ([], [KILL]),
    "kill on twice": ([KILL], [KILL]),
    "kill on with a reason": ([], [(["kill", "on", "--reason", "stop now"], ("POST", "/v1/kill/on", {"reason": "stop now"}))]),
    "kill on with a reason of 201 characters": ([], [(["kill", "on", "--reason", "r" * 201],
                                                      ("POST", "/v1/kill/on", {"reason": "r" * 201}))]),
    "add, add, answer the first, close the second": ([], [add("task", "A"), add("decision", "B"),
                                                          answer("Q-0001", "ok"), close("Q-0002")]),
    "a decision from add to close": ([], [add("decision", "D", "R"), answer("Q-0001", "Yes", "new facts"),
                                          close("Q-0001")]),
    "five tasks and one once": ([], [add("task", f"t{i}") for i in range(5)] + [add("task", "t2", once=True)]),
}


class DifferentialTests(RootCase):
    """Each scenario runs once through the command line on one root and once through requests on an identical root."""

    def roots(self):
        a, b = self.tmp / "cli", self.tmp / "web"
        for r in (a, b):
            r.mkdir()
            make_root(r, token=TOKEN)
            make_logbook(r)
        return a, b

    def test_there_are_at_least_40_scenarios(self):
        self.assertGreaterEqual(len(SCENARIOS), 40)

    def test_the_command_line_and_the_request_leave_the_same_bytes_and_the_same_entries(self):
        for name, (setup, steps) in SCENARIOS.items():
            with self.subTest(scenario=name):
                a, b = self.roots()
                for argv, _req in setup:
                    ca, _ = run_cli(a, *argv)
                    cb, _ = run_cli(b, *argv)
                    self.assertEqual(ca, cb)
                web = InProc(b)
                for argv, (method, path, body) in steps:
                    code_cli, _out = run_cli(a, *argv)
                    r = web.request(method, path, body)
                    self.assertEqual(r.code, code_cli, f"{name}: {argv} gave {code_cli}, the request {r}")
                    self.assertEqual((r.ok, r.word == "done"), (code_cli == 0, code_cli == 0))
                self.assertEqual((a / "queue.md").read_bytes(), (b / "queue.md").read_bytes(), name)
                ka, kb = a / ".umwayi" / "KILL", b / ".umwayi" / "KILL"
                self.assertEqual(ka.exists(), kb.exists())
                if ka.exists():
                    self.assertEqual(ka.read_bytes(), kb.read_bytes())
                self.assertEqual(plain_entries(a), plain_entries(b), name)

    def test_the_reads_say_what_the_command_line_says(self):
        a, b = self.roots()
        for argv, _r in (add("task", "One"), add("decision", "Two", "R"), add("task", "Three"), answer("Q-0001", "ok"),
                         close("Q-0003")):
            run_cli(a, *argv)
            run_cli(b, *argv)
        web = InProc(b)
        for query, args in (("", []), ("?status=open", ["--status", "open"]), ("?kind=decision", ["--kind", "decision"]),
                            ("?status=closed&kind=task", ["--status", "closed", "--kind", "task"]),
                            ("?status=answered", ["--status", "answered"])):
            code, out = run_cli(a, "queue", "list", *args)
            r = web.get("/v1/queue" + query)
            self.assertEqual((r.code, code), (0, 0))
            self.assertEqual([row["id"] for row in r.data["rows"]], [ln.split()[0] for ln in out.splitlines()
                                                                      if ln.startswith("Q-")], query)
            self.assertFalse(r.data["more"])
        row = web.get("/v1/queue?kind=decision").data["rows"][0]
        self.assertEqual(sorted(row), ["answer", "answered", "id", "kind", "recommendation", "status", "title"])
        self.assertEqual((row["id"], row["title"], row["recommendation"]), ("Q-0002", "Two", "R"))

    def test_status_matches_kill_status(self):
        a, b = self.roots()
        web = InProc(b)
        for turn_on in (False, True):
            if turn_on:
                run_cli(a, "kill", "on")
                run_cli(b, "kill", "on")
            code, out = run_cli(a, "kill", "status")
            r = web.get("/v1/status")
            self.assertEqual(r.data["kill_switch"], out.split()[0])
            self.assertEqual(r.code, 0)

    def test_logbook_verify_and_snapshot_agree_with_the_commands(self):
        a, b = self.roots()
        for argv, _r in (add("task", "One"), add("decision", "Two")):
            run_cli(a, *argv)
            run_cli(b, *argv)
        web = InProc(b)
        code, _ = run_cli(a, "logbook", "verify")
        r = web.get("/v1/logbook")
        self.assertEqual((r.code, code), (0, 0))
        self.assertEqual(set(r.data), {"entries", "chain_length", "problems"})
        self.assertEqual(r.data["problems"], 0)
        code, _ = run_cli(a, "view", "snapshot")
        snap = json.loads((a / ".umwayi" / "snapshot.json").read_text())
        r = web.get("/v1/snapshot")
        self.assertEqual(r.code, 0)
        for key in ("schema", "date", "queue", "rules", "kill_switch", "schedule"):
            self.assertEqual(r.data[key], snap[key], key)

    def test_agents_list_check_and_budget_status_agree_with_the_commands(self):
        a, b = self.roots()
        for r_ in (a, b):
            write_agents(r_, self.tmp / "work")
        web = InProc(b)
        code, out = run_cli(a, "agent", "list")
        r = web.get("/v1/agents")
        self.assertEqual((r.code, code), (0, 0))
        self.assertEqual(r.data["agents"], [{"name": "helper", "platform": "kiro", "transport": "cli"}])
        code, out = run_cli(a, "agent", "check", "helper")
        r = web.post("/v1/agents/helper/check", {})
        self.assertEqual(r.code, code)
        code, out = run_cli(a, "agent", "check", "nobody")
        r = web.post("/v1/agents/nobody/check", {})
        self.assertEqual((r.code, code), (64, 64))
        code, out = run_cli(a, "budget", "status", "--date", DATE)
        r = web.get("/v1/budget")
        self.assertEqual(r.code, code)

    def test_the_replies_hold_no_path_and_no_planted_text(self):
        a, b = self.roots()
        work = self.tmp / ("work-" + SENTINEL)
        write_agents(b, work)
        (b / "memory" / "master.md").write_text(SENTINEL + "\n")
        (b / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": [SENTINEL]}))
        (b / "rules.yaml").write_text((b / "rules.yaml").read_text() + f"\n# {SENTINEL}\n")
        web = InProc(b)
        replies = [web.get(p) for p in ("/v1/status", "/v1/snapshot", "/v1/logbook", "/v1/budget", "/v1/agents")]
        replies.append(web.post("/v1/agents/helper/check", {}))
        for r in replies:
            self.assertNotIn(SENTINEL.encode(), r.raw, r)
            self.assertNotIn(str(self.tmp).encode(), r.raw, r)


# ------------------------------------------------------------------------------------------ the code guard

SERVE_FILES = sorted((REPO / "umwayi").glob("serve*.py"))


class CodeGuardTests(unittest.TestCase):
    def sources(self):
        found = {p.name: p.read_text(encoding="utf-8") for p in SERVE_FILES}
        self.assertTrue({"serve.py", "servegate.py", "servetoken.py"} <= set(found), "the serve modules are not there yet")
        return found

    def test_the_files_exist(self):
        self.assertEqual({p.name for p in SERVE_FILES} & {"serve.py", "servegate.py", "servetoken.py"},
                         {"serve.py", "servegate.py", "servetoken.py"})

    def test_no_serve_module_opens_the_logbook_the_queue_the_rules_or_the_kill_file_by_name(self):
        for name, src in self.sources().items():
            consts = {n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            for banned in ("LOGBOOK.md", "queue.md", "KILL", ".umwayi/KILL", "logbook.sha256"):
                self.assertFalse(any(banned == c or c.endswith("/" + banned) for c in consts), f"{name} names {banned}")
            self.assertEqual(sum(1 for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant)
                                 and n.value == "rules.yaml"), 1 if name == "serve.py" else 0, name)

    def test_no_serve_module_imports_subprocess_or_a_shell(self):
        for name, src in self.sources().items():
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    self.assertNotIn("subprocess", [a.name for a in node.names], name)
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "subprocess", name)
            for bad in ("os.system", "os.popen", "shell=True"):
                self.assertNotIn(bad, src)

    def test_json_loads_is_called_only_on_a_body_the_token_record_and_build_json(self):
        for name, src in self.sources().items():
            n = len(re.findall(r"json\.loads\(", src))
            self.assertEqual(n, {"servegate.py": 1, "servetoken.py": 1, "serve.py": 1}.get(name, 0), name)  # serve.py: build.json

    def test_no_function_compares_an_answer_with_yes_or_ask_me_first(self):
        for name, src in self.sources().items():
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Compare):
                    parts = [node.left] + node.comparators
                    for p in parts:
                        if isinstance(p, ast.Constant):
                            self.assertNotIn(p.value, ("Yes", "No", "Ask me first"), f"{name} line {node.lineno}")
                        if isinstance(p, ast.Attribute):
                            self.assertNotIn(p.attr, ("YES", "NO", "ASK"), f"{name} line {node.lineno}")

    def test_the_network_modules_are_imported_only_inside_a_function(self):
        src = (REPO / "umwayi" / "serve.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        top = {id(n) for n in tree.body}
        found = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for m in mods:
                    if m.split(".")[0] in ("socket", "http", "socketserver", "ssl"):
                        found.append(m)
                        self.assertNotIn(id(node), top, f"{m} must be imported inside the function that starts the server")
        self.assertTrue(found)

    def test_the_banned_commands_do_not_appear_in_any_serve_module(self):
        banned = ("publish", "archive", "schedule", "autonomy", "turn_off", "recover_torn", "settle_lost", "calibrate",
                  "petition", "reopen", "workflow", "steward", "social", "run_agent", "chat_agent", "login_agent",
                  "logbook.seal", "logbook.anchor", "--approved-by", "approved_by")
        for name, src in self.sources().items():
            code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
            code = re.sub(r'""".*?"""', "", code, flags=re.S)
            code = re.sub(r"'''.*?'''", "", code, flags=re.S)
            for b in banned:
                self.assertNotIn(b, code, f"{name} mentions {b}")

    def test_the_core_is_called_through_the_module_so_a_spy_sees_it(self):
        src = (REPO / "umwayi" / "serve.py").read_text(encoding="utf-8")
        for bad in ("from umwayi.kill import", "from umwayi.rules import", "from umwayi.logbook import",
                    "from umwayi.taskqueue import"):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
