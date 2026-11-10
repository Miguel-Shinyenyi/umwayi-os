# AI helpers (layer 7)

## Purpose

The AI helpers (Steward and the social helper) draft only: they read the queue, the logbook or an article and write files under `drafts/`, and every step goes through the rules first. They exist so routine drafting is done for the owner without a helper ever approving, posting or changing anything else.

## Current state

AI helpers draft only. Every step an AI helper wants to take goes through the rules first, the same check as `umwayi check`:

- No stops the AI helper (exit 2).
- Ask me first stops it (exit 3) and adds a queue item of kind decision for you. Answering it is your record; it does not let the AI helper go on. To allow the action, add a Yes rule in rules.yaml.
- Only Yes continues.
- Every step adds one logbook entry. If rules.yaml is missing or broken, no AI helper runs (exit 3). If the logbook fails its tamper check, no AI helper runs (exit 1).
- An AI helper can never approve anything. The helper commands have no `--approved-by` option.
- AI helpers write files only under `drafts/` (plus their logbook entries, and the queue item when they stop on Ask me first).

### Steward

```
umwayi steward [--waiting-days 7] [--date 2026-11-07]
```

Reads `queue.md` and the logbook, and writes `drafts/steward-0001.md`: open items, items waiting longer than the given number of days, answered items not closed yet, and suggested next tasks. It never changes the queue and never answers an item.

### Social helper

```
umwayi social draft articles/week-45.md [--date 2026-11-07]
```

The article starts with front matter:

```
---
title: What I learned this week
link: https://example.org/what-i-learned
summary: One line about it (optional)
---
```

It writes one draft per channel listed in `umwayi.json`, for example `"social_channels": ["linkedin", "mastodon"]`, as `drafts/post-linkedin-0001.md`. Each post comes from one fixed template: the title, the summary (or the first paragraph), and `Read more: LINK`. Posts are at most 280 characters, plain text, with no hashtags and no em dashes. There is no model call and no network. It never posts. To publish a draft, run `umwayi publish-draft drafts/post-linkedin-0001.md`, which is Ask me first.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-08 | Answering a helper's queue item does not let it go on; to allow an action the owner changes `rules.yaml` | Layer 7, PR 7: on purpose, so an answer is a record and not a permission. |
| 2026-11-08 | No helper command has an `--approved-by` option (7.1) | Layer 7, PR 7: a helper can never approve. |
| 2026-11-08 | The social helper uses one fixed template, no model call and no network (7.3) | Layer 7, PR 7: a draft is predictable and offline. |

## Open questions

- Social drafts use the same text for every channel ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 7).
- If a later step stops, drafts from earlier steps stay, each with its own logbook entry ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), layer 7).
