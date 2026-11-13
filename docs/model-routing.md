# Model routing options (W19, part 3b)

## Purpose

This page lists the models that Kiro and OpenCode offer, what their own docs say each one is good at, and the kinds of
task each one suits. It only proposes options. The owner always chooses the model. Nothing in umwayi reads this table to
pick a model, and `umwayi routing check` never suggests one.

Model lists change every few weeks. So each row cites the vendor page it came from, the day that page was read, and a
`review_by` date. A row past its `review_by` date fails the checker until someone reads the page again.

## Current state

Built: the table below, and `umwayi routing check PATH` (`umwayi/routing.py`). The command reads this table or the
[task log](task-log.md) and prints one line for each failure to standard error. It exits 0 if the file is well formed,
2 on any failure, 64 for a wrong command line, and never 1 or 3. It changes nothing and runs only when the owner runs it.
Use `--date YYYY-MM-DD` to check as of another day.

The table has these columns, in this order: platform, model, strengths, task types, source, source date, review_by.

The checker fails on:

- a platform that is not Kiro or OpenCode, or an empty model or strengths cell;
- a task type that is not in the fixed list below, an empty list, or a type named twice;
- a source that is not an https page of the vendor of that platform (kiro.dev for Kiro, opencode.ai or docs.opencode.ai
  for OpenCode), or that has a query, a fragment, a port or a login part;
- a source date or review_by that is not a real date, a source date in the future, a review_by that is not after the
  source date or is more than 45 days after it, and a review_by that is already past;
- the same model twice for one platform, a row with the wrong number of columns, a cell over 600 characters, a header
  that is not exactly the seven names, a second table, and a file that is unreadable, too big or not UTF-8.

Task types: general, hard-multistep, routine-multistep, scoped-coding, bug-fix, review, docs, refactor, long-context,
agent-work, high-volume, budget, multilingual, structured-decision, private-local.

What it does not do: it does not read the vendor page, so a strength that is wrong passes. It does not rank models and
it does not know which model is right for a task. Only the form is checked.

How the rows were made: on 2026-11-13 I read the two Kiro pages (the strengths page, and the overview page for costs and
fallbacks) and the two OpenCode pages named in the sources. Strengths are my short paraphrase of what the vendor wrote.
Costs are not in the rows, because they change faster than the rest. Read the current credit multiplier on
https://kiro.dev/docs/models/ before a choice. The Kiro overview page was marked updated on 2026-11-12.

Left out on purpose: Claude Sonnet 4.0 (Kiro lists it as end of life since 2026-10-14). OpenCode Console lists about 90
models and gives no strength for any single one, so only the rows where the page says something are here.

