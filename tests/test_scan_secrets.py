"""The security scan (tasks.md S.2.4, requirement S.R8): secrets in any output or logbook entry.

A planted secret, each a unique word, goes into every place one can enter (S.R8.1): the prompt three ways, every
credential name umwayi knows of, the owner's own telemetry header, memory, rules, the queue, an article, a jobs file,
a unit file, a tool input through the hooks, an ACP message, a telemetry body, the fakes' own output (an email) and
the text of a planted crash. Then every byte umwayi printed (every command's stdout and stderr) and every file under
the root, the unit folder, TMPDIR and the capture file is swept (S.R8.2): no planted word, no run header secret and no
canary token may be in it, except in the short list of places a layer puts it on purpose.

Every command is a real child process in the whole-system test's world (tests/whole_system_support.py).
"""

import json
import unittest

from tests.budget.support import api_request, logs, user_prompt_event
from tests.whole_system_support import World
from umwayi.agents import CLAUDE_CREDENTIAL_ENV, KIRO_CREDENTIAL_ENV

ENV_NAMES = tuple(CLAUDE_CREDENTIAL_ENV) + tuple(KIRO_CREDENTIAL_ENV) + ("OTEL_EXPORTER_OTLP_HEADERS",)
PLANTED = {
    "prompt argument": "S2PROMPTARG", "prompt file": "S2PROMPTFILE", "prompt stdin": "S2PROMPTSTDIN",
    **{f"env {n}": f"S2ENV{n.replace('_', '')}" for n in ENV_NAMES},
    "private memory": "S2MEMORY", "rules comment": "S2RULES", "queue answer": "S2ANSWER",
    "article body": "S2ARTICLE", "jobs comment": "S2JOBS", "unit file": "S2UNIT", "tool input": "S2TOOL",
    "acp message": "S2ACP", "telemetry body": "S2TELEMETRY", "crash text": "S2CRASH",
    "auth email": "owner@example.invalid",  # the fake `claude auth status` and the fake node print it
}
# where a layer puts a planted word on purpose: (word, where it may be, why)
ALLOWED = [
    ("S2MEMORY", "memory/", "the owner's own file"),
    ("S2RULES", "rules.yaml", "the owner's own file"),
    ("S2ANSWER", "queue.md", "layer 3 keeps the answer in queue.md; the logbook records its length only"),
    ("S2ARTICLE", "articles/", "the owner's own file"),
    ("S2JOBS", "jobs.yaml", "the owner's own file"),
    ("S2UNIT", "units/", "the hand edit itself; schedule check and remove refuse it without printing it"),
    ("S2ACP", "output: agent chat", "an ACP chat prints the agent's text for the owner (layer 10)"),
    ("S2PROMPTSTDIN", "output: agent chat reviewer", "a cli chat hands the owner's terminal to the agent; the line is "
                                                    "the agent's echo, not umwayi's (layer 10, part 5)"),
]


