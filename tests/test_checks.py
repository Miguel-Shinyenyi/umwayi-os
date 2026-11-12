"""The owner checks panel's data (tasks.md UI.4, requirements 12.R7.2 and 12.R10.4).

ui/src/data/checks.js holds the six checks only the owner can run. Every step is taken word for word from the NOTES file named
for its check, and this test finds each piece in that file: a step's text, its code block, each command, the "what to record"
cell of the results table and the heading. A command changed in a NOTES file and not in the page, or the other way round, fails.
Prose that only explains why a check is open (name, reason) is not compared. Standard library only: checks.js is read as text,
no Node. Each rule has a planted fault in a temporary copy, found by a named test.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ORDER = ["10.21", "10.31", "11.6", "B.10", "10.37", "UI.5"]
FILES = ["ui/src/data/checks.js", "adapters/NOTES-layer10.md", "adapters/NOTES-layer11.md", "adapters/NOTES-layer12.md",
         ".kiro/specs/umwayi-os/tasks.md"]
EM_DASH = "\u2014"
_DEC = json.JSONDecoder()
_CHECK_KEY = re.compile(r'^ {4}(id|name|reason|notes|heading): (".*"),$')
_STEP = re.compile(r"^ {6}\{ (.*) \},$")


def parse(js: str) -> list:
    """The checks of checks.js as dicts. The file keeps every string a JSON string on one line, so no Node is needed."""
    checks = []
    for line in js.split("\n"):
        m = _CHECK_KEY.match(line)
        if m:
            if m.group(1) == "id":
                checks.append({"steps": []})
            checks[-1][m.group(1)] = json.loads(m.group(2))
            continue
        m = _STEP.match(line)
        if m:
            body, i, step = m.group(1), 0, {}
            while i < len(body):
                k = re.match(r"(\w+): ", body[i:])
                if not k:
                    raise ValueError(f"cannot read a step: {body[i:i + 40]!r}")
                i += k.end()
                value, i = _DEC.raw_decode(body, i)
                step[k.group(1)] = value
                if body[i:i + 2] == ", ":
                    i += 2
            checks[-1]["steps"].append(step)
    return checks


def find_run(lines: list, wanted: list) -> bool:
    """wanted (stripped lines) is a run of lines of the NOTES file: the first line ends one line of it, the rest are equal."""
    stripped = [x.strip() for x in lines]
    w = [x.strip() for x in wanted]
    for i, line in enumerate(stripped):
        if not line.endswith(w[0]):
            continue
        if stripped[i + 1:i + len(w)] == w[1:]:
            return True
    return False


def problems(root: Path) -> list:
    root = Path(root)
    out = []
    js = (root / "ui/src/data/checks.js").read_text(encoding="utf-8")
    try:
        checks = parse(js)
    except ValueError as e:
        return [str(e)]
    if [c.get("id") for c in checks] != ORDER:
        out.append(f"the checks are {[c.get('id') for c in checks]}, not {ORDER} in this order (12.R7.1)")
    tasks = (root / ".kiro/specs/umwayi-os/tasks.md").read_text(encoding="utf-8")
    notes_cache = {}
    if EM_DASH in js:
        out.append("checks.js has an em dash")
    for c in checks:
        cid = c.get("id", "?")
        if not re.search(r"(?<![\w.])" + re.escape(cid) + r"(?![\w])", tasks):
            out.append(f"check {cid} is not in tasks.md")
        path = root / c.get("notes", "missing")
        if not path.is_file():
            out.append(f"check {cid}: the NOTES file {c.get('notes')} does not exist")
            continue
        if path not in notes_cache:
            notes_cache[path] = path.read_text(encoding="utf-8")
        text = notes_cache[path]
        lines = text.split("\n")
        if not any(re.sub(r"^#+ ", "", ln) == c.get("heading") for ln in lines):
            out.append(f"check {cid}: the heading {c.get('heading')!r} is not in {c['notes']}")
        if not c["steps"]:
            out.append(f"check {cid} has no step")
        ids = [s.get("id") for s in c["steps"]]
        if len(ids) != len(set(ids)):
            out.append(f"check {cid} has two steps with the same id")
        for s in c["steps"]:
            where = f"check {cid} step {s.get('id')}"
            if not s.get("text") or not find_run(lines, s["text"].split("\n")):
                out.append(f"{where}: the text is not word for word in {c['notes']}")
            if "block" in s and not find_run(lines, s["block"].split("\n")):
                out.append(f"{where}: the code block is not word for word in {c['notes']}")
            for cmd in s.get("commands", []):
                if cmd not in text:
                    out.append(f"{where}: the command {cmd!r} is not word for word in {c['notes']}")
            if "record" in s and f"| {s['record']} |" not in text:
                out.append(f"{where}: the record cell is not word for word in {c['notes']}")
    return out


class RepoTests(unittest.TestCase):
    def test_the_six_checks_are_word_for_word_from_their_notes(self):
        self.assertEqual(problems(REPO), [])

    def test_there_are_six_checks_in_the_order_of_the_requirement_and_each_has_steps_and_commands(self):
        checks = parse((REPO / "ui/src/data/checks.js").read_text(encoding="utf-8"))
        self.assertEqual([c["id"] for c in checks], ORDER)
        for c in checks:
            self.assertTrue(c["steps"], c["id"])
            self.assertTrue(any(s.get("commands") for s in c["steps"]), c["id"])
        self.assertEqual({c["id"]: len(c["steps"]) for c in checks},
                         {"10.21": 4, "10.31": 16, "11.6": 19, "B.10": 5, "10.37": 3, "UI.5": 20})

    def test_the_commands_are_text_for_the_owner_and_the_file_runs_nothing(self):
        js = (REPO / "ui/src/data/checks.js").read_text(encoding="utf-8")
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', re.sub(r"(?m)^//.*$", "", js))  # the words of the steps are data, not code
        self.assertNotRegex(code, r"\b(import|fetch|eval|Function|XMLHttpRequest|localStorage|sessionStorage|indexedDB|cookie|document|window)\b")
        # the one export besides the list is the ids
        self.assertEqual(re.findall(r"^export (?:const|function) (\w+)", js, re.M), ["CHECKS", "CHECK_IDS"])

    def test_the_b10_steps_the_panel_needs_are_in_the_notes_of_that_check(self):
        text = (REPO / "adapters/NOTES-layer10.md").read_text(encoding="utf-8")
        self.assertIn("UMWAYI_TELEMETRY_CAPTURE=/tmp/umwayi-capture.jsonl umwayi agent run reviewer", text)
        self.assertIn("UMWAYI_TELEMETRY_CAPTURE", (REPO / "umwayi/telemetry.py").read_text(encoding="utf-8"))


class PlantedFaultTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-checks-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for f in FILES:
            (self.root / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / f, self.root / f)

    def edit(self, rel, fn):
        p = self.root / rel
        p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")

    def found(self, fragment):
        got = problems(self.root)
        self.assertTrue(any(fragment in x for x in got), f"{fragment!r} not in {got}")

    def test_the_copy_is_clean_before_any_plant(self):
        self.assertEqual(problems(self.root), [])

    def test_a_command_changed_in_the_page(self):
        self.edit("ui/src/data/checks.js", lambda t: t.replace("umwayi schedule validate", "umwayi schedule validates", 1))
        self.found("is not word for word")

    def test_a_command_changed_in_the_notes(self):
        self.edit("adapters/NOTES-layer11.md", lambda t: t.replace("systemctl --user list-timers 'umwayi-*'", "systemctl --user list-timers", 2))
        self.found("is not word for word in adapters/NOTES-layer11.md")

    def test_a_step_text_changed_in_the_notes(self):
        self.edit("adapters/NOTES-layer10.md", lambda t: t.replace("Type one line with a word you can search for later", "Type one line", 1))
        self.found("check 10.21 step A4: the text is not word for word")

    def test_a_code_block_line_changed(self):
        self.edit("adapters/NOTES-layer10.md", lambda t: t.replace("command: claude\n", "command: claudes\n", 1))
        self.found("the code block is not word for word")

    def test_a_record_cell_changed(self):
        self.edit("adapters/NOTES-layer11.md", lambda t: t.replace("| the status code systemd shows with the kill switch on |", "| a code |", 1))
        self.found("the record cell is not word for word")

    def test_a_check_missing_or_out_of_order(self):
        self.edit("ui/src/data/checks.js", lambda t: t.replace('id: "10.37"', 'id: "10.99"', 1))
        self.found("in this order")
        self.found("check 10.99 is not in tasks.md")

    def test_a_check_id_that_is_not_in_tasks_md(self):
        self.edit(".kiro/specs/umwayi-os/tasks.md", lambda t: t.replace("11.6", "11.x"))
        self.found("check 11.6 is not in tasks.md")

    def test_a_heading_that_is_not_in_the_notes(self):
        self.edit("adapters/NOTES-layer12.md", lambda t: t.replace("## The owner's interface check (UI.5)", "## The interface check", 1))
        self.found("the heading")

    def test_a_check_with_no_steps_and_two_steps_with_one_id(self):
        self.edit("ui/src/data/checks.js", lambda t: t.replace('{ id: "10.31"', '{ id: "A3"', 0))
        self.edit("ui/src/data/checks.js", lambda t: re.sub(r'\{ id: "A4",', '{ id: "A3",', t, count=1))
        self.found("two steps with the same id")

    def test_a_notes_file_that_does_not_exist(self):
        self.edit("ui/src/data/checks.js", lambda t: t.replace("adapters/NOTES-layer11.md", "adapters/NOTES-layer99.md", 1))
        self.found("does not exist")

    def test_an_em_dash(self):
        self.edit("ui/src/data/checks.js", lambda t: t.replace("// The six checks", "// The six " + EM_DASH + " checks", 1))
        self.found("em dash")


if __name__ == "__main__":
    unittest.main()
