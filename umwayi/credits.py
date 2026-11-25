"""M4 f, the first part: the credit reading, a number and a date in `credits.yaml`, shown in `umwayi budget status`.

The Muse CLI shows no credit balance. With the owner's permission, Claude in Chrome reads the billing page ("Free credits in use") and the
figure goes into `credits.yaml` of the root, ROUNDED, with the date of the read, and nothing else: no card, no account, no page text.

    version: 1
    credits:
      muse:                 # a provider of units.yaml
        left_uu: 14000      # whole UU left when it was read, rounded down by the person who wrote it
        read: 2026-11-25    # the day of the read

A reading older than `STALE_DAYS` is shown as stale, never as current. Billing can lag by up to an hour, so a reading says what the page said,
not what is true now. The spend of the runs since the read is NOT counted per provider yet, and the line says so. This module reads the file
and writes nothing; no command starts, stops or refuses anything by it. The parser is strict: a problem has a line number and never the text.
"""
from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from umwayi import miniyaml, units
from umwayi.errors import ConfigError

FILE_NAME = "credits.yaml"
MAX_BYTES = 16 * 1024
STALE_DAYS = 2
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


@dataclass(frozen=True)
class Reading:
    left_uu: int
    read: str  # YYYY-MM-DD


class CreditsError(ConfigError):
    """credits.yaml is malformed. The message has a line number or a key name, never the text of the file."""


def parse(text: str) -> dict:
    """name -> Reading of a credits.yaml text. Raises CreditsError for anything it does not expect."""
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError:
        raise CreditsError(f"{FILE_NAME}: the file is not valid YAML of the shape it expects") from None
    if not isinstance(data, dict) or set(data) != {"version", "credits"} or data["version"] != 1 or isinstance(data["version"], bool):
        raise CreditsError(f"{FILE_NAME}: the top level is exactly version: 1 and credits")
    raw = data["credits"]
    if not isinstance(raw, dict):
        raise CreditsError(f"{FILE_NAME}: credits must be a mapping of provider names")
    out = {}
    for name, item in raw.items():
        if not (isinstance(name, str) and _NAME.match(name)):
            raise CreditsError(f"{FILE_NAME}: a provider name is a lowercase letter, then lowercase letters, digits and '-'")
        if not isinstance(item, dict) or set(item) != {"left_uu", "read"}:
            raise CreditsError(f"{FILE_NAME}: {name} has exactly left_uu and read, and nothing else")
        left, when = item["left_uu"], item["read"]
        if isinstance(left, bool) or not isinstance(left, int) or not 0 <= left <= units.MAX_NUMBER:
            raise CreditsError(f"{FILE_NAME}: {name}.left_uu is a whole number of UU")
        if not units._real_date(when):
            raise CreditsError(f"{FILE_NAME}: {name}.read is a real date YYYY-MM-DD")
        out[name] = Reading(left, when)
    return out


def read(root) -> dict:
    """The readings of `root`/credits.yaml, or {} when there is none. A link, a folder or a big file is a CreditsError."""
    path = Path(root) / FILE_NAME
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return {}
    except OSError:
        raise CreditsError(f"{FILE_NAME} cannot be read") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
        raise CreditsError(f"{FILE_NAME} must be a regular file of at most {MAX_BYTES} bytes")
    try:
        return parse(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        raise CreditsError(f"{FILE_NAME} cannot be read as UTF-8") from None


def age_days(reading: Reading, today: str) -> int:
    return (date.fromisoformat(today) - date.fromisoformat(reading.read)).days


def is_stale(reading: Reading, today: str) -> bool:
    """True when the reading is older than STALE_DAYS, or dated in the future (a clock or a typo: not trusted)."""
    age = age_days(reading, today)
    return age > STALE_DAYS or age < 0


def lines(u, readings: dict, today: str) -> list:
    """The `umwayi budget status` lines of the readings. A provider that units.yaml does not name is said so, not hidden."""
    out = []
    for name, r in sorted(readings.items()):
        age = age_days(r, today)
        if is_stale(r, today):
            state = "STALE, not current" + (" (dated in the future)" if age < 0 else "")
        else:
            state = f"{age} day(s) old"
        known = "" if name in u.providers else "; this provider is not in units.yaml"
        out.append(f"credits {name}: {r.left_uu} UU left when read on {r.read} ({state}); billing can lag by up to an hour, and the spend "
                   f"of runs since the read is not counted per provider yet{known}")
    return out
