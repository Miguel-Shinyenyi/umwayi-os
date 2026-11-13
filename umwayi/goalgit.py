"""Goal orchestration (W9.6b): the git commands umwayi runs, the worktree of a task, and the path checks.

This is the only place git is started for a goal. It holds the whole list of the 18 argument lists (design.md "The git
commands"), `run_git`, the pure `worktree_path`, `check_path` (the one check that `agent run --workdir` and
`agent check --workdir` also use), the `leftover`, `dirty` and `stale` checks, the cap of eight worktrees and the
lifecycle: make, verify, remove an unused one, remove after merged, and the plan's.

Rules this module keeps (requirements W9.R8.1 and W9.R8.9 to W9.R8.16):

* Argument lists only, never a shell, no network. Every list begins with the same words (`-c core.hooksPath=/dev/null`,
  `-c core.fsmonitor=false`, `-C DIR`) and runs with a clean environment (`GIT_CONFIG_GLOBAL=/dev/null` and the rest).
* Three writes exist: `worktree add -b`, `worktree add --detach` and `worktree remove`. Each appears once. No list
  holds push, merge, rebase, pull, fetch, reset, clean, checkout, switch, branch, tag, stash, commit, prune, lock,
  move, repair, --force or -f. There is no force flag anywhere, and no function here deletes a branch.
* A name or a path that enters a list matches a fixed pattern first. A path comes only from `worktree_path` and passes
  `check_path`. Nothing here reads a name from text.
* Nothing here changes the owner's working copy: no list touches HEAD, the index or a file of the root, and the
  reads of a worktree run with `GIT_OPTIONAL_LOCKS=0`.

Standard library only (`goalstate` is imported inside the one function that reads task files).
"""

from __future__ import annotations

import os
import posixpath
import re
import select
import signal
import stat
import subprocess
import time
from dataclasses import dataclass

from umwayi import goalpacket as gp
from umwayi.errors import UmwayiError, UsageError

GIT_TIMEOUT = 20.0  # seconds, for every list
OUTPUT_CAP = 1_000_000  # bytes of output, for every list
MAX_WORKTREES = 8  # the cap on disk use (KNOWN-LIMITS 229)
MAX_PATH = 4096
SUFFIX = "-worktrees"
ROOT_MODE = 0o700

_GOAL = re.compile(r"G-[0-9]{4,}")
_TASK = re.compile(r"T-[0-9]{2}")
_NAME = re.compile(r"g-[0-9]{4,}-(?:t-[0-9]{2}|plan)")
_BRANCH = re.compile(r"umwayi/g-[0-9]{4,}-t-[0-9]{2}")
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")

# What a refusal says. Fixed sentences: they never hold a path, a branch or text of an answer.
SENTENCES = {
    "stale": "main is behind origin/main: update main, then answer",
    "leftover": "a worktree, branch or folder of this task is left over, or the worktree root is full: remove it "
                "with git worktree remove, then answer",
    "dirty": "the worktree is not clean, or its tip moved: look at it, then answer",
    "config": "the worktree could not be made or checked: check the repo and the worktree root, then answer",
}
PATH_SENTENCE = ("agent: --workdir takes only a worktree that umwayi made under its worktree root. "
                 "Nothing was started.")


class GitError(UmwayiError):
    """git could not be run or gave more than the cap. Treated as `config` by the callers."""


class Refused(UmwayiError):
    """A start or a step that stops with `needs owner`. `reason` is stale, leftover, dirty or config; `found` lists
    what is left over, as (kind, text) pairs, for the queue row."""

    def __init__(self, reason: str, found=()):
        super().__init__(SENTENCES[reason])
        self.reason = reason
        self.found = tuple(found)


class PathRefused(UsageError):
    """`--workdir` or a worktree path was refused. Exit 64 at the command line. The message never echoes the path.
    `reason` is `path` (not a worktree umwayi made) or `config` (the worktree root is a link, a file or too wide)."""

    def __init__(self, reason: str = "path"):
        super().__init__(PATH_SENTENCE)
        self.reason = reason


# ------------------------------------------------------------------------------------------------ the list

