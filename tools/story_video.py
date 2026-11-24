"""L8, the script part: turn a story file (docs/stories/ID.json) into the SCRIPT of a concept video, and a manifest line for the video pack.

The script is the plain text a renderer reads: the title, the source story and the real code, "Made with AI" declared on every frame, the
honesty line, five scenes of four seconds each with a chip and a caption, the tones, the cost and who posts. It follows the format of the
scripts in the owner's video pack (for example the fuel gauge). This module does NOT render: rendering needs Pillow, numpy, ffmpeg and fonts
that are not dependencies of this repository, and it stays in the video pack. The words on screen are the words of the story file, which a
test has already checked against the code (tools/stories.py).

    python -m tools.story_video ID [--out FILE] [--filename NAME.mp4]     the script (stdout, or a new file)
    python -m tools.story_video ID --manifest [--filename NAME.mp4]       the manifest line

A story is refused (exit 2, one fixed reason) when it breaks any rule of tools/stories.py, or when the words ON SCREEN (the chips, labels
and captions of the scenes) say enforced, sandboxed or confined: the owner's rule is that no video says them until one real enforced run
(W40) has finished a goal. A story that is not fully built carries "Not fully built" in the footer. Cost is 0 units for a local render; a
paid render needs the video budget (L9), which is not built, so this tool never writes a figure above 0.

Exit codes: 0 done, 2 refused (the reason is printed), 64 usage or an unknown story id. It writes only to a new file named by --out and
never overwrites one. Standard library only; it starts no program and opens no network connection.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from tools import stories

SCENE_SECONDS = 4
BANNED = re.compile(r"(?i)\b(enforced|sandboxed|confined)\b")
TONE_LINE = ("Tones (D major pentatonic: D4 E4 F#4 A4 B4 D5): one ping at each scene start (D4, E4, F#4, A4, B4 in order); "
             "B4 when the chip says ask; a rising D4 F#4 A4 D5 when the chip says yes; no other tone for the other chips.")
POSTING = "Posting is the owner's act. The owner approves the video before it is posted outside the PR."


class Refused(Exception):
    """The story cannot become a script. The message is one fixed reason, never text of the story."""


def check(story: dict) -> None:
    bad = stories.problems(story)
    if bad:
        raise Refused("the story breaks a rule of tools/stories.py (" + bad[0].split(":")[0][:60] + ")")
    for sc in story["scenes"]:
        for field in ("label", "chip", "caption"):
            if BANNED.search(sc[field]):
                raise Refused("a scene says enforced, sandboxed or confined: no video says that before a real enforced run (W40)")


def default_filename(story: dict) -> str:
    return f"umwayi-story-{story['id']}.mp4"


def script(story: dict, filename: str | None = None) -> str:
    """The script text of one story. Raises Refused. Pure: no file is read or written here."""
    check(story)
    name = filename or default_filename(story)
    prs = " and ".join(f"PR {n}" for n in story["prs"])
    state = {"built": "Built", "partly": "Not fully built: partly built", "planned": "Not fully built: planned"}[story["built"]]
    n = len(story["scenes"])
    lines = [
        f"SCRIPT: {name} (9:16, 1080x1920, {n * SCENE_SECONDS} s, {n} scenes of {SCENE_SECONDS} s, 30 fps)",
        f"Source story: {prs}, {story['title']}. Real code: {', '.join(story['code'])}. Command: {story['command']}.",
        "Numbers on screen are examples, not the owner's real figures. The words on screen are the words the code prints: "
        + ", ".join(story["words"]) + ".",
        'AI use is declared on screen in every frame ("Made with AI"). Honesty: ' + story["honesty"],
        "Video cost: 0 units (local render, no paid credits). The video budget (L9) is not built, so no paid render is planned here.",
        "",
    ]
    for i, sc in enumerate(story["scenes"]):
        a, b = i * SCENE_SECONDS, (i + 1) * SCENE_SECONDS
        chip = sc["tone"] if sc["tone"] == "info" else f"{sc['tone']}: {sc['chip']}"
        lines.append(f"Scene {i + 1} ({a} to {b} s): {sc['label']}. Chip: {chip}. Caption: {sc['caption']}")
    lines += ["", TONE_LINE, f"Footer: Made with AI. Cooperative today. {state}. {prs}.", POSTING]
    return "\n".join(lines) + "\n"


def manifest_line(story: dict, filename: str | None = None) -> str:
    """One row for the manifest of the video pack: the file, the story, the PRs, the state, the cost and that it is not posted."""
    check(story)
    name = filename or default_filename(story)
    prs = ", ".join(str(n) for n in story["prs"])
    return f"| {name} | docs/stories/{story['id']}.json | {prs} | {story['built']} | 0 units | made with AI | posted: no |"


def main(argv) -> int:
    args = list(argv)
    out = filename = None
    manifest = False
    ident = None
    while args:
        a = args.pop(0)
        if a == "--out" and args:
            out = args.pop(0)
        elif a == "--filename" and args:
            filename = args.pop(0)
        elif a == "--manifest":
            manifest = True
        elif not a.startswith("-") and ident is None:
            ident = a
        else:
            print("usage: python -m tools.story_video ID [--out FILE] [--filename NAME.mp4] [--manifest]", file=sys.stderr)
            return 64
    if ident is None or filename is not None and not re.fullmatch(r"[A-Za-z0-9._-]{1,80}\.mp4", filename):
        print("usage: python -m tools.story_video ID [--out FILE] [--filename NAME.mp4] [--manifest]", file=sys.stderr)
        return 64
    found = stories.load_all()
    if ident not in found:
        print(f"story_video: there is no story {ident!r}; the stories are: {', '.join(sorted(found))}", file=sys.stderr)
        return 64
    try:
        text = manifest_line(found[ident], filename) + "\n" if manifest else script(found[ident], filename)
    except Refused as e:
        print(f"story_video: refused: {e}", file=sys.stderr)
        return 2
    if out is None:
        sys.stdout.write(text)
        return 0
    path = Path(out)
    try:
        with open(path, "x", encoding="utf-8") as f:  # a new file only: never overwritten
            f.write(text)
    except FileExistsError:
        print("story_video: that file already exists; it is never overwritten", file=sys.stderr)
        return 64
    except OSError:
        print("story_video: the file cannot be written", file=sys.stderr)
        return 64
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
