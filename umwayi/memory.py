"""Layer 1: memory loader.

Reads master context, projects and journal files into one context bundle
for an AI helper. Private paths from the config are never included, and
their names are never reported (only a count).
"""

from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from umwayi.config import Config
from umwayi.errors import UmwayiError

SECTIONS = ("master", "projects", "journal")
_SUFFIXES = {".md", ".txt"}


@dataclass(frozen=True)
class Entry:
    section: str
    path: str  # posix path relative to the root
    text: str


@dataclass
class Bundle:
    entries: list[Entry] = field(default_factory=list)
    excluded_count: int = 0
    skipped_count: int = 0

    def to_dict(self) -> dict:
        return {
            "entries": [
                {"section": e.section, "path": e.path, "text": e.text} for e in self.entries
            ],
            "excluded_count": self.excluded_count,
            "skipped_count": self.skipped_count,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def render(self) -> str:
        out = ["# umwayi context bundle", ""]
        for section in SECTIONS:
            items = [e for e in self.entries if e.section == section]
            out.append(f"## {section}")
            out.append("")
            if not items:
                out.append("(none)")
                out.append("")
            for e in items:
                out.append(f"### {e.path}")
                out.append("")
                out.append(e.text.rstrip("\n"))
                out.append("")
        out.append(
            f"(private files left out: {self.excluded_count}, "
            f"unreadable files skipped: {self.skipped_count})"
        )
        return "\n".join(out) + "\n"


def is_private(rel_path: str, private_paths: tuple[str, ...]) -> bool:
    """True if rel_path, or any parent folder of it, matches a private entry.

    Matching is case-insensitive. An entry matches by equality or as a glob
    (where '*' also crosses folders, which errs on the side of hiding more).
    """
    parts = rel_path.casefold().split("/")
    prefixes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    for entry in private_paths:
        e = entry.casefold()
        for p in prefixes:
            if p == e or fnmatch.fnmatchcase(p, e):
                return True
    return False


def _read_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def load_bundle(config: Config) -> Bundle:
    root = config.root
    mem = root / config.memory_dir
    try:
        real_root = root.resolve()
        real_mem = mem.resolve()
        real_mem.relative_to(real_root)
    except (OSError, ValueError):
        raise UmwayiError("memory: memory_dir must be inside the root") from None
    if mem.is_symlink() or not mem.is_dir():
        raise UmwayiError("memory: memory_dir is not a folder")

    bundle = Bundle()

    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    def consider(path: Path, section: str) -> None:
        r = rel(path)
        if is_private(r, config.private_paths):
            bundle.excluded_count += 1
            return
        if path.is_symlink() or path.name.startswith(".") or path.suffix.lower() not in _SUFFIXES:
            if path.suffix.lower() in _SUFFIXES and not path.name.startswith("."):
                bundle.skipped_count += 1
            return
        text = _read_text(path)
        if text is None:
            bundle.skipped_count += 1
            return
        bundle.entries.append(Entry(section=section, path=r, text=text))

    # master context
    master = mem / "master.md"
    if master.exists() or master.is_symlink():
        consider(master, "master")

    # projects and journal
    for section in ("projects", "journal"):
        folder = mem / section
        if folder.is_symlink() or not folder.is_dir():
            continue
        if is_private(rel(folder), config.private_paths):
            # count files hidden by a private folder, without naming them
            for _d, _dirs, files in os.walk(folder, followlinks=False):
                bundle.excluded_count += len(files)
            continue
        collected: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
            d = Path(dirpath)
            keep = []
            for name in sorted(dirnames):
                sub = d / name
                if sub.is_symlink() or name.startswith("."):
                    continue
                if is_private(rel(sub), config.private_paths):
                    for _d, _dirs, files in os.walk(sub, followlinks=False):
                        bundle.excluded_count += len(files)
                    continue
                keep.append(name)
            dirnames[:] = keep
            for name in sorted(filenames):
                collected.append(d / name)
        for path in sorted(collected, key=rel):
            consider(path, section)

    return bundle
