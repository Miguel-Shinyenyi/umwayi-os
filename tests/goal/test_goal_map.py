"""W37: the goal map document (umwayi/goal.py `map_data`) and the command `umwayi goal map`.

The document is the contract of docs/goal-map.md. These tests build goals through the public functions of
umwayi/goalstate.py in a temporary root (the logbook is dated with fakeroot.DATE, today's UTC date) and check: the exact
keys and types, the states, roles, worktrees, ages and budget, the last 40 events with a fixed label per kind, every
unknown with its note, the supervisor read from the lock file without locking it, and that nothing is written, no
process starts and no planted secret, path or event data reaches the document.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from tests.goal.fakeroot import DATE, REPO
from tests.goal.goalsupport import GoalCase
from umwayi import goal as gl
from umwayi import goallog, goalstate as gs, kill
from umwayi.cli import main

SECRET = "sk-live-W37PLANTEDSECRET9"
WORD_SECRET = "zebrasecretword"  # an ordinary word: hidden only because it comes after the cut at 80 characters
EVENT_SECRET = "w37secretreason"  # a valid event word that must never be copied out of the event data
TOP = ["version", "now", "kill_switch", "goal", "supervisor", "tasks", "events", "notes"]
GOAL_KEYS = {"id", "title", "state", "budget", "needs_owner"}
SUP_KEYS = {"alive", "pid_known", "last_event_age_s", "state"}
TASK_KEYS = {"id", "title", "state", "role_now", "worktree", "age_s", "needs_owner_reason", "pr"}
EVENT_KEYS = {"t", "kind", "task", "text"}


def tree(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        rel = p.relative_to(root).as_posix()
        st = os.lstat(p)
        out[rel] = (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else "x",
                    st.st_mtime_ns, st.st_mode)
    return out


def at(epoch):
    return gl._map_iso(epoch)


class MapCase(GoalCase):
    def doc(self, now=None):
        return gl.map_data(self.root, self.clock() if now is None else now)

    def running(self, n=3):
        goal = self.approved(n)
        self.move(goal, "T-01", "running", "start", role="builder", agent="claude-build", cap_uu=30,
                  branch="umwayi/g-0001-t-01", tip="a" * 40, base="b" * 40)
        return goal

    def event(self, goal, task, kind, data, when=None):
        p = gs.events_path(self.root, goal, task)
        old = p.read_bytes() if p.exists() else b""
        n = len(goallog.read(old)[0]) + 1
        p.write_bytes(old + goallog.make_line(n, at(self.clock() if when is None else when), kind, data))


class ShapeTests(MapCase):
    def test_no_goal_gives_a_null_goal_and_everything_else_empty(self):
        d = self.doc()
        self.assertEqual(d, {"version": 1, "now": at(self.clock()), "kill_switch": "off", "goal": None,
                             "supervisor": {"alive": False, "pid_known": False, "last_event_age_s": None, "state": "idle"},
                             "tasks": [], "events": [], "notes": []})
        self.assertEqual(list(d), TOP)

    def test_every_object_has_exactly_the_keys_of_the_contract_and_their_types(self):
        goal = self.running()
        self.event(goal, "T-01", "output", {"lines": 3, "bytes": 40, "skipped": 0})
        d = self.doc()
        self.assertEqual(list(d), TOP)
        self.assertEqual(set(d["goal"]), GOAL_KEYS)
        self.assertEqual(set(d["goal"]["budget"]), {"used_uu", "reserved_uu", "cap_uu"})
        self.assertEqual(set(d["supervisor"]), SUP_KEYS)
        self.assertTrue(d["tasks"] and d["events"])
        for t in d["tasks"]:
            self.assertEqual(set(t), TASK_KEYS)
            self.assertIn(t["role_now"], ("builder", "tester", "guide", "none"))
            self.assertIsNone(t["pr"])
            self.assertTrue(t["worktree"] is None or (set(t["worktree"]) == {"branch", "clean"} and t["worktree"]["clean"] is None))
            self.assertTrue(t["age_s"] is None or (isinstance(t["age_s"], int) and t["age_s"] >= 0))
        for e in d["events"]:
            self.assertEqual(set(e), EVENT_KEYS)
            self.assertIn(e["text"], gl.MAP_EVENT_TEXT.values())
        self.assertRegex(d["now"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        json.dumps(d, ensure_ascii=True)  # plain JSON

    def test_the_command_and_the_function_give_the_same_document(self):
        self.running()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("umwayi.goal.time.time", return_value=self.clock()), redirect_stderr(err):
            code = main(["--root", str(self.root), "goal", "map"], out=out)
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(json.loads(out.getvalue()), self.doc())
        self.assertEqual(err.getvalue(), "")

    def test_an_extra_argument_is_a_usage_error(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--root", str(self.root), "goal", "map", "G-0001"]), 64)

    def test_a_real_process_prints_the_document_and_exits_0(self):
        self.running()
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "goal", "map"], capture_output=True,
                           text=True, env={**os.environ, "PYTHONPATH": str(REPO)}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d["goal"]["id"], "G-0001")
        self.assertNotIn(str(self.root), r.stdout)


class ContentTests(MapCase):
    def test_states_roles_worktrees_ages_and_the_reason_of_a_task_that_needs_the_owner(self):
        goal = self.running()
        self.clock.advance(90)
        self.move(goal, "T-02", "needs owner", "unclear")
        self.clock.advance(10)
        d = self.doc()
        t1, t2, t3 = d["tasks"]
        self.assertEqual((t1["id"], t1["state"], t1["role_now"], t1["age_s"]), ("T-01", "running", "builder", 100))
        self.assertEqual(t1["worktree"], {"branch": "umwayi/g-0001-t-01", "clean": None})
        self.assertEqual((t2["state"], t2["needs_owner_reason"], t2["role_now"], t2["age_s"]), ("needs owner", "unclear", "none", 10))
        self.assertEqual((t3["state"], t3["worktree"], t3["age_s"], t3["needs_owner_reason"]), ("queued", None, None, None))
        self.assertEqual(d["goal"]["state"], "active")
        self.assertTrue(d["goal"]["needs_owner"])
        self.assertEqual(d["supervisor"]["last_event_age_s"], 10)

    def test_the_role_of_a_later_run_comes_from_its_started_event(self):
        goal = self.running()
        self.event(goal, "T-01", "started", {"role": "tester", "agent": "kiro-test", "cap_uu": 12, "pid": 0})
        d = self.doc()
        self.assertEqual(d["tasks"][0]["role_now"], "tester")
        self.assertEqual(d["goal"]["budget"]["reserved_uu"], 12)
        self.event(goal, "T-01", "started", {"role": "check", "agent": "kiro-test", "cap_uu": 5, "pid": 0})
        self.assertEqual(self.doc()["tasks"][0]["role_now"], "none")

    def test_the_budget_is_the_plan_and_the_task_spend_against_the_goal_cap(self):
        self.running()
        b = self.doc()["goal"]["budget"]
        self.assertEqual(b, {"used_uu": 20, "reserved_uu": 0, "cap_uu": 100})

    def test_a_plan_that_waits_for_the_owner_is_needs_owner_and_has_no_tasks_running(self):
        self.planned(2)
        d = self.doc()
        self.assertEqual(d["goal"]["state"], "plan")
        self.assertTrue(d["goal"]["needs_owner"])
        self.assertEqual(d["supervisor"]["state"], "idle")

    def test_the_newest_goal_is_shown(self):
        self.approved(1)
        self.started(text="A second goal for the owner to read.")
        d = self.doc()
        self.assertEqual(d["goal"]["id"], "G-0002")
        self.assertEqual(d["goal"]["title"], "A second goal for the owner to read.")

    def test_the_last_40_real_events_in_time_order_with_a_fixed_label_and_no_poll(self):
        goal = self.running()
        for i in range(60):
            self.clock.advance(1)
            self.event(goal, "T-01" if i % 2 else "T-02", "output", {"lines": i, "bytes": i, "skipped": 0})
            self.event(goal, "T-01", "poll", {})
        d = self.doc()
        self.assertEqual(len(d["events"]), 40)
        self.assertEqual([e["t"] for e in d["events"]], sorted(e["t"] for e in d["events"]))
        self.assertEqual(d["events"][-1]["t"], at(self.clock()))
        self.assertTrue(all(e["kind"] == "output" and e["text"] == "the helper wrote output" for e in d["events"]))

    def test_a_kill_switch_that_is_on_is_on(self):
        kill.turn_on(self.root, DATE, "test")
        self.assertEqual(self.doc()["kill_switch"], "on")

    def test_every_event_kind_has_its_label_and_no_label_holds_data(self):
        self.assertEqual(set(gl.MAP_EVENT_TEXT), {k for k, (_spec, real) in goallog.KINDS.items() if real})
        for label in gl.MAP_EVENT_TEXT.values():
            self.assertRegex(label, r"^[a-z][a-z ]+$")


class UnknownTests(MapCase):
    def test_a_hand_edited_logbook_makes_every_state_unknown_with_a_note(self):
        self.running()
        p = self.root / "LOGBOOK.md"
        p.write_text(p.read_text(encoding="utf-8").replace("G-0001", "G-0009", 1), encoding="utf-8")
        d = self.doc()
        self.assertIn(gl.MAP_NOTES["logbook"], d["notes"])
        self.assertEqual(d["goal"]["state"], "unknown")
        self.assertEqual({t["state"] for t in d["tasks"]}, {"unknown"})
        self.assertEqual(d["supervisor"]["state"], "idle")  # read from the lock, not from the logbook

    def test_an_unreadable_task_file_is_an_unknown_task_with_a_note(self):
        goal = self.running()
        (gs.goal_dir(self.root, goal) / "T-02.json").write_text("{not json " + SECRET, encoding="utf-8")
        d = self.doc()
        t2 = d["tasks"][1]
        self.assertEqual((t2["id"], t2["state"], t2["title"]), ("T-02", "unknown", "unreadable"))
        self.assertIn(gl.MAP_NOTES["task"], d["notes"])
        self.assertIsNone(d["goal"]["budget"])
        self.assertNotIn(SECRET, json.dumps(d))

    def test_an_unreadable_goal_file_is_an_unknown_goal_with_a_note(self):
        goal = self.running()
        (gs.goal_dir(self.root, goal) / "goal.json").write_text("[]", encoding="utf-8")
        d = self.doc()
        self.assertEqual(d["goal"], {"id": "G-0001", "title": "unreadable", "state": "unknown", "budget": None,
                                     "needs_owner": False})
        self.assertIn(gl.MAP_NOTES["goal"], d["notes"])

    def test_a_goal_folder_that_is_a_link_gives_no_goal_and_says_why(self):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        other = self.root.parent / "elsewhere"
        other.mkdir()
        os.symlink(other, self.root / ".umwayi" / "goals")
        d = self.doc()
        self.assertIsNone(d["goal"])
        self.assertEqual(d["notes"], [gl.MAP_NOTES["goals"]])

    def test_a_bad_event_line_is_left_out_with_a_note_and_never_quoted(self):
        goal = self.running()
        p = gs.events_path(self.root, goal, "T-01")
        p.write_bytes(p.read_bytes() + ("not an event " + SECRET + "\n").encode())
        d = self.doc()
        self.assertIn(gl.MAP_NOTES["skipped"], d["notes"])
        self.assertNotIn(SECRET, json.dumps(d))

    def test_a_kill_switch_that_cannot_be_read_is_unknown_with_a_note(self):
        with mock.patch("umwayi.goal.kill.state", return_value="garbled"):
            d = self.doc()
        self.assertEqual(d["kill_switch"], "unknown")
        self.assertIn(gl.MAP_NOTES["kill"], d["notes"])

    def test_the_notes_are_fixed_sentences(self):
        for n in gl.MAP_NOTES.values():
            self.assertRegex(n, r"^[A-Z][A-Za-z ,.]+$")
            self.assertNotIn("\u2014", n)


@unittest.skipUnless(os.path.exists("/proc/locks"), "the lock table /proc/locks is Linux only")
class SupervisorTests(MapCase):
    def test_a_held_lock_is_an_alive_supervisor_watching_the_running_task(self):
        self.running()
        with gs.lock(self.root):
            d = self.doc()
        self.assertEqual(d["supervisor"]["alive"], True)
        self.assertEqual(d["supervisor"]["pid_known"], True)
        self.assertEqual(d["supervisor"]["state"], "watching T-01")

    def test_a_lock_file_nobody_holds_is_not_alive_and_a_running_task_then_reads_lost(self):
        self.running()
        with gs.lock(self.root):
            pass
        d = self.doc()
        self.assertEqual((d["supervisor"]["alive"], d["supervisor"]["state"]), (False, "lost"))

    def test_reading_never_takes_the_lock(self):
        self.running()
        taken = []
        real = gs.lock

        def spy(*a, **kw):
            taken.append(a)
            return real(*a, **kw)

        with mock.patch.object(gs, "lock", side_effect=spy), mock.patch("fcntl.flock", side_effect=AssertionError("flock")):
            self.doc()
        self.assertEqual(taken, [])

    def test_a_supervisor_that_holds_the_lock_in_another_thread_is_not_blocked(self):
        self.running()
        ready, done = threading.Event(), threading.Event()

        def hold():
            with gs.lock(self.root):
                ready.set()
                done.wait(10)

        th = threading.Thread(target=hold)
        th.start()
        try:
            ready.wait(10)
            self.assertTrue(self.doc()["supervisor"]["alive"])
        finally:
            done.set()
            th.join(10)

    def test_a_lock_table_that_cannot_be_read_is_unknown_with_a_note(self):
        self.running()
        real_open = open

        def fake_open(path, *a, **kw):
            if str(path) == "/proc/locks":
                raise OSError("no")
            return real_open(path, *a, **kw)

        (self.root / gs.LOCK_REL).parent.mkdir(exist_ok=True)
        (self.root / gs.LOCK_REL).write_bytes(b"")
        with mock.patch("builtins.open", side_effect=fake_open):
            d = self.doc()
        self.assertEqual(d["supervisor"], {"alive": False, "pid_known": False, "last_event_age_s": 0, "state": "unknown"})
        self.assertIn(gl.MAP_NOTES["supervisor"], d["notes"])


class NothingLeaksTests(MapCase):
    def plant(self):
        long_title = "Write the hello page and its two tests for the owner in small safe steps today " + WORD_SECRET
        goal = self.started(text=f"Build it with {SECRET} in it, and nothing else of note.")
        from umwayi import goalpacket as gp
        from tests.goal.goalsupport import plan_bytes
        gs.record_plan(self.root, goal, gp.parse_plan(plan_bytes(2)), "claude-guide", when=self.when, now=self.clock())
        gs.approve_plan(self.root, goal, builder="claude-build", tester="kiro-test", guide="claude-guide", model="sonnet",
                        effort="high", task_budget_uu=30, goal_budget_uu=100, per_day=500, when=self.when, now=self.clock())
        self.move(goal, "T-01", "running", "start", role="builder", agent="claude-build", cap_uu=30,
                  branch="umwayi/g-0001-t-01", tip="a" * 40, base="b" * 40)
        t = gs.read_task(self.root, goal, "T-01")
        t["packet"]["goal"] = f"{long_title} plus {SECRET} and /home/{SECRET}/x"
        t["branch"] = f"/tmp/{SECRET}/worktree"
        t["tip"] = SECRET
        gs.write_task(self.root, goal, "T-01", t)
        t2 = gs.read_task(self.root, goal, "T-02")
        t2["packet"]["goal"] = f"Run rm -rf /home/{SECRET} --force now"
        gs.write_task(self.root, goal, "T-02", t2)
        self.event(goal, "T-01", "stopped", {"reason": EVENT_SECRET})
        self.event(goal, "T-01", "started", {"role": "builder", "agent": EVENT_SECRET, "cap_uu": 30, "pid": 4242})
        wt = self.root.parent / (self.root.name + "-worktrees") / SECRET
        wt.mkdir(parents=True)
        return goal

    def test_a_planted_secret_in_a_title_an_event_and_a_worktree_path_never_appears(self):
        self.plant()
        text = json.dumps(self.doc(), ensure_ascii=False)
        for word in (SECRET, "W37PLANTEDSECRET", WORD_SECRET, EVENT_SECRET, "4242", "/home/", "/tmp/", "rm -rf", "--force",
                     str(self.root), self.root.name + "-worktrees"):
            self.assertNotIn(word, text, word)
        d = self.doc()
        self.assertTrue(d["tasks"][0]["title"].startswith("Write the hello page"))
        self.assertLessEqual(max(len(t["title"]) for t in d["tasks"]), 80)
        self.assertEqual(d["tasks"][0]["worktree"]["branch"], "umwayi/g-0001-t-01")
        self.assertIn("[hidden]", d["goal"]["title"])
        # the planted words are really in the files, so the test could fail
        files = b"".join(p.read_bytes() for p in (self.root / ".umwayi" / "goals").rglob("*") if p.is_file())
        for word in (SECRET, WORD_SECRET, EVENT_SECRET):
            self.assertIn(word.encode(), files, word)

    def test_the_label_hides_words_that_look_like_a_path_a_flag_or_a_key_and_cuts_at_80(self):
        cases = {
            "Do the numbered piece of work number 1 now.": "Do the numbered piece of work number 1 now.",
            "Fix it (step 2), then 2026.": "Fix it (step 2), then 2026.",
            f"use {SECRET} here": "use [hidden] here",
            "see /home/me/x and C:\\x": "see [hidden] and [hidden]",
            "run rm -rf now": "run rm [hidden] now",
            "PLANTEDSECRET word": "[hidden] word",
            "a token=abc and $HOME and `ls`": "a [hidden] and [hidden] and [hidden]",
            "line one\nline two\ttab": "line one line two tab",
            "123456 is too long a number": "[hidden] is too long a number",
        }
        for raw, want in cases.items():
            self.assertEqual(gl.map_label(raw), want, raw)
        self.assertEqual(len(gl.map_label("word " * 40)), 80)
        self.assertTrue(gl.map_label("word " * 40).endswith("..."))
        self.assertEqual(gl.map_label(None), "")


class ReadOnlyTests(MapCase):
    def test_it_writes_nothing_appends_no_entry_and_starts_no_process(self):
        goal = self.running()
        self.event(goal, "T-01", "output", {"lines": 1, "bytes": 1, "skipped": 0})
        before = tree(self.root.parent)
        entries = len(self.entries())
        boom = AssertionError("a process was started")
        with mock.patch("subprocess.Popen", side_effect=boom), mock.patch("os.fork", side_effect=boom), \
                mock.patch("os.posix_spawn", side_effect=boom, create=True), \
                mock.patch("umwayi.fsutil.atomic_write", side_effect=AssertionError("a write")):
            for _ in range(3):
                self.doc()
        self.assertEqual(tree(self.root.parent), before)
        self.assertEqual(len(self.entries()), entries)
        self.assertFalse((self.root / gs.LOCK_REL).exists())

    def test_the_source_of_the_map_has_no_write_and_no_process_call(self):
        import inspect
        src = "".join(inspect.getsource(f) for f in (gl.map_data, gl.map_label, gl._map_lock_holder, gl._map_events,
                                                     gl._map_age, gl._map_iso, gl.map_now, gl.goal_map))
        for word in ("write_", ".write(", "logbook.append", "Writer(", "subprocess", "Popen", "run_git", "unlink", "mkdir", "rename", "gs.lock(", "fcntl",
                     "change_state", "repair", "deny_expired", "mark_lost"):
            self.assertNotIn(word, src, word)
        self.assertNotIn("\u2014", src)


if __name__ == "__main__":
    unittest.main()
