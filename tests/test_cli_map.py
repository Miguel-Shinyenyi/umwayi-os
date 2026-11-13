"""W2: the command map page cannot go stale.

The data file ui/src/data/cli-map.json is written from the real argparse tree by ui/tools/cli_map.py. These tests fail when:
- a command or group of the real command line is missing from the data file (or the file lists one that does not exist),
- the data file is not what the script would write now,
- the built page ui/dist/cli-map.html does not list every command, or is not the page that was built, or breaks the page rules
  (a script, a request, a link, a policy that is not default-src 'none').
Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import re
import sys
import unittest
from html import unescape
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from umwayi.cli import build_parser  # noqa: E402

_spec = importlib.util.spec_from_file_location("cli_map_tool", REPO / "ui" / "tools" / "cli_map.py")
cli_map = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli_map)

DATA = REPO / "ui" / "src" / "data" / "cli-map.json"
PAGE = REPO / "ui" / "dist" / "cli-map.html"
BUILD = REPO / "ui" / "dist" / "build.json"
EM_DASH = "\u2014"


def real_paths(parser: argparse.ArgumentParser, prefix: tuple = ()) -> dict:
    """Every command path of the parser that `--help` shows, read on its own (not through the script): path -> has children."""
    found = {}
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        shown = {c.dest for c in action._choices_actions if c.help != argparse.SUPPRESS}
        for name, sub in action.choices.items():
            hidden = name not in shown and any(c.dest == name for c in action._choices_actions)
            if hidden:
                continue
            path = prefix + (name,)
            below = real_paths(sub, path)
            found[path] = bool(below)
            found.update(below)
    return found


def data_paths(nodes: list) -> dict:
    found = {}
    for n in nodes:
        found[tuple(n["path"])] = bool(n["children"])
        found.update(data_paths(n["children"]))
    return found


def problems_in_data(data: dict, parser: argparse.ArgumentParser) -> list:
    real, have = real_paths(parser), data_paths(data["children"])
    out = []
    for path in sorted(set(real) - set(have)):
        out.append(f"missing from ui/src/data/cli-map.json: {' '.join(path)}")
    for path in sorted(set(have) - set(real)):
        out.append(f"in ui/src/data/cli-map.json but not in the command line: {' '.join(path)}")
    for path in sorted(set(real) & set(have)):
        if real[path] != have[path]:
            out.append(f"group or command differs: {' '.join(path)}")
    return out


def problems_in_page(html: str, data: dict) -> list:
    out = []
    paths = data_paths(data["children"])
    seen = {tuple(unescape(m).split(" ")) for m in re.findall(r'<li data-path="([^"]*)"', html)}
    for path in sorted(set(paths) - seen):
        out.append(f"missing from ui/dist/cli-map.html: {' '.join(path)}")
    if re.search(r"<script|<link|<img|<iframe|<form|<input|<object|<embed|\bsrc\s*=|\bhref\s*=|@import|url\(|fetch\(|XMLHttpRequest", html, re.I):
        out.append("ui/dist/cli-map.html loads, links or sends something")
    m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]*)"', html)
    styles = re.findall(r"<style>(.*?)</style>", html, re.S)
    if not m or len(styles) != 1:
        out.append("ui/dist/cli-map.html needs one policy and one style element")
    else:
        want = "sha256-" + base64.b64encode(hashlib.sha256(styles[0].encode("utf-8")).digest()).decode("ascii")
        parts = [p.strip() for p in m.group(1).split(";")]
        if parts != ["default-src 'none'", f"style-src '{want}'", "base-uri 'none'", "form-action 'none'"]:
            out.append("ui/dist/cli-map.html: the policy is not the closed one for this style")
    if EM_DASH in html:
        out.append("ui/dist/cli-map.html has an em dash")
    for node in (n for n in _flat(data["children"]) if not n["line"]):
        if "no help line yet" not in html:
            out.append(f"{' '.join(node['path'])} has no help line and the page does not say so")
    return out


def _flat(nodes: list) -> list:
    out = []
    for n in nodes:
        out.append(n)
        out += _flat(n["children"])
    return out


class FirstSentenceTests(unittest.TestCase):
    def test_cuts_at_a_semicolon_or_full_stop(self):
        self.assertEqual(cli_map.first_sentence("check a file; exit 0 or 2"), "check a file")
        self.assertEqual(cli_map.first_sentence("check a file. Then more"), "check a file")

    def test_keeps_a_stop_inside_brackets_or_a_name(self):
        self.assertEqual(cli_map.first_sentence("sign in (a.b; c) now; more"), "sign in (a.b; c) now")
        self.assertEqual(cli_map.first_sentence("write queue.md out"), "write queue.md out")

    def test_no_help_gives_none(self):
        self.assertIsNone(cli_map.first_sentence(None))
        self.assertIsNone(cli_map.first_sentence("   "))


class DataFileTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(DATA.read_text(encoding="utf-8"))
        self.parser = build_parser()

    def test_every_command_and_group_is_in_the_data_file_and_nothing_else(self):
        self.assertEqual(problems_in_data(self.data, self.parser), [])

    def test_the_file_is_what_the_script_writes_now(self):
        self.assertEqual(DATA.read_text(encoding="utf-8"), cli_map.render(cli_map.collect()),
                         "run: python ui/tools/cli_map.py, then node build.mjs in ui")

    def test_the_file_has_no_em_dash(self):
        self.assertNotIn(EM_DASH, DATA.read_text(encoding="utf-8"))

    def test_a_removed_command_is_found(self):
        data = copy.deepcopy(self.data)
        data["children"][1]["children"].pop(0)  # queue list
        self.assertEqual(problems_in_data(data, self.parser), ["missing from ui/src/data/cli-map.json: queue list"])

    def test_a_removed_group_is_found(self):
        data = copy.deepcopy(self.data)
        gone = data["children"].pop(0)  # memory, with its command
        found = problems_in_data(data, self.parser)
        self.assertIn(f"missing from ui/src/data/cli-map.json: {gone['name']}", found)
        self.assertIn(f"missing from ui/src/data/cli-map.json: {gone['name']} bundle", found)

    def test_a_command_that_does_not_exist_is_found(self):
        data = copy.deepcopy(self.data)
        data["children"].append({"name": "ghost", "path": ["ghost"], "help": "x", "line": "x", "children": []})
        self.assertEqual(problems_in_data(data, self.parser), ["in ui/src/data/cli-map.json but not in the command line: ghost"])

    def test_a_command_added_to_the_parser_is_found(self):
        parser = build_parser()
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        sub.add_parser("brand-new", help="a new command")
        self.assertEqual(problems_in_data(self.data, parser), ["missing from ui/src/data/cli-map.json: brand-new"])

    def test_a_command_with_no_help_is_listed_with_no_line(self):
        parser = build_parser()
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        sub.add_parser("quiet")
        found = {n["name"]: n for n in cli_map._walk(parser, [])}
        self.assertIn("quiet", found)
        self.assertIsNone(found["quiet"]["line"])


class PageTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(DATA.read_text(encoding="utf-8"))
        self.html = PAGE.read_text(encoding="utf-8")

    def test_the_page_lists_every_command_and_follows_the_page_rules(self):
        self.assertEqual(problems_in_page(self.html, self.data), [])

    def test_the_page_is_the_one_that_was_built(self):
        build = json.loads(BUILD.read_text(encoding="utf-8"))
        self.assertEqual(build.get("cliMapPage"), hashlib.sha256(PAGE.read_bytes()).hexdigest(),
                         "ui/dist/cli-map.html was edited by hand or not rebuilt: run node build.mjs in ui")
        self.assertEqual(build["files"]["src/data/cli-map.json"], hashlib.sha256(DATA.read_bytes()).hexdigest())

    def test_a_page_without_a_command_is_found(self):
        html = re.sub(r'<li data-path="queue list">.*?</li>', "", self.html, count=1, flags=re.S)
        self.assertEqual(problems_in_page(html, self.data), ["missing from ui/dist/cli-map.html: queue list"])

    def test_a_script_or_a_link_in_the_page_is_found(self):
        self.assertTrue(problems_in_page(self.html.replace("</body>", "<script>1</script></body>"), self.data))
        self.assertTrue(problems_in_page(self.html.replace("</body>", '<a href="x">x</a></body>'), self.data))

    def test_a_looser_policy_is_found(self):
        html = self.html.replace("default-src 'none'", "default-src 'none'; connect-src 'self'")
        self.assertTrue(problems_in_page(html, self.data))


if __name__ == "__main__":
    unittest.main()
