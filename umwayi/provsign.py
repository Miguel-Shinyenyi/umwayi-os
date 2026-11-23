"""W49 and W50: sign a task's provenance record with the owner's SSH key, and `umwayi verify PATH`.

Signing is the owner's act (`umwayi provenance sign GOAL TASK`, at a terminal, never in the supervisor). It runs
`ssh-keygen -Y sign -U -f PUBKEY -n umwayi-provenance` with the record on standard input: `-U` means only a key that `ssh-agent` holds is
used, so umwayi starts no process that reads a private key file, and umwayi never reads, copies, prints or stores a private key. The signature is
checked at once, written once beside the record (`TASK.json.sig`), and sealed by one logbook entry.

`verify` answers from a *trusted* record: the logbook verifies and has a chain; the record's hash is in a written entry and in a later signed
entry; the signature file's hash is in the signed entry; `ssh-keygen -Y verify` says the signature is good for the record and the key; and the
key's fingerprint is the one in the signed entry. A record that is signed but not trusted makes verify refuse (exit 2); it never falls back to an
older record.

What it does NOT prove: that the code is right, who wrote the bytes, or that nobody else could use the agent that holds the key (any process
that can reach `SSH_AUTH_SOCK` can sign; umwayi removes that variable from every helper it starts). The logbook is local: someone who can write
the root can rewrite the chain, the records and the signatures; only an anchor kept elsewhere (`--anchor`) catches that.

Standard library plus the system's `ssh-keygen`, found at a fixed absolute path (a regular file not writable by others). Nothing is installed,
and nothing goes over a network.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

from umwayi import kill, logbook, provenance
from umwayi.errors import UmwayiError

NAMESPACE = "umwayi-provenance"
PRINCIPAL = "umwayi-owner"
SSH_KEYGEN_PATHS = ("/usr/bin/ssh-keygen", "/usr/local/bin/ssh-keygen", "/opt/homebrew/bin/ssh-keygen")
KEY_TYPES = ("ssh-ed25519", "sk-ssh-ed25519@openssh.com")
SIGN_TIMEOUT_S = 60  # a hardware key waits for a touch
VERIFY_TIMEOUT_S = 20
_SIG_HEAD, _SIG_TAIL = "-----BEGIN SSH SIGNATURE-----", "-----END SSH SIGNATURE-----"
# fixed words of a refusal: no record text, no path, no key
REFUSALS = {
    "no_key": "provenance.public_key is not set in umwayi.json, or the key file is not one public key line of an allowed type",
    "no_tool": "ssh-keygen was not found at a fixed path",
    "no_agent": "there is no ssh-agent that holds this key (SSH_AUTH_SOCK)",
    "sign_failed": "ssh-keygen could not sign (the key is not in the agent, a timeout, or an old ssh-keygen)",
    "bad_signature": "the signature did not verify at once",
    "no_record": "there is no record for this task, or its written entry does not match",
    "signed_already": "this record is signed already",
    "no_chain": "the logbook has no hash chain",
    "logbook": "the logbook does not verify",
    "untrusted": "a record that names this file is signed but not trusted",
    "kill_switch": "the kill switch is on or its state cannot be read",
    "declined": "the owner did not type yes, so nothing was signed",
}
_FP = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
_SIGNED = re.compile(r"record (G-\d{4,}) (T-\d{2,}) signed \(record sha256 ([0-9a-f]{64}); signature sha256 ([0-9a-f]{64}); key (SHA256:[A-Za-z0-9+/]{43})\)")


class SignError(UmwayiError):
    def __init__(self, reason: str):
        assert reason in REFUSALS
        super().__init__(f"provenance: {REFUSALS[reason]}")
        self.reason = reason


def find_ssh_keygen() -> str:
    for p in SSH_KEYGEN_PATHS:
        try:
            st = os.stat(p)
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode) and os.access(p, os.X_OK) and not st.st_mode & 0o022:
            return p
    raise SignError("no_tool")


def read_public_key(path) -> tuple:
    """(the key line, its fingerprint) of a file that holds exactly one public key of an allowed type. Never a private key."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise SignError("no_key") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 4096:
            raise SignError("no_key")
        text = os.read(fd, 4097).decode("utf-8", "replace")
    finally:
        os.close(fd)
    lines = [l for l in text.splitlines() if l.strip()]
    if "PRIVATE KEY" in text or len(lines) != 1:
        raise SignError("no_key")
    parts = lines[0].split()
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        raise SignError("no_key")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except ValueError:
        raise SignError("no_key") from None
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")
    return f"{parts[0]} {parts[1]}", fp


