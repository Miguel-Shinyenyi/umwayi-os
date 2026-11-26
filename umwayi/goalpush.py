"""Goal publish, step 2 (docs/goal-publish-design.md, option 1): push the branch of one task that is in review. It opens no
pull request and nothing calls it yet.

`push(root, goal, task, repo, when=...)` pushes `umwayi/g-NNNN-t-NN` to `origin`, and only that. In this order:

  1. the kill switch is off (checked again just before the push);
  2. the ids and the repo are in their fixed shapes, and the branch is built from the ids, never taken from the caller;
  3. the logbook says the task is `in review` with this branch, its goal is not stopped, and the local branch is still at
     the tip that was reviewed;
  4. `origin` has one push URL and it is the repo that the rules are asked about;
  5. `goalpublish.decide` says yes;
  6. a logbook entry is written (no entry, no push), the push runs, and a second entry is written.

The push is a fixed argument list with no shell. It has no force option, and its one refspec is the reviewed commit and the
task branch, so no `+` and no `main` can be in it. git runs through the one runner of `umwayi/goalgit.py`: a clean
environment, no hooks, a time limit, and its error output is dropped. Entries and results hold ids, counts and fixed words,
never git output or helper text.
"""
from __future__ import annotations

import re

from umwayi import goalgit as gg, goalpacket as gp, goalpublish, goalstate as gs, kill, logbook
from umwayi.errors import UmwayiError

SOURCE = "umwayi goal publish"  # not "umwayi goal": those entries have the strict shapes of goalstate
PUSHED = "pushed"
_GOAL = re.compile(r"G-[0-9]{4,6}")
_TASK = re.compile(r"T-[0-9]{2}")
_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
_BRANCH = re.compile(r"umwayi/g-[0-9]{4,6}-t-[0-9]{2}")
_TIP = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_GITHUB = ("https://github.com/", "git@github.com:", "ssh://git@github.com/")

# `-c` words beat the repo's own config: no hooks, and `origin` is never a mirror (a mirror push is a forced push of
# every ref). The options stop the config from adding tags or submodules to the push.
_PREFIX = ("git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "remote.origin.mirror=false",
           "-C")
_URLS = ("remote", "get-url", "--push", "--all", "origin")
_PUSH = ("push", "--no-follow-tags", "--recurse-submodules=no", "origin")


def push_argv(directory: str, tip: str, branch: str) -> list:
    """The argument list of the push. Pure. A tip or a branch outside its shape is a ValueError."""
    if not (isinstance(directory, str) and directory.startswith("/")):
        raise ValueError("bad directory")
    if not (isinstance(tip, str) and _TIP.fullmatch(tip)):
        raise ValueError("bad tip")
    if not (isinstance(branch, str) and _BRANCH.fullmatch(branch)):
        raise ValueError("bad branch")
    return [*_PREFIX, directory, *_PUSH, f"{tip}:refs/heads/{branch}"]


def _git(argv: list) -> tuple:
    """The one way this module starts git. A test replaces it to see every argument list."""
    return gg._spawn(argv)


def _origin_is(directory: str, repo: str) -> bool:
    """True if `origin` has exactly one push URL (after git's own rewrites) and it names `repo`: a GitHub URL, or a bare
    repo on this computer whose path ends in `owner/name.git`."""
    code, out = _git([*_PREFIX, directory, *_URLS])
    if code != 0:
        return False
    try:
        lines = out.decode("utf-8").split("\n")
    except UnicodeDecodeError:
        return False
    if len(lines) != 2 or lines[1]:
        return False
    url = lines[0]
    if url.startswith("/"):
        return url.endswith(f"/{repo}.git")
    return any(url in (host + repo, host + repo + ".git") for host in _GITHUB)


def _in_review(root, goal: str, task: str, branch: str) -> str | None:
    """The reviewed tip if the logbook says this task is in review on `branch` and its goal is not stopped, else None."""
    view = gs.view(root).get(goal)
    if view is None or view.stopped:
        return None
    t = view.tasks.get(task)
    if t is None or t.state != "in review" or t.branch != branch:
        return None
    return t.tip if isinstance(t.tip, str) and _TIP.fullmatch(t.tip) else None


def _log(root, when: str, goal: str, task: str, what: str, counts: str, not_done: str) -> bool:
    """One entry of ids and counts. False if it could not be written."""
    try:
        logbook.append(root, logbook.Entry(when, SOURCE, f"Goal {goal} task {task}: {what}", counts, not_done))
    except (UmwayiError, OSError):
        return False
    return True


def push(root, goal: str, task: str, repo: str, *, when: str) -> str:
    """Push the branch of one task in review. Returns one fixed word. Only `pushed` means a push that git reported as done
    and that both entries record.

    Nothing was pushed: `kill`, `name`, `state`, `moved`, `origin`, `no`, `ask`, `unlogged`.
    The push ran: `failed` (git did not report success), `unrecorded` (the entry after it could not be written, whatever
    git said)."""
    switch = kill.state(root)
    if kill.stopped(switch):
        # the result is `kill` whether or not this entry can be written
        _log(root, when, "(not read)", "(not read)", "push refused by the kill switch", "Pushes run: 0.",
             "Nothing was pushed.")
        return "kill"
    if not (isinstance(goal, str) and _GOAL.fullmatch(goal) and isinstance(task, str) and _TASK.fullmatch(task)
            and isinstance(repo, str) and _REPO.fullmatch(repo)):
        return "name"
    branch = gp.branch_name(goal, task)
    try:
        action = goalpublish.action(goal, task, repo, branch)
    except goalpublish.PublishRefused:
        return "name"
    try:
        tip = _in_review(root, goal, task, branch)
    except UmwayiError:
        return "state"  # a logbook that cannot be trusted says nothing is in review
    if tip is None:
        return "state"
    directory = gg.real_root(root)
    try:
        head = gg.run_git("branch_exists", root, BRANCH=branch)
        if not head.ok or head.text() != tip:
            return "moved"
        if not _origin_is(directory, repo):
            return "origin"
    except gg.GitError:
        return "origin"
    argv = push_argv(directory, tip, branch)
    answer = goalpublish.decide(root, action, when, kill_state=switch)
    if answer != "yes":
        return answer if answer in ("no", "unlogged") else "ask"
    if not _log(root, when, goal, task, "push attempt starts", "Branches to push: 1.", "No push has run yet."):
        return "unlogged"
    ran, done, stopped = 0, 0, False
    try:
        stopped = kill.stopped(kill.state(root))
        if not stopped:
            ran = 1
            try:
                done = 1 if _git(argv)[0] == 0 else 0
            except gg.GitError:
                done = 0
    finally:
        # also written when the push is cut off by an unexpected error
        recorded = _log(root, when, goal, task, "push attempt ended",
                        f"Pushes run: {ran}. Branches confirmed pushed: {done}.",
                        "No pull request was opened and nothing was merged.")
    if stopped:
        return "kill"
    if not recorded:
        return "unrecorded"
    return PUSHED if done else "failed"
