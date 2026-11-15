"""W58a: `umwayi rules validate [--rules PATH]`. Read only.

It loads the rules file with the very reader the gate uses (`rules.load_rules`, so the same size limit, the same regular file
check and the same strict parser) and says whether it loads and every rule is well formed. On the first problem it prints one
line with the line number of the rule (or of the YAML problem), the rule id when it has one, and the reader's own words.
It changes nothing in the rule language, the matchers, the starter rules or the gate, and writes nothing (no logbook entry).

Exit codes: 0 the file loads and every rule is well formed; 64 it does not (missing, unreadable, not YAML, or a rule that is
not well formed); 2 an unexpected error. Never 1, never 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from umwayi import miniyaml, rules
from umwayi.errors import UmwayiError

_YAML_LINE = re.compile(r"^rules\.yaml: line (\d+): ")
_RULE_ID = re.compile(r"^rule '([^']*)': ")


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


def rule_lines(text: str) -> dict:
    """{index of the rule (1 based): the line its list item starts on}. Only for text miniyaml accepts."""
    try:
        toks = miniyaml._tokenize(text)
    except miniyaml.YamlError:
        return {}
    out: dict = {}
    if not toks:
        return out
    top = toks[0][0]
    i = 0
    while i < len(toks):
        ind, t, _n = toks[i]
        kv = miniyaml._split_key(t) if ind == top and not miniyaml._is_item(t) else None
        i += 1
        if kv is None or kv[0] != "rules":
            continue
        idx, item_ind = 0, None
        while i < len(toks) and (toks[i][0] > top or (toks[i][0] == top and miniyaml._is_item(toks[i][1]))):
            jind, jt, jn = toks[i]
            if miniyaml._is_item(jt) and (item_ind is None or jind == item_ind):
                item_ind = jind
                idx += 1
                out[idx] = jn
            i += 1
    return out


def _top_line(text: str) -> int | None:
    """The line of the 'rules' key, or of the first line with content."""
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip() and not line.lstrip().startswith("#"):
            return n
    return None


def validate(path: Path) -> Result:
    shown = str(path)
    try:
        loaded = rules.load_rules(path)
    except UmwayiError as e:
        msg = str(e)
        text = None
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            text = None
        idx = getattr(e, "rule_index", None)
        m = _YAML_LINE.match(msg)
        if m:
            line = int(m.group(1))
        elif idx is not None and text is not None:
            line = rule_lines(text).get(idx)
        elif text is not None and (msg.startswith("rules.yaml: top level") or msg.startswith("rules.yaml: 'rules' must")):
            line = _top_line(text)
        else:
            line = None
        rid = None
        m2 = _RULE_ID.match(msg)
        if m2:
            rid = m2.group(1)
        elif idx is not None and text is not None:
            rid = _id_of(text, idx)
        where = f"line {line}" if line is not None else "line unknown"
        who = f"rule {rid}" if rid else (f"rule #{idx} (no id)" if idx is not None else "no rule")
        return Result(64, [f"no: {shown}: {where}: {who}: {msg}",
                           f"The rules file is not well formed, so every check answers Ask me first until it is fixed "
                           f"(exit 64). Nothing was changed."])
    return Result(0, [f"ok: {shown}: it loads and its {len(loaded)} rule(s) are well formed. Nothing was changed."])


def _id_of(text: str, idx: int):
    """The id of rule idx when the YAML gives it one that is plain text, else None. Read only for the message."""
    try:
        data = miniyaml.loads(text)
        item = data["rules"][idx - 1]
        rid = item.get("id") if isinstance(item, dict) else None
    except (miniyaml.YamlError, KeyError, IndexError, TypeError, AttributeError):
        return None
    return rid if isinstance(rid, str) and rules._ID.match(rid) else None