class SecretSweepTests(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.addCleanup(self.w.cleanup)
        self.w.build()

    def plant_files(self):
        w = self.w
        (w.root / "memory" / "private" / "bank.md").write_text(f"card {PLANTED['private memory']}\n", encoding="utf-8")
        rules = w.root / "rules.yaml"
        rules.write_text(f"# {PLANTED['rules comment']}\n" + rules.read_text(encoding="utf-8"), encoding="utf-8")
        jobs = w.root / "jobs.yaml"
        jobs.write_text(f"# {PLANTED['jobs comment']}\n" + jobs.read_text(encoding="utf-8"), encoding="utf-8")
        art = w.root / "articles" / "example.md"
        art.write_text(art.read_text(encoding="utf-8").rstrip("\n") + f"\n\nA later paragraph {PLANTED['article body']}.\n",
                       encoding="utf-8")

    def run_the_scan(self):
        w = self.w
        env = {n: PLANTED[f"env {n}"] for n in ENV_NAMES if n != "OTEL_EXPORTER_OTLP_HEADERS"}
        env["OTEL_EXPORTER_OTLP_HEADERS"] = "authorization=" + PLANTED["env OTEL_EXPORTER_OTLP_HEADERS"]
        u = lambda *a, **k: w.u(*a, extra=dict(env, **k.pop("extra", {})), **k)  # noqa: E731
        self.plant_files()
        self.assertEqual(u("memory", "bundle").returncode, 0)
        u("queue", "add", "--kind", "decision", "Ship it?")
        self.assertEqual(u("queue", "answer", "Q-0001", "--answer", f"Yes {PLANTED['queue answer']}", "--revisit-if", "none").returncode, 0)
        u("logbook", "seal", "--chain", "--by", "Owner")
        u("check", json.dumps({"type": "read_memory", "note": PLANTED["tool input"]}))
        u("run", str(w.root / "jobs.yaml"), "--job", "open-queue")
        u("social", "draft", "articles/example.md")
        w.hook("claude_code", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                               "tool_input": {"command": f"echo {PLANTED['tool input']}"}})
        w.hook("kiro", {"hook_event_name": "PreToolUse", "tool_name": "execute_bash",
                        "tool_input": {"command": f"echo {PLANTED['tool input']}"}})
        w.hook("stdio", {"tool_name": "deploy", "tool_input": {"target": PLANTED["tool input"]}})
        report = {"do": "otlp", "body": logs(user_prompt_event(), api_request(cost_micros=99))}
        report["body"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"].append(
            {"key": "prompt", "value": {"stringValue": PLANTED["telemetry body"]}})
        capture = w.base / "capture.jsonl"
        self.assertEqual(u("agent", "run", "reviewer", "--prompt", PLANTED["prompt argument"],
                           extra={"FAKE_SCRIPT": json.dumps([report, {"do": "exit", "code": 0}]),
                                  "UMWAYI_TELEMETRY_CAPTURE": str(capture)}).returncode, 0)
        prompt_file = w.base / "prompt.txt"
        prompt_file.write_text(PLANTED["prompt file"] + "\n", encoding="utf-8")
        self.assertEqual(u("agent", "run", "kiro", "--prompt-file", str(prompt_file)).returncode, 0)
        self.assertEqual(u("agent", "run", "reviewer", "-", input=PLANTED["prompt stdin"],
                           extra={"FAKE_SCRIPT": "[]"}).returncode, 0)
        u("agent", "chat", "reviewer", input=f"{PLANTED['prompt stdin']}\n/quit\n", extra={"FAKE_SCRIPT": "[]"})
        w.node_answers({"turns": [[{"chunk": f"agent says {PLANTED['acp message']}"},
                                   {"otlp": {"body": logs(api_request(cost_micros=5))}}]]})
        self.assertEqual(u("agent", "chat", "acp-reviewer", input=f"go {PLANTED['prompt stdin']}\n:quit\n").returncode, 0)
        spec = {"turns": [[{"chunk": f"kiro says {PLANTED['acp message']}"}]]}
        u("agent", "chat", "kiro-acp", input="go\n:quit\n", extra={"FAKE_ACP": json.dumps(spec)})
        self.assertEqual(u("schedule", "install", "answered-queue", "--approved-by", "Owner").returncode, 0)
        unit = w.unit_file("answered-queue", "service")
        unit.write_text(unit.read_text(encoding="utf-8") + f"# {PLANTED['unit file']}\n", encoding="utf-8")
        u("schedule", "check")
        u("schedule", "remove", "answered-queue")
        u("queue", "add", "--kind", "task", "Crash", fault="umwayi.taskqueue:add:crash",
          extra={"UMWAYI_FAULT_TEXT": PLANTED["crash text"]})
        u("agent", "run", "reviewer", "--prompt", "go", fault="umwayi.budget:settle_text:crash",
          extra={"UMWAYI_FAULT_TEXT": PLANTED["crash text"], "FAKE_SCRIPT": "[]"})
        u("budget", "settle-lost", "--by", "Owner")
        u("budget", "status")
        u("logbook", "verify")
        return capture

    def secrets_of_runs(self) -> list:
        """The run header secret of every start and every canary token, read from the fakes' own records."""
        out = []
        for c in self.w.calls():
            if c.get("started") and c.get("otel", {}).get("OTEL_EXPORTER_OTLP_HEADERS"):
                out.append(("run header secret", c["otel"]["OTEL_EXPORTER_OTLP_HEADERS"].split("=", 1)[1]))
            if c.get("event") == "session_start_hook":
                args = c.get("args", [])
                if "--token" in args:
                    out.append(("canary token", args[args.index("--token") + 1]))
        return out

    def places(self, capture):
        """(where, text) of every byte umwayi printed or wrote."""
        w = self.w
        for words, text in w.outputs:
            yield f"output: {words}", text
        for top, label in ((w.root, ""), (w.units, "units/"), (w.tmpdir, "tmp/")):
            if not top.exists():
                continue
            for p in sorted(top.rglob("*")):
                if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts:
                    yield label + p.relative_to(top).as_posix(), p.read_bytes().decode("utf-8", "replace")
        if capture.exists():
            yield "capture file", capture.read_text(encoding="utf-8")

    def test_no_planted_secret_in_any_byte_umwayi_wrote_or_printed(self):
        capture = self.run_the_scan()
        runs = self.secrets_of_runs()
        self.assertTrue([x for x in runs if x[0] == "run header secret"], "no start was seen")
        self.assertTrue([x for x in runs if x[0] == "canary token"], "no ACP chat canary was seen")
        found = []
        for where, text in self.places(capture):
            for what, word in list(PLANTED.items()) + runs:
                if word in text and not any(word == w_ and where.startswith(p) for w_, p, _why in ALLOWED):
                    line = next(i for i, x in enumerate(text.split("\n"), 1) if word in x)
                    found.append(f"{what} in {where} line {line}")
        self.assertEqual(found, [])
        # and the allowed places really hold them, so the sweep could see them
        seen = {where for where, text in self.places(capture) if PLANTED["acp message"] in text}
        self.assertTrue([x for x in seen if x.startswith("output: agent chat")], seen)

    def test_a_planted_leak_is_found_with_its_file_and_line(self):
        """The sweep itself: a test-only fault that prints the prompt is found."""
        w = self.w
        w.u("agent", "run", "reviewer", "--prompt", PLANTED["prompt argument"], fault="umwayi.agents:_one_line:crash",
            extra={"UMWAYI_FAULT_TEXT": PLANTED["prompt argument"], "FAKE_SCRIPT": "[]"})
        w.outputs.append(("planted leak", f"line one\nthe prompt was {PLANTED['prompt argument']}\n"))
        found = [f"{where} line {next(i for i, x in enumerate(t.split(chr(10)), 1) if PLANTED['prompt argument'] in x)}"
                 for where, t in self.places(w.base / "none") if PLANTED["prompt argument"] in t]
        self.assertEqual(found, ["output: planted leak line 2"])


if __name__ == "__main__":
    unittest.main()
