"""W37: the route `goal.map` (`GET /v1/goal-map`) of `umwayi serve`, through the backend without a socket.

Every root here is dated with today's UTC date, never a fixed day: the goal entries, the requests and the token's
expiry. The route must: send the same document `umwayi goal map` prints (the differential test); call `goal.map_data`
once, after the rules check and before the request entry (the spy); be logged like every other read (a rules check and
one request entry); write nothing else and start no process; carry no planted secret, path or event data; and have no
stream, no polling route and nothing under it (a near miss is a 404 from the gate).
"""
import io
import json
import os
import shutil
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from tests.serve.support import TOKEN, InProc, RootCase, logbook_entries, make_root, rules_text, servegate, state_files
from umwayi import goal as gl
from umwayi import goallog, goalpacket as gp, goalstate as gs, logbook
from umwayi.cli import main

TODAY = datetime.now(timezone.utc).date().isoformat()
EXPIRES = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
NOW = 1_800_000_000
SECRET = "sk-live-W37ROUTESECRET7"
EVENT_SECRET = "w37routesecret"
PLAN = json.dumps({"tasks": [{"goal": f"Write the hello page {SECRET} now /home/{SECRET}/x", "context": [],
                              "checks": ["The page check can be answered pass or fail."], "size": 40, "files": ["a.py"]},
                             {"goal": "Write the second piece with care.", "context": [],
                              "checks": ["The second check can be answered pass or fail."], "size": 40, "files": ["b.py"]}]})


