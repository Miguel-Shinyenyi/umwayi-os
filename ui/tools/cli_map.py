"""Writes ui/src/data/cli-map.json from the real umwayi command line (W2).

It walks the argparse tree that `umwayi --help` shows: every group (a command that has commands under it) and every command,
with the help line argparse holds for it. The page ui/dist/cli-map.html is built from that file, so the page cannot list a
command that does not exist, and tests/test_cli_map.py fails when a command or group is missing from the file.

Run it from the repo root:

    python ui/tools/cli_map.py            write the data file
    python ui/tools/cli_map.py --check    exit 0 if the file is current, 2 if not, and write nothing

Standard library only. It reads the parser and changes nothing in umwayi/. It makes no request and starts no program. Only this
script reads the parser; the page and the Node code of ui/ import nothing from umwayi.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ui" / "src" / "data" / "cli-map.json"
SCHEMA = 1


def first_sentence(text: str | None) -> str | None:
    """The help line cut at its first semicolon or full stop, so one line stays one line. None when there is no help."""
    if text is None:
        return None
    text = " ".join(text.split())
    if not text:
        return None
    cut = len(text)
    depth = 0  # a semicolon or full stop inside brackets does not end the sentence
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and (ch == ";" or (ch == "." and (i + 1 == len(text) or text[i + 1] == " "))):
            cut = i
            break
    return text[:cut].rstrip(" ,:") or None


def _walk(parser: argparse.ArgumentParser, path: list) -> list:
    nodes = []
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        helps = {c.dest: c.help for c in action._choices_actions}
        for name, sub in action.choices.items():
            help_text = helps.get(name)
            if help_text == argparse.SUPPRESS:
                continue  # `umwayi --help` does not show it, so the map does not either
            node = {
                "name": name,
                "path": path + [name],
                "help": help_text,
                "line": first_sentence(help_text),
                "children": _walk(sub, path + [name]),
            }
            nodes.append(node)
    return nodes


def collect() -> dict:
    sys.path.insert(0, str(ROOT))
    from umwayi.cli import build_parser

    parser = build_parser()
    return {
        "schema": SCHEMA,
        "program": parser.prog,
        "description": parser.description,
        "children": _walk(parser, []),
    }


def render(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write ui/src/data/cli-map.json from the real command line.")
    ap.add_argument("--check", action="store_true", help="exit 2 if the data file is not current; write nothing")
    args = ap.parse_args(argv)
    text = render(collect())
    if args.check:
        have = DATA.read_text(encoding="utf-8") if DATA.is_file() else None
        if have == text:
            print("ui/src/data/cli-map.json is current")
            return 0
        print("ui/src/data/cli-map.json is not current: run python ui/tools/cli_map.py")
        return 2
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(text, encoding="utf-8")
    print(f"wrote {DATA.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