| platform | model | strengths | task types | source | source date | review_by |
| --- | --- | --- | --- | --- | --- | --- |
| Kiro | Auto | Kiro's own router. It sends each request to a frontier model and falls back on its own. Free tier gets Sonnet class quality or better, paid tiers Opus class or better. It never routes to Experimental models. | general | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | GPT-5.6 Sol | OpenAI flagship tier for the hardest multi-step work: long-horizon refactors and complex terminal tasks. 1M token context. Highest credit use of the three GPT-5.6 tiers. | hard-multistep, refactor, long-context | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | GPT-5.6 Terra | Middle tier for routine multi-step development, between Sol's capability and Luna's speed. 1M token context. | routine-multistep | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | GPT-5.6 Luna | Fastest and cheapest GPT-5.6 tier, for frequent agentic tasks where speed and credit use matter more than peak capability. 1M token context. | high-volume, budget, agent-work | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Fable 5.1 | Anthropic model for long-running, context-heavy work: root cause tracing, multi-file refactors, long autonomous runs. Kiro Enterprise only, an administrator must enable it. Runs in US East only. Traffic is kept up to 30 days for abuse checks. Not for a personal plan. | hard-multistep, refactor, long-context | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Opus 5.5 | Latest Opus for demanding agentic coding. Strong on long, complex tasks, checks its own work and writes clear summaries. 1M token context. | hard-multistep, long-context | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Opus 5 | Strong on multi-file features and large refactors, finishes whole tasks without stubs, verifies its own work and coordinates parallel agents with fewer conflicts. 1M token context. | hard-multistep, refactor, agent-work | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Opus 4.8 | Opus that flags uncertainty and pushes back when evidence is thin, with efficient tool calling and good follow-through on long agentic tasks. 1M token context. | review, hard-multistep | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Opus 4.7 | Scales its reasoning to the task by itself. Follows instructions closely, checks its output before reporting and reads dense screenshots and diagrams better. 1M token context. | hard-multistep, review | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Opus 4.6 | Strong agentic coding that stays productive in long sessions and on very large codebases. Good at debugging and code review through planning and self-correction. 1M token context. | bug-fix, review, long-context | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Opus 4.5 | Handles trade-offs and ambiguity across several systems and aims to be right on the first attempt for complex problems. 200K token context. | hard-multistep | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Sonnet 5.5 | Fastest Sonnet, over 30 percent faster than Sonnet 5. Suited to scoped coding, bug fixes, review, agent and subagent work, and scoped docs, slides and spreadsheets. 1M token context. | scoped-coding, bug-fix, review, agent-work, docs | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Sonnet 5 | Plans before it edits, runs longer without supervision and checks its own output. Suited to spec-driven work with higher fidelity across broad changes, and to agent tasks that run to the end. 1M token context. | routine-multistep, agent-work | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Sonnet 4.6 | Upgrade of Sonnet 4.5 that is more token efficient. Good at iterative work and long sessions, and works as lead agent or subagent. | routine-multistep, agent-work | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Sonnet 4.5 | Agentic coding with long autonomous runs and good tool use. Better planning, system design and security engineering than Sonnet 4.0. 200K token context. | routine-multistep | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Haiku 5.5 | For high-volume work that needs quick answers. Very low credit use for requests up to 100K tokens, higher above that. 1M token context. | high-volume, budget | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Claude Haiku 4.5 | Anthropic's fastest model with near-frontier results, matching Sonnet 4 on reasoning and coding at more than twice the speed. 200K token context. | high-volume, budget, scoped-coding | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Grok 4.7 | xAI model for coding and knowledge work that stays on task through long jobs and checks its work. Experimental in Kiro and not on the Free tier. 500K token context, higher credit use above 200K tokens. | hard-multistep, long-context | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Kimi K3 | Moonshot open-weight model for long-running coding and knowledge work. Takes text and images, 1M token context. A Kiro Excluded Model, so the AWS output indemnity does not apply. US geography only. | long-context, agent-work | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | MiniMax M2.5 | Open-weight model with strong coding across the whole development cycle, from design to review, at a fraction of frontier cost. | routine-multistep, budget | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | GLM-5 | Open-weight model for repository-scale context. Suited to cross-file migrations, full-stack features and legacy refactors. 200K token context. | refactor, long-context | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | DeepSeek 3.2 | Open-weight model for agentic workflows and code generation. Handles long tool-calling chains and stateful sessions. Experimental in Kiro. | agent-work, budget | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | MiniMax M2.1 | Open-weight model for multilingual programming and UI generation, with good results in Rust, Go, C++, Kotlin and TypeScript. Experimental in Kiro. | multilingual, budget | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| Kiro | Qwen3 Coder Next | Open-weight model built for coding agents with strong error recovery. Best for long agentic coding sessions, and the most cost-effective open-weight option. 256K token context. Experimental in Kiro. | budget, agent-work | https://kiro.dev/docs/models/available-models/ | 2026-11-13 | 2026-12-13 |
| OpenCode | OpenCode Console paid models | OpenCode says its team tested and verified the Console models as working well as coding agents. It states no strength for any single model, so this row says nothing about which one suits a task. The list changes often, read it with the models command. | agent-work | https://opencode.ai/docs/console/models/ | 2026-11-13 | 2026-12-13 |
| OpenCode | Big Pickle | A stealth model that OpenCode offers free for a limited time while it collects feedback. OpenCode states no strengths for it. | budget | https://opencode.ai/docs/console/models/ | 2026-11-13 | 2026-12-13 |
| OpenCode | GLM-5.3-Flash Free | Free for a limited time. OpenCode says the provider keeps no data and does not train on it. OpenCode states no strengths for it. | budget | https://opencode.ai/docs/console/models/ | 2026-11-13 | 2026-12-13 |
| OpenCode | DeepSeek V4.1 Flash Free | Free for a limited time. OpenCode says the provider keeps no data and does not train on it. OpenCode states no strengths for it. | budget | https://opencode.ai/docs/console/models/ | 2026-11-13 | 2026-12-13 |
| OpenCode | MiniMax M3.1 Flash Free | Free for a limited time. OpenCode says the provider keeps no data and does not train on it. OpenCode states no strengths for it. | budget | https://opencode.ai/docs/console/models/ | 2026-11-13 | 2026-12-13 |
| OpenCode | Jev 1.13 | A System One model from TypeSafe AI for fast, structured decisions. It does not write text. It scores a state against yes or no, multiple choice or rubric questions and returns values and probabilities. Not a coding model. | structured-decision | https://opencode.ai/docs/console/models/ | 2026-11-13 | 2026-12-13 |
| OpenCode | GPT 6 Luna Decision | Takes the same System One request as Jev and accepts text and images. Not a coding model. | structured-decision | https://opencode.ai/docs/console/models/ | 2026-11-13 | 2026-12-13 |
| OpenCode | Gemini Decision 1 | Takes the same System One request as Jev and also accepts audio, video and PDFs. Not a coding model. | structured-decision | https://opencode.ai/docs/console/models/ | 2026-11-13 | 2026-12-13 |
| OpenCode | Local models (Ollama, LM Studio, vLLM) | OpenCode finds local models at their default addresses. For Ollama and LM Studio it reads context size, vision and tool support from the server. vLLM models are found as text only, and tool calling needs server flags that discovery does not report. Quality depends on the model you run. | private-local, budget | https://opencode.ai/docs/models/ | 2026-11-13 | 2026-12-13 |

## Decisions log

- 2026-11-13: The owner chooses the model, always. This page and the checker propose and check. Reason: the owner's
  instruction for W19 part 3b.
- 2026-11-13: `review_by` is 30 days after the day the source was read, and the checker allows at most 45. Reason: model
  lists change within weeks. The 30 and 45 are the builder's proposal, not an owner decision (see Open questions).
- 2026-11-13: The checker fails a row whose `review_by` is past. Reason: a table nobody re-reads should stop passing, not
  stay quietly out of date. The cost is that this check starts failing on 2026-12-14 until the rows are re-read.
- 2026-11-13: No cost figure is in a row. Reason: credit multipliers change faster than strengths and sit on a different
  Kiro page than the one each row cites.

## Open questions

- Which OpenCode models belong in the table? OpenCode gives no strength per model, so I listed only the rows where its
  page says something. Recommendation: keep it so, and add an OpenCode model only when its page says what it is good at.
- Is 30 days (maximum 45) the right wait before a row must be read again? Recommendation: keep 30.
- Should a later task connect this table to the guidance loader or the agents files? That was out of scope here.
  Recommendation: not yet. Keep it a page the owner reads.
