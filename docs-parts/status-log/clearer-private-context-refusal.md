date: 2026-11-22
pr: none
what: A plan refused for a `private` context entry in a root whose `umwayi.json` cannot be read now says why: `context: task 1, entry 1, private; umwayi.json cannot be read, so every path counts as private`, in `goal start`, `show`, `status` and `report`. Before, the refusal looked like the guide's fault; in a real goal run it was the root's (every path counts as private when the config cannot be read, so any context file is refused). A good config gives the old words. The path is still never printed. The owner accepted the change.
tests: see the pull request
