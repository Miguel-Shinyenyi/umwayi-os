"""U1 step 3: `umwayi stories list` and `umwayi stories export`, read only.

The story files of docs/stories/ (docs/stories-in-the-gui.md) are data that a page in the GUI can show. These two commands read them and
print them; they write nothing, call nothing and open no network connection. `export` prints ONE JSON document, so a page can read it
through a script tag or a local request without reading the folder itself. The terminal stays the source of truth: the export carries no
power and no state, only the stories as written, with their built, partly or planned badge.

A file is checked for its STRUCTURE before it is printed: the exact keys, a built state, five scenes with a tone and the chip of that tone,
and an id equal to the file name. Anything else refuses the whole export (exit 64, the file name and one fixed problem, never text of the
file), so a page never shows half a folder. The deeper rules (every fixed word in the code the story names, the prose, the honesty scan)
are the tests of tools/stories.py; they run on every change to a story file.

Exit codes: 0 done (also when there are no stories), 64 a story file that is not well formed. Standard library only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from umwayi import fsutil
from umwayi.errors import ConfigError

FOLDER = ("docs", "stories")
MAX_BYTES = 64 * 1024
MAX_FILES = 200
KEYS = ("id", "title", "command", "prs", "built", "honesty", "analogy", "analogy_stops", "does_not", "owner_check", "words", "code", "scenes")
SCENE_KEYS = ("label", "chip", "tone", "caption")
CHIPS = {"yes": "Yes", "ask": "Ask me first", "no": "No", "info": "Info"}
BUILT = ("built", "partly", "planned")
_ID = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
NOTE = ("These are the stories as written in docs/stories. The terminal stays the source of truth: nothing here decides anything, and "
        "built, partly or planned is the state the story file states.")


class StoryError(ConfigError):
    """A story file is not well formed. Exit 64. The message names the file and one fixed problem, never text of the file."""


def _fail(name: str, why: str):
    raise StoryError(f"docs/stories/{name}: {why}")


def _structure(name: str, s) -> None:
    if not isinstance(s, dict) or tuple(s) != KEYS:
        _fail(name, "the keys are not the ones of the story file")
    if s["id"] != name[:-5] or not isinstance(s["id"], str) or not _ID.match(s["id"]):
        _fail(name, "the id is not the file name")
    if s["built"] not in BUILT:
        _fail(name, "built is not built, partly or planned")
    for k in ("title", "command", "honesty", "analogy", "analogy_stops"):
        if not isinstance(s[k], str) or not s[k].strip():
            _fail(name, f"{k} is empty")
    if not isinstance(s["prs"], list) or not all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in s["prs"]):
        _fail(name, "prs is not a list of numbers")
    for k in ("does_not", "owner_check", "words", "code"):
        if not isinstance(s[k], list) or not all(isinstance(x, str) and x.strip() for x in s[k]):
            _fail(name, f"{k} is not a list of lines")
    sc = s["scenes"]
    if not isinstance(sc, list) or len(sc) != 5:
        _fail(name, "there are not five scenes")
    for x in sc:
        if (not isinstance(x, dict) or tuple(x) != SCENE_KEYS or x["tone"] not in CHIPS or x["chip"] != CHIPS[x["tone"]]
                or not isinstance(x["label"], str) or not isinstance(x["caption"], str) or not x["label"].strip() or not x["caption"].strip()):
            _fail(name, "a scene has a tone, a chip or a text that is wrong")


def story_files(root) -> list:
    """The stories of `root`, sorted by id, each checked for structure. No folder is no stories. Raises StoryError."""
    folder = Path(root).joinpath(*FOLDER)
    if not folder.is_dir():
        return []
    files = sorted(p for p in folder.iterdir() if p.suffix == ".json")
    if len(files) > MAX_FILES:
        raise StoryError("docs/stories: too many files")
    out = []
    for p in files:
        try:
            data = json.loads(fsutil.read_regular(p, MAX_BYTES).decode("utf-8"))
        except (OSError, ValueError, fsutil.TooBig):
            _fail(p.name, "the file cannot be read as JSON")
        _structure(p.name, data)
        out.append(data)
    return out


def list_lines(stories: list) -> list:
    if not stories:
        return ["There are no stories in docs/stories."]
    width = max(len(s["id"]) for s in stories)
    lines = [f"{s['id']:<{width}}  {s['built']:<7}  {s['title']}" for s in stories]
    lines.append(f"{len(stories)} stories. Show one in a page with: umwayi stories export")
    return lines


def export_document(stories: list) -> str:
    """One JSON document: the note, the count and the stories as written."""
    return json.dumps({"note": NOTE, "count": len(stories), "stories": stories}, indent=2, ensure_ascii=False) + "\n"