# DIR is "root" (the umwayi root, a git work tree) or "tree" (the worktree of a task). {BRANCH}, {BASE}, {TIP}, {SHA}
# and {PATH} are filled after their pattern (or check_path) passed; every other word is a literal.
COMMANDS = {
    "is_repo": ("root", ("rev-parse", "--is-inside-work-tree"), False),
    "has_main": ("root", ("rev-parse", "--verify", "--quiet", "refs/heads/main"), False),
    "base": ("root", ("rev-parse", "refs/heads/main"), False),
    "has_origin_main": ("root", ("rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"), False),
    "behind_origin": ("root", ("rev-list", "--count", "refs/heads/main..refs/remotes/origin/main"), False),
    "branch_exists": ("root", ("rev-parse", "--verify", "--quiet", "refs/heads/{BRANCH}"), False),
    "worktree_list": ("root", ("worktree", "list", "--porcelain", "-z"), False),
    "worktree_add": ("root", ("worktree", "add", "-b", "{BRANCH}", "{PATH}", "{BASE}"), True),
    "worktree_add_detached": ("root", ("worktree", "add", "--detach", "{PATH}", "{BASE}"), True),
    "worktree_remove": ("root", ("worktree", "remove", "{PATH}"), True),
    "toplevel": ("tree", ("rev-parse", "--show-toplevel"), False),
    "common_dir": ("tree", ("rev-parse", "--git-common-dir"), False),
    "head": ("tree", ("rev-parse", "HEAD"), False),
    "status": ("tree", ("status", "--porcelain=v1", "-z", "--untracked-files=all"), False),
    "count_ahead": ("tree", ("rev-list", "--count", "{BASE}..HEAD"), False),
    "changed": ("tree", ("diff", "--name-status", "-z", "--no-ext-diff", "--no-renames", "{BASE}", "HEAD"), False),
    "is_ancestor": ("root", ("merge-base", "--is-ancestor", "{TIP}", "refs/heads/main"), False),
    "commit_exists": ("root", ("cat-file", "-e", "{SHA}^{commit}"), False),
}
WRITES = tuple(name for name, (_, _, writes) in COMMANDS.items() if writes)
_PREFIX = ("git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C")
_PATTERNS = {"BRANCH": _BRANCH, "BASE": _SHA, "TIP": _SHA, "SHA": _SHA}


def git_env(environ=None) -> dict:
    """The environment of every list: the program path and nothing else of the caller's, plus the fixed words."""
    environ = os.environ if environ is None else environ
    return {"PATH": environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
            "GIT_ATTR_NOSYSTEM": "1"}


def argv_for(name: str, directory: str, **params) -> list:
    """The argument list of one command. Pure. A parameter that does not match its pattern is a ValueError, and so is
    a missing, extra or unknown one. `PATH` must be given as a string; `run_git` checks it with `check_path` first."""
    if name not in COMMANDS:
        raise ValueError("unknown git command")
    if not isinstance(directory, str) or not directory.startswith("/") or "\x00" in directory:
        raise ValueError("bad directory")
    words = COMMANDS[name][1]
    wanted = {m for w in words for m in re.findall(r"\{([A-Z]+)\}", w)}
    if set(params) != wanted:
        raise ValueError("wrong parameters")
    out = []
    for w in words:
        for key in wanted:
            if "{" + key + "}" in w:
                value = params[key]
                if key == "PATH":
                    ok = isinstance(value, str) and value.startswith("/") and "\x00" not in value \
                        and "\n" not in value and 0 < len(value) <= MAX_PATH
                else:
                    ok = isinstance(value, str) and _PATTERNS[key].fullmatch(value) is not None
                if not ok:
                    raise ValueError("bad " + key)
                w = w.replace("{" + key + "}", value)
        out.append(w)
    return [*_PREFIX, directory, *out]


@dataclass(frozen=True)
class GitResult:
    code: int
    out: bytes

    @property
    def ok(self) -> bool:
        return self.code == 0

    def text(self) -> str:
        """The output as one line of text without its final newline, or "" if it is not text."""
        try:
            t = self.out.decode("utf-8")
        except UnicodeDecodeError:
            return ""
        return t[:-1] if t.endswith("\n") else t


def _spawn(argv: list) -> tuple:
    """Run one argument list: no shell, a clean environment, 20 seconds, 1 MB. Returns (code, output)."""
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env=git_env(), cwd=os.sep, start_new_session=True)
    except OSError:
        raise GitError("git could not be started") from None
    buf = bytearray()
    deadline = time.monotonic() + GIT_TIMEOUT
    fd = proc.stdout.fileno()

    def kill():
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.wait()

    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                kill()
                raise GitError("git did not answer in time")
            ready, _, _ = select.select([fd], [], [], min(left, 0.5))
            if not ready:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > OUTPUT_CAP:
                kill()
                raise GitError("git gave more output than the cap")
        proc.wait(timeout=max(deadline - time.monotonic(), 0.1))
    except subprocess.TimeoutExpired:
        kill()
        raise GitError("git did not end in time") from None
    finally:
        proc.stdout.close()
    return proc.returncode, bytes(buf)


