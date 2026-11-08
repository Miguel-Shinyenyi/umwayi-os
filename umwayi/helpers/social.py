"""Layer 7: the social helper. It turns one local article into post drafts.

`umwayi social draft ARTICLE_FILE` takes these steps, each checked by the
rules and logged by the helper base:

  1. read_article   read the article file (read only) and build the post text
  2. write_draft    once per channel in umwayi.json "social_channels":
                    drafts/post-CHANNEL-NNNN.md

The post comes from one fixed template. There is no model call and no network.
Each post is short (at most 280 characters), plain text, has no hashtags and
no em dashes, and ends with a link line taken from the article front matter.
The social helper never posts. To publish a draft, the owner runs the layer 6
step `umwayi publish-draft`, which is Ask me first.

Article front matter (the first lines of the file):

    ---
    title: What I learned this week
    link: https://example.org/what-i-learned
    summary: One line about it (optional)
    ---
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from umwayi.config import load_config
from umwayi.errors import ConfigError, UmwayiError
from umwayi.helpers.base import Helper, Outcome, Result, run as run_helper
from umwayi.memory import is_private

MAX_POST = 280
MAX_ARTICLE_BYTES = 200_000
MAX_TITLE = 200
MAX_FIELD = 300
MIN_SUMMARY = 20  # a summary cut shorter than this is left out
LINK_LABEL = "Read more: "
_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?: (.*))?$")
_LINK = re.compile(r"^https://[A-Za-z0-9][A-Za-z0-9.-]*(:\d{1,5})?(/[^\s<>\"'`|#]*)?$")
_DASHES = re.compile("\\s*[\u2012\u2013\u2014\u2015]+\\s*")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_PROTECTED = {".git", ".umwayi"}


@dataclass(frozen=True)
class Article:
    title: str
    link: str
    summary: str  # from the front matter, else the first paragraph, may be empty


# ------------------------------------------------------------------ text


def plain(text: str) -> str:
    """One line of plain text: no markdown links, hashtags, em dashes or control characters."""
    s = _MD_LINK.sub(r"\1", text)
    s = _DASHES.sub(", ", s)
    s = s.replace("#", "")
    s = re.sub(r"[*`]", "", s)
    s = "".join(ch if ch.isprintable() else " " for ch in s)
    s = " ".join(s.split())
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",(\s*,)+", ",", s)
    return s.strip(" ,")


def shorten(text: str, room: int) -> str:
    """Cut text at a word boundary so it fits in room characters, with '...'. Empty if too little room."""
    if len(text) <= room:
        return text
    if room < MIN_SUMMARY:
        return ""
    cut = text[: room - 3]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    cut = cut.rstrip(" ,.;:")
    return cut + "..." if len(cut) >= MIN_SUMMARY - 3 else ""


def compose(title: str, summary: str, link: str) -> str:
    """The one fixed template."""
    parts = [title] + ([summary] if summary else []) + [LINK_LABEL + link]
    return "\n\n".join(parts) + "\n"


def build_post(article: Article) -> str:
    title = plain(article.title)
    if not title:
        raise UmwayiError("social: the title is empty after cleaning")
    summary = plain(article.summary)
    text = compose(title, summary, article.link)
    if len(text) > MAX_POST and summary:
        room = MAX_POST - len(compose(title, "", article.link)) - 2
        text = compose(title, shorten(summary, room), article.link)
    if len(text) > MAX_POST:
        raise UmwayiError(f"social: the title and the link are too long for a post of {MAX_POST} characters")
    check_post(text, article.link)
    return text


def check_post(text: str, link: str) -> None:
    """Fail closed: the post must be short, plain, without hashtags or em dashes, and end with the link."""
    if len(text) > MAX_POST:
        raise UmwayiError("social: the post is too long")
    if "#" in text:
        raise UmwayiError("social: the post has a hashtag")
    if any(ch in text for ch in "\u2012\u2013\u2014\u2015"):
        raise UmwayiError("social: the post has an em dash")
    if any(not (ch.isprintable() or ch == "\n") for ch in text):
        raise UmwayiError("social: the post is not plain text")
    if not text.endswith("\n" + LINK_LABEL + link + "\n"):
        raise UmwayiError("social: the post does not end with the link line")


# --------------------------------------------------------------- article


def parse_article(text: str) -> Article:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise UmwayiError("social: the article must start with front matter between two '---' lines")
    end = next((i for i in range(1, min(len(lines), 50)) if lines[i].strip() == "---"), None)
    if end is None:
        raise UmwayiError("social: the front matter has no closing '---' line in the first 50 lines")
    fields: dict = {}
    for i in range(1, end):
        line = lines[i]
        if not line.strip():
            continue
        m = _KEY.match(line)
        if not m:
            raise UmwayiError(f"social: front matter line {i + 1} must look like 'key: value'")
        key, value = m.group(1).lower(), (m.group(2) or "").strip()
        if key not in ("title", "link", "summary"):
            raise UmwayiError(f"social: front matter line {i + 1} has a key other than title, link and summary")
        if key in fields:
            raise UmwayiError(f"social: front matter line {i + 1} repeats a key")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].strip()
        if not value or len(value) > MAX_FIELD or not value.isprintable():
            raise UmwayiError(f"social: front matter line {i + 1} needs a short one line value")
        fields[key] = value
    if "title" not in fields:
        raise UmwayiError("social: the front matter needs a title")
    if "link" not in fields:
        raise UmwayiError("social: the front matter needs a link")
    if len(fields["title"]) > MAX_TITLE:
        raise UmwayiError(f"social: the title is longer than {MAX_TITLE} characters")
    if not _LINK.match(fields["link"]):
        raise UmwayiError("social: the link must be one https:// address with no spaces, quotes or '#'")
    summary = fields.get("summary") or first_paragraph(lines[end + 1:])
    return Article(fields["title"], fields["link"], summary)


def first_paragraph(lines: list) -> str:
    para: list = []
    for line in lines:
        s = line.strip()
        if not s:
            if para:
                break
            continue
        if s.startswith("#") and not para:
            continue  # a heading before the first paragraph
        para.append(s)
    return " ".join(para)


def resolve_article(root: Path, article: str, private_paths: tuple) -> tuple[Path, str]:
    """Check the path before anything is read. Refuse anything unsafe."""
    if not isinstance(article, str) or not article.strip():
        raise UmwayiError("social: an article file must be given")
    root_abs = Path(os.path.abspath(root))
    p = Path(article)
    if ".." in p.parts:
        raise UmwayiError("social: the article path must not contain '..'")
    full = Path(os.path.normpath(p if p.is_absolute() else root_abs / p))
    try:
        rel = full.relative_to(root_abs)
    except ValueError:
        raise UmwayiError("social: the article must be inside the root") from None
    if not rel.parts:
        raise UmwayiError("social: the article must be a file inside the root")
    if rel.parts[0].casefold() in _PROTECTED:
        raise UmwayiError("social: the article must not be in .git or .umwayi")
    cur = root_abs
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise UmwayiError("social: the article must not be a symbolic link, or inside a linked folder")
    rel_posix = rel.as_posix()
    if is_private(rel_posix, private_paths):
        raise UmwayiError("social: the article is a private path from umwayi.json")
    if not full.exists():
        raise UmwayiError("social: the article was not found")
    if not full.is_file():
        raise UmwayiError("social: the article must be a regular file")
    return full, rel_posix


def read_article(path: Path, rel: str) -> Outcome:
    try:
        if path.stat().st_size > MAX_ARTICLE_BYTES:
            raise UmwayiError(f"social: the article is larger than {MAX_ARTICLE_BYTES} bytes")
        data = path.read_bytes()
    except OSError:
        raise UmwayiError("social: the article cannot be read") from None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise UmwayiError("social: the article is not valid UTF-8 text") from None
    article = parse_article(text)
    post = build_post(article)
    return Outcome(
        added=f"read {rel} ({len(data)} bytes, SHA-256 {hashlib.sha256(data).hexdigest()}); "
        f"built a post of {len(post)} characters from the fixed template",
        not_done="The article was only read, nothing was changed. No model and no network were used.",
        value=(article, post),
    )


# ------------------------------------------------------------------- run


def draft(root: Path, article: str, today: str) -> Result:
    root = Path(root)
    config = load_config(root)  # no config means private paths unknown: refuse
    channels = config.social_channels
    if not channels:
        raise ConfigError("social: umwayi.json has no social_channels, so there is no channel to draft for")
    path, rel = resolve_article(root, article, config.private_paths)
    helper = Helper(root, "social", today)

    def body() -> list:
        _article, post = helper.step("read_article", lambda: read_article(path, rel)).value
        written = []
        for channel in channels:
            o = helper.step(
                "write_draft",
                lambda c=channel: helper.draft(f"post-{c}", post, f"a post draft for {c} from {rel}"),
                channel=channel,
            )
            written.append(o.value.rel)
        lines = [f"Wrote {w}" for w in written]
        lines += [
            "These are drafts. Nothing was posted.",
            f"To publish one, the owner runs: umwayi publish-draft {written[0]} (Ask me first).",
        ]
        return lines

    return run_helper(helper, body)
