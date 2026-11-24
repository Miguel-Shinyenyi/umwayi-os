"""The rules of a story file (docs/stories/ID.json), shared by the test of the stories and the script writer of the videos (L8).

`problems(story)` is the list of everything wrong with one story dict: the exact keys, five scenes with a tone and a chip, a built state, every
fixed word present in the code the story names, prose of at least 100 words, no em dash and no overclaim (the honesty scan of
tools/pr_story.py). Standard library only. Nothing here reads a file but the stories and the code files they name.
"""
import json
import re
from pathlib import Path

from tools import pr_story

REPO = Path(__file__).resolve().parents[1]
FOLDER = REPO / "docs" / "stories"
KEYS = ("id", "title", "command", "prs", "built", "honesty", "analogy", "analogy_stops", "does_not", "owner_check", "words", "code", "scenes")
SCENE_KEYS = ("label", "chip", "tone", "caption")
TONES = ("yes", "ask", "no", "info")
CHIPS = {"yes": "Yes", "ask": "Ask me first", "no": "No", "info": "Info"}
BUILT = ("built", "partly", "planned")
MIN_WORDS = 100


def prose(s):
    parts = [s["title"], s["honesty"], s["analogy"], s["analogy_stops"], *s["does_not"], *s["owner_check"]]
    for sc in s["scenes"]:
        parts += [sc["label"], sc["caption"]]
    return "\n".join(parts)


def problems(s, root=REPO):
    """Every rule, as a list of messages for one story dict. Empty means the story is good."""
    out = []
    if tuple(s) != KEYS:
        return [f"the keys are not {', '.join(KEYS)} in that order"]
    if not isinstance(s["id"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", s["id"]):
        out.append("the id is not a plain lower case word")
    if not isinstance(s["prs"], list) or not s["prs"] or not all(isinstance(n, int) and n > 0 for n in s["prs"]):
        out.append("prs is not a list of pull request numbers")
    if s["built"] not in BUILT:
        out.append("built is not built, partly or planned")
    for k in ("title", "command", "honesty", "analogy", "analogy_stops"):
        if not isinstance(s[k], str) or not s[k].strip():
            out.append(f"{k} is empty")
    for k in ("does_not", "owner_check", "words", "code"):
        if not isinstance(s[k], list) or not s[k] or not all(isinstance(x, str) and x.strip() for x in s[k]):
            out.append(f"{k} is not a list of lines")
    sc = s["scenes"]
    if not isinstance(sc, list) or len(sc) != 5:
        out.append("there are not five scenes")
    else:
        for i, x in enumerate(sc, 1):
            if not isinstance(x, dict) or tuple(x) != SCENE_KEYS:
                out.append(f"scene {i} does not have {', '.join(SCENE_KEYS)}")
            elif x["tone"] not in TONES or x["chip"] != CHIPS[x["tone"]] or not x["label"].strip() or not x["caption"].strip():
                out.append(f"scene {i} has a tone, a chip or a text that is wrong")
    if out:
        return out
    code = []
    for rel in s["code"]:
        p = (root / rel)
        if not (p.is_file() and p.resolve().is_relative_to(root.resolve())):
            out.append(f"the code file {rel} does not exist in the repository")
        else:
            code.append(p.read_text(encoding="utf-8"))
    for w in s["words"]:
        if not any(w in text for text in code):
            out.append(f"the word {w} is not in the code the story names")
    text = prose(s)
    if len(text.split()) < MIN_WORDS:
        out.append(f"the prose has {len(text.split())} words, under {MIN_WORDS}")
    if "\u2014" in json.dumps(s, ensure_ascii=False):
        out.append("there is an em dash")
    fails, _ = pr_story.check("pull_request", text)
    out += [f"honesty: {f}" for f in fails]
    if s["built"] != "built" and not re.search(r"(?i)partly|not (yet )?(built|called)|nothing calls|planned", s["honesty"]):
        out.append("a story that is not fully built must say so in its honesty line")
    return out


def load_all(folder=FOLDER):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(folder).glob("*.json"))}