def real_root(root) -> str:
    """The real path of the umwayi root (a link in the way is resolved here, once)."""
    return os.path.realpath(os.fspath(root))


def run_git(name: str, root, worktree: str | None = None, at_root: bool = False, **params) -> GitResult:
    """Run one command of the list. `root` is the umwayi root. A command about a tree needs `worktree`, which must pass
    `check_path` first (or `at_root=True`, to ask the root repo itself, as the path check does for the common dir).
    GitError if git cannot be run; a non-zero exit is a result, not an error."""
    if name not in COMMANDS:
        raise ValueError("unknown git command")
    kind, words, _ = COMMANDS[name]
    base = real_root(root)
    if kind == "tree" and not at_root:
        if worktree is None:
            raise ValueError("this command needs a worktree")
        directory = check_path(root, worktree)
    else:
        if worktree is not None or (at_root and kind != "tree"):
            raise ValueError("this command takes no worktree")
        directory = base
    if any("{PATH}" in w for w in words):
        if "PATH" not in params:
            raise ValueError("wrong parameters")
        params = dict(params, PATH=check_path(root, params["PATH"]))
    code, out = _spawn(argv_for(name, directory, **params))
    return GitResult(code, out)


# ------------------------------------------------------------------------------------------------ names and paths


def _ids(goal, task=None) -> None:
    if not (isinstance(goal, str) and _GOAL.fullmatch(goal)):
        raise ValueError("bad goal id")
    if task is not None and not (isinstance(task, str) and _TASK.fullmatch(task)):
        raise ValueError("bad task id")


def worktree_name(goal: str, task: str | None = None) -> str:
    """`g-0007-t-02` for a task, `g-0007-plan` for the plan. Pure; only from ids that matched their patterns."""
    _ids(goal, task)
    return goal.lower() + ("-plan" if task is None else "-" + task.lower())


def task_branch(goal: str, task: str) -> str:
    _ids(goal, task)
    return gp.branch_name(goal, task)


def worktree_root_of(root_real: str) -> str:
    """The fixed worktree root: the umwayi root's real path with `-worktrees` added. Pure."""
    if not (isinstance(root_real, str) and root_real.startswith("/") and posixpath.normpath(root_real) == root_real
            and root_real != "/" and "\x00" not in root_real):
        raise ValueError("the root must be a real absolute path")
    return root_real + SUFFIX


def worktree_path(root_real: str, goal: str, task: str | None = None) -> str:
    """The path of a task's worktree (or the plan's with no task). Pure: a function of the real path of the root and the
    ids, never of text. `check_path` then proves the answer."""
    return worktree_root_of(root_real) + "/" + worktree_name(goal, task)


