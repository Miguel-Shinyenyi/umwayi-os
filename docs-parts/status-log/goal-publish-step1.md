date: 2026-11-26
pr: 270
what: Goal publish step 1, the priority of the owner (umwayi-os must push on its own). A new rules action `goal_publish` (goal, task, repo, branch) in `umwayi/goalpublish.py`: it builds the question from fixed shapes (a task branch `umwayi/g-NNNN-t-NN`, never main, and the branch must match the goal and task) and asks the rules; no rule is Ask me first; a Yes needs a rule that names the repo; it is on the never list of graded autonomy in `umwayi/rules.py`. It starts, pushes and opens nothing. The example is in `goal.rules.example.yaml`. The push and the pull request text are steps 2 and 3.
tests: tests/test_goalpublish.py, 11 tests; all passed on a local run (0.04 s). CI is the main check.
