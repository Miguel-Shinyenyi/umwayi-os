"""Goal publish, step 1 (docs/goal-publish-design.md, option 1): the rules action `goal_publish`. It starts and pushes nothing.

When a task of a goal has been accepted, a later step will push its branch and open a draft pull request. Before that step may do anything it
asks the rules this one question, built from ids and names and never from helper text:

    {"type": "goal_publish", "goal": "G-0002", "task": "T-01", "repo": "owner/name", "branch": "umwayi/g-0002-t-01"}

No rule means Ask me first, so nothing is published until the owner writes a Yes rule that names the repo. `goal_publish` is on the never list of
graded autonomy (umwayi/rules.py): no autonomy may turn Ask me first into Yes. The branch must be a task branch of umwayi (`umwayi/g-NNNN-t-NN`),
never `main` and never another name; a repo is `owner/name`. This module only builds the action and asks; it has no push, no `gh` and no network.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from umwayi import rules

TYPE = "goal_publish"
_GOAL = re.compile(r"^G-[0-9]{4,6}$")
_TASK = re.compile(r"^T-[0-9]{2,4}$")
_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")
_BRANCH = re.compile(r"^umwayi/g-[0-9]{4,6}-t-[0-9]{2,4}$")


class PublishRefused(ValueError):
    """The action cannot be built: a name is not in the fixed shape. The message never carries the text it refused."""


def action(goal: str, task: str, repo: str, branch: str) -> dict:
    """The rules action for publishing one task branch. Every field is checked against a fixed shape first."""
    if not isinstance(goal, str) or not _GOAL.match(goal):
        raise PublishRefused("the goal id is not in the shape G-0001")
    if not isinstance(task, str) or not _TASK.match(task):
        raise PublishRefused("the task id is not in the shape T-01")
    if not isinstance(repo, str) or not _REPO.match(repo) or repo.endswith(".git"):
        raise PublishRefused("the repo is not in the shape owner/name")
    if not isinstance(branch, str) or not _BRANCH.match(branch):
        raise PublishRefused("the branch is not a task branch of umwayi (umwayi/g-0001-t-01)")
    if branch != f"umwayi/{goal.lower()}-{task.lower()}":
        raise PublishRefused("the branch does not belong to this goal and task")
    return {"type": TYPE, "goal": goal, "task": task, "repo": repo, "branch": branch}


def decide(root, act: dict, when: str, kill_state: str | None = None) -> str:
    """Ask the rules and write one logbook entry. Returns "yes", "no", "ask" or "unlogged".

    "yes" only when the answer is Yes, no autonomy is on it and the entry was written. Everything else is a refusal."""
    root = Path(root)
    decision, logged = rules.check_and_log(json.dumps(act), root / "rules.yaml", root, when, kill_state=kill_state)
    if not logged:
        return "unlogged"
    if decision.answer == rules.NO:
        return "no"
    if decision.answer != rules.YES or decision.autonomy is not None:
        return "ask"
    return "yes"
