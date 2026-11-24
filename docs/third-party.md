# Third-party software and credit lines (M5)

## Purpose

This page says what umwayi-os uses from other people, what it does not ship or host, and where a credit line belongs. umwayi-os is a set of rules and records around AI helpers. It does not contain a model, it does not host one, and it does not call a model by itself. A helper (Claude Code, OpenCode, Muse Code) is a program the owner installs and signs in to; umwayi starts it and checks what it can, and never reads, prints or stores a key or a sign-in token.

Each piece named below keeps its own licence and terms. This page does not restate them. The owner has read the Muse terms and agreed (2026-11-23).

## Current state

What umwayi-os uses:

| What | Where | Note |
|---|---|---|
| Python 3.10 or newer, the standard library only | the `umwayi` package and `tools/` | `pyproject.toml` lists no dependency |
| `three` and `esbuild` | `ui/` | the 3D scene and its build |
| `next`, `react`, `react-dom` and `three` | `site/` | the public site |
| `git`, and `gh` with the owner's own login | `tools/` (`pr_green.py`, `pr_number.py`) and the goal flow's git steps | the code never reads, prints or stores the token of `gh` |
| `ssh-keygen`, `ssh-agent` and `ssh-add` | `umwayi provenance sign` and `umwayi verify` | the owner's own key, never read by umwayi |
| Landlock (Linux) and Seatbelt (macOS) | `umwayi/confine.py`, `umwayi/seatbelt.py` | operating system features, not software shipped here |

Helpers the owner installs and signs in to (umwayi ships none of them):

- **Claude Code** and **OpenCode**: built, with their own checks.
- **Kiro**: paused by the owner (account problem, AWS case open). Code and design stay.
- **Muse Code**: designed (`docs/muse-route-design.md`), not built. No run of Muse has been made by umwayi yet.

What umwayi-os does not do: it does not ship, host, fine tune or resell a model, and it does not train one.

### Credit lines

- The line **"Built with Muse Spark Open"** appears only where a doc, a screen or a video shows a Muse Spark Open run. There is none today, so the line is not used anywhere yet.
- No Meta logo is used. The credit is words only.
- Other helpers are named in plain words where a run is shown, with no logo.

### Data use on free credits

On free credits, content sent to Muse may be used by Meta for product improvement. For that reason only public umwayi-os work is ever sent to Muse: never code of a private or confidential repository, never a secret. The owner sets the public mark; umwayi never infers it. This sentence goes with any page, post or video that mentions a Muse run.

## Decisions log

- 2026-11-23 (owner): the credit line and the no-logo rule above; the data-use sentence stays with every Muse mention.
- 2026-11-24 (this page): the credit line is not used until a Spark Open run is shown, so no page claims a run that did not happen.

## Open questions

- **Q1.** Where does a video carry the credit line? Recommendation: in the on-screen caption of the scene that shows the run, in the same words, so a viewer sees it with the run and not only in the description.
- **Q2.** Should this page list the licence of each dependency? Recommendation: no. A copy goes stale; the lockfiles and `LICENSE` files of each package are the record, and the page links nothing it cannot keep true.
