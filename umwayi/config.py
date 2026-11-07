"""Layer 1: config file (umwayi.json).

Fail closed: a missing or invalid config is an error, never an empty
private list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from umwayi.errors import UmwayiError

CONFIG_NAME = "umwayi.json"
_KEYS = {"memory_dir", "private_paths"}


@dataclass(frozen=True)
class Config:
    root: Path
    memory_dir: str
    private_paths: tuple[str, ...]


def _clean_rel(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UmwayiError(f"config: {what} must be a non-empty string")
    v = value.strip().replace("\\", "/")
    while v.startswith("./"):
        v = v[2:]
    v = v.rstrip("/")
    if not v:
        raise UmwayiError(f"config: {what} must name a path inside the root")
    if v.startswith("/") or (len(v) > 1 and v[1] == ":"):
        raise UmwayiError(f"config: {what} must be relative to the root")
    if ".." in PurePosixPath(v).parts:
        raise UmwayiError(f"config: {what} must not contain '..'")
    return v


def load_config(root: Path) -> Config:
    root = Path(root)
    path = root / CONFIG_NAME
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise UmwayiError(f"config: cannot read {CONFIG_NAME} in the root") from None
    except UnicodeDecodeError:
        raise UmwayiError(f"config: {CONFIG_NAME} is not valid UTF-8") from None
    try:
        data = json.loads(raw)
    except ValueError:
        raise UmwayiError(f"config: {CONFIG_NAME} is not valid JSON") from None
    if not isinstance(data, dict):
        raise UmwayiError("config: top level must be an object")
    unknown = set(data) - _KEYS
    if unknown:
        raise UmwayiError("config: unknown key(s) found")
    missing = _KEYS - set(data)
    if missing:
        raise UmwayiError("config: missing required key(s): " + ", ".join(sorted(missing)))
    memory_dir = _clean_rel(data["memory_dir"], "memory_dir")
    priv = data["private_paths"]
    if not isinstance(priv, list):
        raise UmwayiError("config: private_paths must be a list")
    private = tuple(_clean_rel(p, "private_paths entry") for p in priv)
    return Config(root=root, memory_dir=memory_dir, private_paths=private)