def _inside(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def _lstat(path: str):
    try:
        return os.lstat(path)
    except OSError:
        return None


def check_worktree_root(root) -> str:
    """The fixed worktree root, if it exists and is right: a real folder (not a link), the owner's, mode 0700, outside
    the umwayi root. Returns its path. PathRefused (reason `config`) if it exists and is wrong, (reason `path`) if it
    is missing."""
    base = real_root(root)
    wt = worktree_root_of(base)
    st = _lstat(wt)
    if st is None:
        raise PathRefused("path")
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() \
            or stat.S_IMODE(st.st_mode) != ROOT_MODE or _inside(wt, base) or _inside(base, wt):
        raise PathRefused("config")
    if os.path.realpath(wt) != wt:
        raise PathRefused("config")
    return wt


def check_path(root, path, must_exist: bool = False) -> str:
    """Prove that `path` is a worktree path umwayi made (W9.R8.10, W9.R8.11), or raise PathRefused. Returns the path.

    The path must be the exact string `worktree_path` gives for some ids: a direct child of the fixed worktree root, a
    name in the pattern (lower case), no `..`, no trailing slash, no link on the way. The real path of the umwayi root
    is compared, so a root reached through a link is fine, but a path reached through a link is not. The worktree root
    must be a real folder, the owner's, mode 0700. If the path exists it is a real folder and not a link. This looks at
    the file system only; `verify_tree` adds the two git answers."""
    if not isinstance(path, str) or not path or len(path) > MAX_PATH or not path.isprintable() \
            or not path.startswith("/") or ".." in path.split("/"):
        raise PathRefused("path")
    base = real_root(root)
    if base == "/":
        raise PathRefused("path")
    wt = worktree_root_of(base)
    name = path[len(wt) + 1:] if path.startswith(wt + "/") else ""
    if not name or "/" in name or _NAME.fullmatch(name) is None:
        raise PathRefused("path")
    if path != wt + "/" + name or _inside(path, base) or _inside(base, path):
        raise PathRefused("path")
    check_worktree_root(root)  # a link, a file or a wide folder is `config`; a missing one is `path`
    st = _lstat(path)
    if st is None:
        if must_exist:
            raise PathRefused("path")
        return path
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or os.path.realpath(path) != path:
        raise PathRefused("path")
    return path


def _common(directory: str, answer: str) -> str:
    return os.path.realpath(answer if answer.startswith("/") else os.path.join(directory, answer))


def verify_tree(root, path) -> str:
    """`check_path` for an existing folder, plus the two git answers of W9.R8.10: `rev-parse --show-toplevel` is the path
    itself and `--git-common-dir` is the common dir of the root repo. PathRefused otherwise (also if git cannot be run)."""
    path = check_path(root, path, must_exist=True)
    try:
        top = run_git("toplevel", root, worktree=path)
        theirs = run_git("common_dir", root, worktree=path)
        mine = run_git("common_dir", root, at_root=True)
    except GitError:
        raise PathRefused("path") from None
    if not (top.ok and theirs.ok and mine.ok) or os.path.realpath(top.text()) != path \
            or _common(path, theirs.text()) != _common(real_root(root), mine.text()):
        raise PathRefused("path")
    return path


# ------------------------------------------------------------------------------------------------ reads


def is_repo(root) -> bool:
    r = run_git("is_repo", root)
    return r.ok and r.text() == "true"


def has_main(root) -> bool:
    return run_git("has_main", root).ok


def read_base(root) -> str:
    """BASE: the commit the local `main` points to now."""
    r = run_git("base", root)
    sha = r.text()
    if not r.ok or _SHA.fullmatch(sha) is None:
        raise Refused("config")
    return sha


def stale(root) -> bool:
    """True if `origin/main` exists and has commits that the local `main` lacks. umwayi never fetches."""
    if not run_git("has_origin_main", root).ok:
        return False
    r = run_git("behind_origin", root)
    if not r.ok or not r.text().isascii() or not r.text().isdigit():
        raise Refused("config")
    return int(r.text()) > 0


def listed(root) -> list:
    """The worktrees git lists for the root repo: a list of dicts with `worktree` (a path) and the other keys of
    `git worktree list --porcelain -z` that were present."""
    r = run_git("worktree_list", root)
    if not r.ok:
        raise Refused("config")
    try:
        fields = r.out.decode("utf-8").split("\x00")
    except UnicodeDecodeError:
        raise Refused("config") from None
    out, cur = [], {}
    for f in fields:
        if f == "":
            if cur:
                out.append(cur)
                cur = {}
            continue
        key, _, value = f.partition(" ")
        cur[key] = value
    if cur:
        out.append(cur)
    if any("worktree" not in rec for rec in out):
        raise Refused("config")
    return out


def _under(root, records) -> list:
    wt = worktree_root_of(real_root(root))
    return [rec["worktree"] for rec in records
            if posixpath.dirname(rec["worktree"]) == wt or posixpath.dirname(os.path.realpath(rec["worktree"])) == wt]


def worktrees(root) -> list:
    """The paths of the worktrees git lists under the fixed worktree root, sorted."""
    return sorted(_under(root, listed(root)))


# ------------------------------------------------------------------------------------------------ the checks


def _other_tasks_name(root, goal, task, path, branch) -> list:
    """Task files of every goal in the root that name this task's path or branch (W9.R8.14), apart from its own."""
    from umwayi import goalstate as gs
    found = []
    try:
        goals = gs.list_goals(root)
        for g in goals:
            for t in gs.list_tasks(root, g):
                try:
                    obj = gs.read_task(root, g, t)
                except UmwayiError:
                    found.append(("task-file", f"{g} {t}"))  # fails closed: a file that cannot be read is a doubt
                    continue
                if (g, t) == (goal, task):
                    continue
                if obj.get("branch") == branch or worktree_path(real_root(root), g, t) == path:
                    found.append(("task-file", f"{g} {t}"))
    except UmwayiError:
        found.append(("task-file", "state"))
    return found


def leftover(root, goal: str, task: str | None = None) -> list:
    """What is left over that stops a start (W9.R8.12, W9.R8.14), as (kind, text) pairs; empty if nothing.

    Kinds: `folder` (the path exists), `registration` (git lists the path or the branch), `task-branch` (the branch exists),
    `unlisted` (a folder or file in the worktree root that git does not list), `cap` (eight worktrees are there),
    `task-file` (another task's file names the same path or branch). Reads only."""
    _ids(goal, task)
    base = real_root(root)
    path = worktree_path(base, goal, task)
    wt = worktree_root_of(base)
    branch = None if task is None else task_branch(goal, task)
    found = []
    if _lstat(path) is not None:
        found.append(("folder", path))
    recs = listed(root)
    here = {path}
    for rec in recs:
        p = rec["worktree"]
        if p in here or os.path.realpath(p) in here or (branch is not None and rec.get("branch") == "refs/heads/" + branch):
            found.append(("registration", p))
    if branch is not None and run_git("branch_exists", root, BRANCH=branch).ok:
        found.append(("task-branch", branch))
    names = set()
    if os.path.isdir(wt) and not os.path.islink(wt):
        try:
            names = set(os.listdir(wt))
        except OSError:
            found.append(("unlisted", wt))
    known = set()
    for p in _under(root, recs):
        known.add(posixpath.basename(p))
    for n in sorted(names - known):
        found.append(("unlisted", wt + "/" + n))
    if len(names | known) >= MAX_WORKTREES:
        found.append(("cap", str(len(names | known))))
    if task is not None:
        found += _other_tasks_name(root, goal, task, path, branch)
    return found


def dirty(root, goal: str, task: str | None = None, tip: str | None = None) -> str | None:
    """None if the worktree is clean (and its tip is `tip`, when given); else `uncommitted`, `moved` or `missing`."""
    base = real_root(root)
    path = worktree_path(base, goal, task)
    try:
        check_path(root, path, must_exist=True)
    except PathRefused:
        return "missing"
    st = run_git("status", root, worktree=path)
    if not st.ok:
        raise Refused("config")
    if st.out:
        return "uncommitted"
    if tip is not None:
        if _SHA.fullmatch(tip) is None:
            raise ValueError("bad TIP")
        head = run_git("head", root, worktree=path)
        if not head.ok or head.text() != tip:
            return "moved"
    return None


# ------------------------------------------------------------------------------------------------ the lifecycle


@dataclass(frozen=True)
class Made:
    path: str
    base: str
    branch: str | None  # None for the plan's worktree (detached)


def start_check(root, goal: str, task: str | None = None) -> str:
    """Steps 1 and 2 of making a worktree (design.md): the root is a git work tree with a local `main`, `main` is not
    behind `origin/main` (`stale`), nothing of this task is left over (`leftover`). Returns BASE. Reads only; the caller
    writes BASE in the start entry before `make`."""
    _ids(goal, task)
    try:
        if not is_repo(root) or not has_main(root):
            raise Refused("config")
        base = read_base(root)
        if stale(root):
            raise Refused("stale")
        found = leftover(root, goal, task)
    except GitError:
        raise Refused("config") from None
    if found:
        raise Refused("leftover", found)
    return base


def _ensure_root(root) -> str:
    base = real_root(root)
    wt = worktree_root_of(base)
    st = _lstat(wt)
    if st is None:
        parent = posixpath.dirname(base)
        pst = _lstat(parent)
        if pst is None or stat.S_ISLNK(pst.st_mode) or not stat.S_ISDIR(pst.st_mode) or pst.st_uid != os.getuid():
            raise Refused("config")
        try:
            os.mkdir(wt, ROOT_MODE)
        except OSError:
            raise Refused("config") from None
    try:
        return check_worktree_root(root)
    except PathRefused:
        raise Refused("config") from None


def _make(root, goal, task, base) -> Made:
    _ids(goal, task)
    if not (isinstance(base, str) and _SHA.fullmatch(base)):
        raise ValueError("bad BASE")
    try:
        found = leftover(root, goal, task)  # time has passed since start_check
        if found:
            raise Refused("leftover", found)
        _ensure_root(root)
        path = worktree_path(real_root(root), goal, task)
        if task is None:
            added = run_git("worktree_add_detached", root, PATH=path, BASE=base)
            branch = None
        else:
            branch = task_branch(goal, task)
            added = run_git("worktree_add", root, BRANCH=branch, PATH=path, BASE=base)
        if not added.ok:
            raise Refused("config")  # nothing else is touched
        problem = _verify_new(root, path, base)
    except GitError:
        raise Refused("config") from None
    if problem:
        _undo(root, path)
        raise Refused("dirty")
    return Made(path, base, branch)


def _verify_new(root, path, base) -> bool:
    """True if the new worktree is wrong: not the right folder or repo, not at BASE, or not clean."""
    try:
        verify_tree(root, path)
    except PathRefused:
        return True
    head = run_git("head", root, worktree=path)
    st = run_git("status", root, worktree=path)
    return not (head.ok and head.text() == base and st.ok and not st.out)


def _undo(root, path) -> bool:
    """Remove a worktree that was just made, without force. False if git refused (it then stays, and is listed)."""
    try:
        return run_git("worktree_remove", root, PATH=path).ok
    except GitError:
        return False


def make(root, goal: str, task: str, base: str) -> Made:
    """Make the worktree of a task: `leftover` once more, the worktree root if it is missing (mode 0700), `worktree add
    -b BRANCH PATH BASE`, then verify: the toplevel is the path, the common dir is the root repo's, HEAD is BASE, the
    tree is clean. A failed add is `config` and nothing else is touched. A wrong new worktree is removed (no force) and
    is `dirty`. `base` is the one `start_check` returned and the caller recorded."""
    if task is None:
        raise ValueError("a task is needed; the plan's worktree is make_plan")
    return _make(root, goal, task, base)


def make_plan(root, goal: str, base: str) -> Made:
    """Make the plan's worktree: `worktree add --detach PATH BASE`, no branch (W9.R8.15)."""
    return _make(root, goal, None, base)


@dataclass(frozen=True)
class Removal:
    removed: bool
    why: str  # removed, gone, not merged, not clean, not at base, git refused


def _remove_clean(root, goal, task, at: str | None) -> Removal:
    base = real_root(root)
    path = worktree_path(base, goal, task)
    try:
        check_path(root, path, must_exist=True)
    except PathRefused:
        return Removal(False, "gone" if _lstat(path) is None else "git refused")
    try:
        st = run_git("status", root, worktree=path)
        if not st.ok or st.out:
            return Removal(False, "not clean")
        if at is not None:
            head = run_git("head", root, worktree=path)
            if not head.ok or head.text() != at:
                return Removal(False, "not at base")
        if not run_git("worktree_remove", root, PATH=path).ok:
            return Removal(False, "git refused")
    except GitError:
        return Removal(False, "git refused")
    return Removal(True, "removed")


def remove_unused(root, goal: str, task: str | None, base: str) -> Removal:
    """Remove a worktree that was made and in which no builder ever started, at once: only if it is clean and at BASE
    (nothing is lost). `worktree remove` without force. The branch of a task stays (it points at BASE)."""
    _ids(goal, task)
    if not (isinstance(base, str) and _SHA.fullmatch(base)):
        raise ValueError("bad BASE")
    return _remove_clean(root, goal, task, base)


def remove_after_merged(root, goal: str, task: str) -> Removal:
    """Cleanup after the owner's merged (W9.R8.13). The task file must say `merged`, the tree must be clean, and git
    removes it without force. Any other state, a tree with a change, or a refusal by git leaves it where it is and says
    why. The branch is never deleted."""
    _ids(goal, task)
    from umwayi import goalstate as gs
    try:
        state = gs.read_task(root, goal, task)["state"]
    except UmwayiError:
        return Removal(False, "not merged")
    if state != "merged":
        return Removal(False, "not merged")
    return _remove_clean(root, goal, task, None)


def remove_plan(root, goal: str, base: str | None = None) -> Removal:
    """Remove the plan's worktree when the plan is approved, denied or discarded (W9.R8.15). Only if it is clean (and at
    BASE, when given): a plan whose tree changed stays as evidence."""
    _ids(goal)
    if base is not None and not (isinstance(base, str) and _SHA.fullmatch(base)):
        raise ValueError("bad BASE")
    return _remove_clean(root, goal, None, base)
