"""Layer 1: config file (umwayi.json).

Fail closed: a missing or invalid config is an error, never an empty
private list.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from umwayi.errors import UmwayiError

CONFIG_NAME = "umwayi.json"
_REQUIRED = {"memory_dir", "private_paths"}
_OPTIONAL = {"social_channels"}  # layer 7: channel names for the social helper
_CHANNEL = re.compile(r"^[a-z][a-z0-9-]{0,19}$")
MAX_CHANNELS = 5


@dataclass(frozen=True)
class Config:
    root: Path
    memory_dir: str
    private_paths: tuple[str, ...]
    social_channels: tuple[str, ...] = ()


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
    unknown = set(data) - _REQUIRED - _OPTIONAL
    if unknown:
        raise UmwayiError("config: unknown key(s) found")
    missing = _REQUIRED - set(data)
    if missing:
        raise UmwayiError("config: missing required key(s): " + ", ".join(sorted(missing)))
    memory_dir = _clean_rel(data["memory_dir"], "memory_dir")
    priv = data["private_paths"]
    if not isinstance(priv, list):
        raise UmwayiError("config: private_paths must be a list")
    private = tuple(_clean_rel(p, "private_paths entry") for p in priv)
    channels = _channels(data.get("social_channels", []))
    return Config(root=root, memory_dir=memory_dir, private_paths=private, social_channels=channels)


def _channels(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise UmwayiError("config: social_channels must be a list")
    if len(value) > MAX_CHANNELS:
        raise UmwayiError(f"config: social_channels has more than {MAX_CHANNELS} names")
    for c in value:
        if not isinstance(c, str) or not _CHANNEL.match(c):
            raise UmwayiError("config: each social_channels name must be lowercase letters, digits and '-' (up to 20)")
    if len(set(value)) != len(value):
        raise UmwayiError("config: social_channels has a name twice")
    return tuple(value)