def _run(args: list, data: bytes, timeout: float, env: dict):
    try:
        return subprocess.run(args, input=data, capture_output=True, timeout=timeout, env=env, shell=False, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return None


def sign_bytes(record: bytes, pubkey_file) -> bytes:
    """The armoured signature of `record`, made by the key in the agent whose public half is `pubkey_file`. Raises SignError."""
    tool = find_ssh_keygen()
    _line, _fp = read_public_key(pubkey_file)
    env = {"PATH": os.environ.get("PATH", ""), "LANG": "C"}
    if not os.environ.get("SSH_AUTH_SOCK"):
        raise SignError("no_agent")
    env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
    p = _run([tool, "-Y", "sign", "-U", "-f", str(pubkey_file), "-n", NAMESPACE], record, SIGN_TIMEOUT_S, env)
    if p is None or p.returncode != 0:
        raise SignError("sign_failed")
    sig = p.stdout.decode("ascii", "replace")
    lines = sig.strip().splitlines()
    if not lines or lines[0] != _SIG_HEAD or lines[-1] != _SIG_TAIL or sig.count(_SIG_HEAD) != 1:
        raise SignError("sign_failed")
    return sig.encode("ascii")


def verify_bytes(record: bytes, signature: bytes, key_line: str) -> bool:
    """True when `signature` is a good signature of `record` by the key `key_line` (type and base64, no comment)."""
    try:
        tool = find_ssh_keygen()
    except SignError:
        return False
    with tempfile.TemporaryDirectory(prefix="umwayi-v") as d:
        allowed, sigf = os.path.join(d, "allowed"), os.path.join(d, "sig")
        with open(allowed, "w", encoding="utf-8") as f:
            f.write(f'{PRINCIPAL} namespaces="{NAMESPACE}" {key_line}\n')
        with open(sigf, "wb") as f:
            f.write(signature)
        p = _run([tool, "-Y", "verify", "-f", allowed, "-I", PRINCIPAL, "-n", NAMESPACE, "-s", sigf], record, VERIFY_TIMEOUT_S,
                 {"PATH": os.environ.get("PATH", ""), "LANG": "C"})
    return p is not None and p.returncode == 0


def sig_path(root, goal: str, task: str) -> Path:
    return provenance.record_path(root, goal, task).with_name(f"{task}.json.sig")


def signed_entry(when: str, goal: str, task: str, record_sha: str, sig_sha: str, fp: str) -> logbook.Entry:
    return logbook.Entry(
        when, provenance.SOURCE, f"record {goal} {task} signed (record sha256 {record_sha}; signature sha256 {sig_sha}; key {fp})",
        "the hash chain was intact before this entry; the record hash matched the written entry; the signature verified with the "
        f"configured public key and namespace {NAMESPACE}",
        "No produced file was read or changed. The private key was not read by umwayi. No path or content is in this entry.")


def parse_signed(entry) -> dict | None:
    if getattr(entry, "source", None) != provenance.SOURCE:
        return None
    m = _SIGNED.fullmatch(getattr(entry, "added", "") or "")
    return None if not m else {"goal": m.group(1), "task": m.group(2), "record": m.group(3), "signature": m.group(4), "key": m.group(5)}


def _entries(root):
    """(entries, chain length) of an intact logbook. Raises SignError("logbook")."""
    try:
        return logbook.read_checked_chain(Path(root))
    except UmwayiError:
        raise SignError("logbook") from None


def sign_task(root, goal: str, task: str, when: str, pubkey_file, confirm) -> dict:
    """Sign the record of one task. `confirm(summary_lines)` returns True when the owner typed yes at a terminal. Fail closed at
    every step: nothing is written until the signature has verified. Raises SignError."""
    root = Path(root)
    if kill.stopped(kill.state(root)):
        raise SignError("kill_switch")
    line, fp = read_public_key(pubkey_file)
    entries, chain = _entries(root)
    if chain < 1:
        raise SignError("no_chain")
    rec_path = provenance.record_path(root, goal, task)
    try:
        data = rec_path.read_bytes()
    except OSError:
        raise SignError("no_record") from None
    sha = hashlib.sha256(data).hexdigest()
    written = [provenance.parse_written(e) for e in entries]
    if not any(w and (w["goal"], w["task"], w["sha256"]) == (goal, task, sha) for w in written):
        raise SignError("no_record")
    if any((s := parse_signed(e)) and (s["goal"], s["task"]) == (goal, task) for e in entries) or sig_path(root, goal, task).exists():
        raise SignError("signed_already")
    if not confirm([f"Sign the provenance record of {goal} {task}: record sha256 {sha}, key {fp}."]):
        raise SignError("declined")
    sig = sign_bytes(data, pubkey_file)
    if not verify_bytes(data, sig, line):
        raise SignError("bad_signature")
    path = sig_path(root, goal, task)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(sig)
    try:
        logbook.append(root, signed_entry(when, goal, task, sha, hashlib.sha256(sig).hexdigest(), fp))
    except UmwayiError:
        os.unlink(path)  # no entry, no signature file: the pair stays whole
        raise SignError("logbook") from None
    return {"goal": goal, "task": task, "record": sha, "key": fp}


# ----------------------------------------------------------------------------------------------- verify


def _record_files(root) -> list:
    """[(goal, task, path)] of every record file, newest goal and task last, from the folder names only."""
    base = Path(root) / provenance.FOLDER
    out = []
    try:
        for g in sorted(base.iterdir()):
            for f in sorted(g.glob("T-*.json")):
                out.append((g.name, f.name[:-5], f))
    except OSError:
        return []
    return out


def trusted(root, goal: str, task: str, entries, key_line_override: str | None = None):
    """The parsed record when (goal, task) has a trusted record, None when it is not signed at all, and raises SignError("untrusted") when it
    is signed and something does not match. Every check is a fixed one; no text of the record is shown."""
    rec_file = provenance.record_path(root, goal, task)
    sigf = sig_path(root, goal, task)
    signed = [s for s in (parse_signed(e) for e in entries) if s and (s["goal"], s["task"]) == (goal, task)]
    if not signed and not sigf.exists():
        return None
    try:
        data, sig = rec_file.read_bytes(), sigf.read_bytes()
    except OSError:
        raise SignError("untrusted") from None
    sha, sigsha = hashlib.sha256(data).hexdigest(), hashlib.sha256(sig).hexdigest()
    s = signed[-1] if signed else None
    wrote = [w for w in (provenance.parse_written(e) for e in entries) if w and (w["goal"], w["task"]) == (goal, task)]
    if not (s and wrote and wrote[0]["sha256"] == sha and s["record"] == sha and s["signature"] == sigsha):
        raise SignError("untrusted")
    key_line = key_line_override
    if key_line is None:
        raise SignError("untrusted")
    try:
        rec = json.loads(data.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        raise SignError("untrusted") from None
    blob = key_line.split()[1]
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(base64.b64decode(blob)).digest()).decode("ascii").rstrip("=")
    if fp != s["key"] or not verify_bytes(data, sig, key_line):
        raise SignError("untrusted")
    return rec, max(i for i, e in enumerate(entries) if (x := parse_signed(e)) and (x["goal"], x["task"]) == (goal, task))


def verify_path(root, rel: str, key_file, anchor: tuple | None = None, python: str | None = None) -> tuple:
    """(exit code, lines). 0 made by umwayi and unchanged; 3 made by umwayi and changed since; 2 no record or a refusal. Writes nothing."""
    root = Path(root)
    try:
        rep = logbook.verify(root, anchor)
        if rep.problems:
            raise SignError("logbook")
        entries, chain = _entries(root)
        if chain < 1:
            raise SignError("no_chain")
        key_line, _fp = read_public_key(key_file)
        target = (root / rel)
        st = os.lstat(target)
        if not stat.S_ISREG(st.st_mode):
            raise SignError("no_record")
        raw = target.read_bytes()
        found = []
        for goal, task, _f in _record_files(root):
            try:
                names = json.loads(provenance.record_path(root, goal, task).read_text(encoding="ascii"))
            except (OSError, ValueError):
                names = None
            if names is None or not any(f.get("path") == rel for f in names.get("files", ())):
                continue
            got = trusted(root, goal, task, entries, key_line)
            if got is not None:
                found.append((got[1], goal, task, got[0]))
    except SignError as e:
        return 2, [f"refused: {REFUSALS[e.reason]}. Allowed next: look at the logbook and the records, then ask again."]
    except OSError:
        return 2, [f"refused: {REFUSALS['no_record']}. Allowed next: give a file inside the root."]
    if not found:
        return 2, ["no record: no signed record names this file."]
    found.sort()  # by the place of the signed entry in the logbook: the newest record is last
    found = [(g, t, r) for _i, g, t, r in found]
    goal, task, rec = found[-1]
    how = provenance.compare(rec, rel, raw, python)
    where = f"{goal} {task}, tip {rec['tip'][:12]}"
    if how == "unchanged":
        return 0, [f"made by umwayi and unchanged ({where})."]
    if how == "structure":
        return 0, [f"made by umwayi and unchanged ({where}): same structure; comments or formatting changed."]
    older = next((f"{g} {t}" for g, t, r in reversed(found[:-1]) if provenance.compare(r, rel, raw, python) == "unchanged"), None)
    return 3, [f"made by umwayi and changed since ({where})." + (f" An older record ({older}) matches these bytes." if older else "")]
