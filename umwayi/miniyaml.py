"""A strict reader for the small YAML subset used by rules.yaml.

Supported: block mappings, block lists, inline lists of scalars, quoted and
plain strings, integers, floats, true, false, null, and comments.

Rejected (as errors): tabs, anchors, aliases, tags, block scalars, flow
mappings, duplicate keys, nested inline lists and bad indentation.

Note: 'yes' and 'no' stay strings, they are NOT booleans. Error messages
carry a line number but never the text of the line.
"""

from __future__ import annotations

import re
from typing import Any


class YamlError(ValueError):
    pass


_INT = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?\d+\.\d+$")
_BAD_START = set("|>&*!%@`{}")


def _strip_comment(s: str) -> str:
    quote = None
    for i, ch in enumerate(s):
        if quote:
            if ch == "\\" and quote == '"':
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'" and (i == 0 or s[i - 1] in " [,:-"):
            quote = ch
        elif ch == "#" and (i == 0 or s[i - 1] in " "):
            return s[:i].rstrip()
    return s.rstrip()


def _tokenize(text: str) -> list[tuple[int, str, int]]:
    lines: list[tuple[int, str, int]] = []
    for n, raw in enumerate(text.splitlines(), 1):
        lead = raw[: len(raw) - len(raw.lstrip())]
        if "\t" in lead:
            raise YamlError(f"line {n}: tabs are not allowed")
        s = _strip_comment(raw)
        if not s.strip():
            continue
        if s.strip() == "---" and not lines:
            continue
        lines.append((len(s) - len(s.lstrip(" ")), s.strip(), n))
    return lines


def _is_item(t: str) -> bool:
    return t == "-" or t.startswith("- ")


def _split_key(s: str) -> tuple[str, str] | None:
    if s[0] in "\"'":
        q = s[0]
        i = 1
        while i < len(s):
            if s[i] == "\\" and q == '"':
                i += 2
                continue
            if s[i] == q:
                break
            i += 1
        else:
            return None
        rest = s[i + 1 :]
        if rest.startswith(":") and (len(rest) == 1 or rest[1] == " "):
            return _scalar_quoted(s[: i + 1], 0), rest[1:].strip()
        return None
    for i, ch in enumerate(s):
        if ch == ":" and (i + 1 == len(s) or s[i + 1] == " "):
            key = s[:i].strip()
            if not key or key[0] in _BAD_START or key[0] in "[":
                return None
            return key, s[i + 1 :].strip()
    return None


def _scalar_quoted(v: str, line: int) -> str:
    if len(v) < 2 or v[-1] != v[0]:
        raise YamlError(f"line {line}: unterminated quoted string")
    inner = v[1:-1]
    if v[0] == "'":
        if "'" in inner.replace("''", ""):
            raise YamlError(f"line {line}: bad quote in string")
        return inner.replace("''", "'")
    out = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\":
            i += 1
            if i >= len(inner):
                raise YamlError(f"line {line}: bad escape")
            esc = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/"}.get(inner[i])
            if esc is None:
                raise YamlError(f"line {line}: unsupported escape")
            out.append(esc)
        elif ch == '"':
            raise YamlError(f"line {line}: bad quote in string")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _split_inline(inner: str, line: int) -> list[str]:
    parts, cur, quote = [], [], None
    i = 0
    while i < len(inner):
        ch = inner[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(inner):
                i += 1
                cur.append(inner[i])
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch == ",":
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    if quote:
        raise YamlError(f"line {line}: unterminated quoted string")
    parts.append("".join(cur).strip())
    return parts


def _scalar(v: str, line: int, in_list: bool = False) -> Any:
    if not v:
        raise YamlError(f"line {line}: empty value")
    c = v[0]
    if c in "\"'":
        return _scalar_quoted(v, line)
    if c == "[":
        if in_list:
            raise YamlError(f"line {line}: nested lists are not supported")
        if v[-1] != "]":
            raise YamlError(f"line {line}: unterminated inline list")
        inner = v[1:-1].strip()
        if not inner:
            return []
        items = _split_inline(inner, line)
        if items and items[-1] == "":
            items.pop()  # trailing comma
        return [_scalar(i, line, in_list=True) for i in items]
    if c in _BAD_START:
        raise YamlError(f"line {line}: unsupported YAML syntax")
    if c == "-" and v.startswith("- "):
        raise YamlError(f"line {line}: nested lists are not supported")
    if ": " in v or v.endswith(":"):
        raise YamlError(f"line {line}: unexpected ':' in value")
    if v in ("true", "false"):
        return v == "true"
    if v in ("null", "~"):
        return None
    if _INT.match(v):
        return int(v)
    if _FLOAT.match(v):
        return float(v)
    return v


class _Parser:
    def __init__(self, lines: list[tuple[int, str, int]]):
        self.lines = lines
        self.pos = 0

    def _more(self) -> bool:
        return self.pos < len(self.lines)

    def node(self, indent: int) -> Any:
        ind, text, n = self.lines[self.pos]
        if ind != indent:
            raise YamlError(f"line {n}: bad indentation")
        return self.list_(indent) if _is_item(text) else self.mapping(indent)

    def list_(self, indent: int) -> list:
        items: list = []
        while self._more():
            ind, text, n = self.lines[self.pos]
            if ind != indent or not _is_item(text):
                break
            rest = text[1:].strip()
            if not rest:
                self.pos += 1
                if self._more() and self.lines[self.pos][0] > indent:
                    items.append(self.node(self.lines[self.pos][0]))
                else:
                    items.append(None)
            elif _split_key(rest) is not None:
                offset = len(text) - len(rest)
                self.lines[self.pos] = (indent + offset, rest, n)
                items.append(self.mapping(indent + offset))
            else:
                items.append(_scalar(rest, n))
                self.pos += 1
        if self._more() and self.lines[self.pos][0] > indent:
            raise YamlError(f"line {self.lines[self.pos][2]}: bad indentation")
        return items

    def mapping(self, indent: int) -> dict:
        d: dict = {}
        while self._more():
            ind, text, n = self.lines[self.pos]
            if ind != indent or _is_item(text):
                break
            kv = _split_key(text)
            if kv is None:
                raise YamlError(f"line {n}: expected 'key: value'")
            key, val = kv
            if key in d:
                raise YamlError(f"line {n}: duplicate key")
            self.pos += 1
            if val == "":
                if self._more() and self.lines[self.pos][0] > indent:
                    d[key] = self.node(self.lines[self.pos][0])
                elif (
                    self._more()
                    and self.lines[self.pos][0] == indent
                    and _is_item(self.lines[self.pos][1])
                ):
                    d[key] = self.list_(indent)
                else:
                    d[key] = None
            else:
                d[key] = _scalar(val, n)
        if self._more() and self.lines[self.pos][0] > indent:
            raise YamlError(f"line {self.lines[self.pos][2]}: bad indentation")
        return d


def loads(text: str) -> Any:
    lines = _tokenize(text)
    if not lines:
        return None
    p = _Parser(lines)
    result = p.node(lines[0][0])
    if p.pos != len(p.lines):
        raise YamlError(f"line {p.lines[p.pos][2]}: unexpected content")
    return result