def run_cli(root, *argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("umwayi.cli._today", return_value=TODAY), mock.patch("umwayi.goal.time.time", return_value=NOW), \
            redirect_stderr(err):
        code = main(["--root", str(root), *argv], out=out)
    return code, out.getvalue()


def make_goal(root, secret=False):
    when = TODAY
    goal = gs.start_goal(root, f"Build the hello page {SECRET} today." if secret else "Build the hello page today.",
                         "claude-guide", 20, when=when, now=NOW - 600)
    gs.record_plan(root, goal, gp.parse_plan(PLAN.encode()), "claude-guide", when=when, now=NOW - 590)
    gs.approve_plan(root, goal, builder="claude-build", tester="kiro-test", guide="claude-guide", model="sonnet",
                    effort="high", task_budget_uu=30, goal_budget_uu=100, per_day=500, when=when, now=NOW - 580)
    gs.change_state(root, goal, "T-01", "running", "start", role="builder", agent="claude-build", cap_uu=30,
                    branch="umwayi/g-0001-t-01", tip="a" * 40, base="b" * 40, when=when, now=NOW - 300)
    gs.change_state(root, goal, "T-02", "needs owner", "unclear", when=when, now=NOW - 120)
    if secret:
        p = gs.events_path(root, goal, "T-01")
        n = len(goallog.read(p.read_bytes())[0])
        p.write_bytes(p.read_bytes() + goallog.make_line(n + 1, gl._map_iso(NOW - 60), "stopped", {"reason": EVENT_SECRET}))
        t = gs.read_task(root, goal, "T-01")
        t["branch"] = f"/tmp/{SECRET}/wt"
        gs.write_task(root, goal, "T-01", t)
        (Path(str(root) + "-worktrees") / SECRET).mkdir(parents=True)
    return goal


class Case(RootCase):
    def setUp(self):
        super().setUp()
        self.root = make_root(self.tmp / "root", rules=rules_text(), expires=EXPIRES)
        logbook.append(self.root, logbook.Entry(TODAY, "tests", "start", "start", "start"))

    def web(self):
        return InProc(self.root, today=TODAY)

    def get(self, web=None):
        with mock.patch("umwayi.goal.time.time", return_value=NOW):
            return (web or self.web()).get("/v1/goal-map")


class RouteTests(Case):
    def test_the_route_is_in_the_closed_table_as_a_read_that_the_kill_switch_does_not_stop(self):
        r = servegate.route_by_id("goal.map")
        self.assertEqual((r.method, r.path, r.cls, r.body_cap, r.stopped, r.skips_rules, r.query, r.fields),
                         ("GET", "/v1/goal-map", "read", 0, False, False, (), ()))

    def test_no_goal_gives_the_empty_document(self):
        r = self.get()
        self.assertEqual((r.status, r.code), (200, 0))
        self.assertEqual(r.data, gl.map_data(self.root, NOW))
        self.assertIsNone(r.data["goal"])
        self.assertEqual((r.data["tasks"], r.data["events"]), ([], []))

    def test_the_route_sends_exactly_what_the_command_prints(self):
        make_goal(self.root)
        code, out = run_cli(self.root, "goal", "map")
        r = self.get()
        self.assertEqual((code, r.code), (0, 0))
        self.assertEqual(r.data, json.loads(out))
        self.assertEqual(r.data["goal"]["id"], "G-0001")
        self.assertEqual([t["state"] for t in r.data["tasks"]], ["running", "needs owner"])

    def test_the_route_and_the_command_agree_on_two_copies_of_one_root(self):
        make_goal(self.root)
        other = self.tmp / "other"
        shutil.copytree(self.root, other)
        code, out = run_cli(other, "goal", "map")
        r = self.get()
        self.assertEqual(json.loads(out), r.data)

    def test_each_call_is_logged_like_every_other_read(self):
        make_goal(self.root)
        web = self.web()
        self.get(web)  # the first check of a root writes the record of rules.yaml once (layer 13)
        before = len(logbook_entries(self.root))
        for _ in range(2):
            self.assertEqual(self.get(web).code, 0)
        new = logbook_entries(self.root)[before:]
        self.assertEqual([e.source for e in new], ["umwayi check", "umwayi serve"] * 2)
        self.assertEqual(len([e for e in new if e.source == "umwayi serve" and ": GET goal.map, done (exit 0)" in e.added]), 2)

    def test_it_changes_no_file_but_the_logbook_and_starts_no_process(self):
        make_goal(self.root)
        self.get()  # the first read of a day may write the rules record once
        before = state_files(self.root)
        boom = AssertionError("a process was started")
        with mock.patch("subprocess.Popen", side_effect=boom), mock.patch("os.fork", side_effect=boom):
            self.assertEqual(self.get().code, 0)
        self.assertEqual(state_files(self.root), before)
        self.assertFalse((self.root / gs.LOCK_REL).exists())

    def test_a_planted_secret_in_a_title_an_event_and_a_worktree_path_is_in_no_response(self):
        make_goal(self.root, secret=True)
        r = self.get()
        self.assertEqual(r.code, 0)
        for word in (SECRET.encode(), b"W37ROUTESECRET", EVENT_SECRET.encode(), b"/home/", b"/tmp/",
                     str(self.tmp).encode()):
            self.assertNotIn(word, r.raw, word)
        self.assertEqual(r.data["tasks"][0]["worktree"]["branch"], "umwayi/g-0001-t-01")

    def test_a_hand_edited_logbook_gives_unknown_states_and_a_note_and_no_guess(self):
        make_goal(self.root)
        p = self.root / "LOGBOOK.md"
        p.write_text(p.read_text(encoding="utf-8").replace("G-0001", "G-0002", 1), encoding="utf-8")
        data = gl.map_data(self.root, NOW)  # what the command shows
        self.assertEqual(data["goal"]["state"], "unknown")
        self.assertIn(gl.MAP_NOTES["logbook"], data["notes"])
        r = self.get()
        self.assertEqual((r.status, r.word), (500, "logbook"))  # its rules check cannot be logged, as for every route
        self.assertNotIn(b"Build the hello page", r.raw)

    def test_the_kill_switch_does_not_stop_the_read_and_shows_on(self):
        from umwayi import kill
        make_goal(self.root)
        kill.turn_on(self.root, TODAY, "test")
        r = self.get()
        self.assertEqual(r.code, 0)
        self.assertEqual(r.data["kill_switch"], "on")

    def test_without_a_yes_rule_for_reads_it_asks_first_and_sends_nothing(self):
        (self.root / "rules.yaml").write_text(rules_text(read=None))
        make_goal(self.root)
        r = self.get()
        self.assertEqual(r.word, "ask")
        self.assertNotIn(b"hello page", r.raw)

    def test_a_crash_inside_the_map_is_exit_2_with_no_text(self):
        with mock.patch("umwayi.goal.map_data", side_effect=RuntimeError(SECRET)), redirect_stderr(io.StringIO()):
            r = self.get()
        self.assertEqual((r.status, r.code), (500, 2))
        self.assertNotIn(SECRET.encode(), r.raw)


class NoStreamTests(Case):
    def test_no_token_wrong_method_and_every_near_miss_are_refused_by_the_gate(self):
        web = self.web()
        self.assertEqual(web.get("/v1/goal-map", token=None).status, 401)
        self.assertEqual(web.post("/v1/goal-map", {}).status, 405)
        for path in ("/v1/goal-map/stream", "/api/goal-map", "/api/goal-map/stream", "/v1/goal-map/", "/v1/goalmap",
                     "/v1/goal-map/G-0001", "/v1/goal_map"):
            self.assertEqual(web.get(path).status, 404, path)
        r = web.get("/v1/goal-map?goal=G-0001")  # the route lists no query key, so none is taken
        self.assertEqual(r.status, 403)
        self.assertFalse(r.ok)

    def test_the_response_is_one_json_document_and_the_connection_closes(self):
        r = self.get()
        self.assertEqual(r.headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(r.headers["connection"], "close")
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertNotIn("text/event-stream", json.dumps(dict(r.headers)))

    def test_no_route_of_the_table_is_a_stream_or_a_poll(self):
        for r in servegate.ROUTES:
            self.assertNotRegex(r.path, r"stream|poll|events|watch", r.id)

    def test_the_serve_module_has_no_event_stream(self):
        from tests.serve.support import serve
        text = open(serve.module().__file__, encoding="utf-8").read()
        self.assertNotIn("text/event-stream", text)


if __name__ == "__main__":
    import unittest
    unittest.main()
