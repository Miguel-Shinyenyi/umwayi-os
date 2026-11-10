"""Shared helpers for the budget governor tests (tasks B.1 to B.9).

Every test runs `python -m umwayi ...` as a real child process with a temporary HOME (tests/agents/support.py).
The fake `claude` of tests/agents/fake_agent.py is the fake telemetry sender: an "otlp" step posts a report to
the receiver of its run, as Claude Code's OTLP/HTTP JSON exporter would (design.md "Budget governor", Facts), or
with a planted wrong header, path, type or length. The OTLP JSON nesting here is the one the OpenTelemetry docs
describe; the exact shape Claude Code emits is checked by the owner in B.10.
"""

import hashlib
import json
import subprocess
import sys
from datetime import date, timedelta

from tests.agents.support import AgentCase, SECRET  # noqa: F401  (SECRET is used by the test modules)

PROMPT_TEXT = "PLANTED-PROMPT-TEXT-never-kept"

AGENTS = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    workdir: {work}
  - name: second
    platform: claude-code
    command: claude
    workdir: {work}
  - name: helper
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: [read_file]
  - name: spendno
    platform: claude-code
    command: claude
    workdir: {work}
  - name: spendask
    platform: claude-code
    command: claude
    workdir: {work}
  - name: slow
    platform: claude-code
    command: claude
    workdir: {work}
    timeout_minutes: 1
"""
RULES = """rules:
  - id: agents-yes
    title: these agents may start
    text: Allowed.
    verdict: yes
    matchers:
      type: agent_run
      agent: [reviewer, second, helper, spendno, spendask, slow]
  - id: budget-yes
    title: spend is fine for these agents
    text: Allowed.
    verdict: yes
    matchers:
      type: budget_check
      agent: [reviewer, second, helper, slow]
  - id: budget-no
    title: spendno may not spend
    text: This agent has no budget.
    verdict: no
    matchers:
      type: budget_check
      agent: spendno
  - id: read-yes
    title: reading is fine
    text: Reading is allowed.
    verdict: yes
    matchers:
      type: [tool_read, tool_read_file]
"""
READ = {"do": "tool", "tool": "Read", "input": {"file_path": "/etc/hostname"}}


def today() -> str:
    return date.today().isoformat()


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


# ------------------------------------------------------------ OTLP JSON bodies


def _attr(key, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {"key": key, "value": {"stringValue": value}} if isinstance(value, str) else {"key": key,
                                                                                               "value": value}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": value}}
    return {"key": key, "value": {"doubleValue": value}}


def api_request(cost_micros=12345, model="claude-sonnet-5", input_tokens=100, output_tokens=20, cache_read=5,
                cache_creation=1, extra=None, raw_cost=None):
    """One claude_code.api_request event, with a prompt-like attribute that must never be kept."""
    attrs = [_attr("event.name", "api_request"), _attr("model", model),
             _attr("input_tokens", input_tokens), _attr("output_tokens", output_tokens),
             _attr("cache_read_tokens", cache_read), _attr("cache_creation_tokens", cache_creation),
             _attr("prompt", PROMPT_TEXT), _attr("request_id", "req-" + PROMPT_TEXT)]
    if raw_cost is not None:
        attrs.append({"key": "cost_usd_micros", "value": raw_cost})
    elif cost_micros is not None:
        attrs.append(_attr("cost_usd_micros", cost_micros))
    attrs += extra or []
    return {"timeUnixNano": "1", "body": {"stringValue": "claude_code.api_request"}, "attributes": attrs}


def user_prompt_event():
    return {"timeUnixNano": "1", "body": {"stringValue": "claude_code.user_prompt"},
            "attributes": [_attr("event.name", "user_prompt"), _attr("prompt", PROMPT_TEXT),
                           _attr("prompt_length", 99)]}


def logs(*records):
    return {"resourceLogs": [{"resource": {"attributes": [_attr("service.name", "claude-code")]},
                              "scopeLogs": [{"scope": {"name": "com.anthropic.claude_code.events"},
                                             "logRecords": list(records)}]}]}


def cost_point(usd, model="claude-sonnet-5"):
    point = {"attributes": [_attr("model", model), _attr("user.prompt", PROMPT_TEXT)], "timeUnixNano": "1"}
    point["asDouble" if isinstance(usd, float) or not isinstance(usd, int) else "asInt"] = usd
    return point


def token_point(n, kind="input", model="claude-sonnet-5"):
    return {"attributes": [_attr("type", kind), _attr("model", model)], "asInt": n, "timeUnixNano": "1"}


def metrics(cost_points=(), token_points=()):
    ms = []
    if cost_points:
        ms.append({"name": "claude_code.cost.usage", "unit": "USD",
                   "sum": {"dataPoints": list(cost_points), "aggregationTemporality": 1, "isMonotonic": True}})
    if token_points:
        ms.append({"name": "claude_code.token.usage", "unit": "tokens",
                   "sum": {"dataPoints": list(token_points), "aggregationTemporality": 1, "isMonotonic": True}})
    return {"resourceMetrics": [{"resource": {"attributes": [_attr("service.name", "claude-code")]},
                                 "scopeMetrics": [{"scope": {"name": "com.anthropic.claude_code"}, "metrics": ms}]}]}


def send_logs(*records, **kw):
    return dict({"do": "otlp", "path": "/v1/logs", "body": logs(*records)}, **kw)


def send_metrics(cost_points=(), token_points=(), **kw):
    return dict({"do": "otlp", "path": "/v1/metrics", "body": metrics(cost_points, token_points)}, **kw)


# ------------------------------------------------------------ units.yaml

UNITS_HEAD = "version: 1\n"


def rate(value, when=None, source="owner", indent=6):
    pad = " " * indent
    return f"\n{pad}value: {value}\n{pad}date: {when or today()}\n{pad}source: {source}"


# ------------------------------------------------------------ the case


class BudgetCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.fake("kiro-cli")
        self.write_rules(RULES)
        self.write_agents(AGENTS)
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable))

    # ---- files

    def units(self, text: str):
        (self.root / "units.yaml").write_text(text, encoding="utf-8")

    def limits(self, **values):
        body = "".join(f"  {k}: {v}\n" for k, v in values.items())
        self.units(UNITS_HEAD + "limits:\n" + body)

    # ---- commands

    def run_agent(self, name="reviewer", *steps, extra=None, fault=None, prompt="Do the task"):
        return self.umwayi("run", name, "--prompt", prompt, extra=dict(self.script(*steps), **(extra or {})),
                           fault=fault)

    def start_run(self, name="reviewer", *steps, extra=None, fault=None):
        return self.start_umwayi("run", name, "--prompt", "A long task",
                                 extra=dict(self.script(*steps), **(extra or {})), fault=fault)

    def budget(self, *args, extra=None):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "budget", *args],
                           capture_output=True, text=True, env=self.env(extra), cwd=str(self.tmp), timeout=60)
        self.assertIn(r.returncode, {0, 2, 3, 64}, f"exit {r.returncode} is not allowed\n{r.stdout}\n{r.stderr}")
        return r

    def u(self, *args):
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args],
                              capture_output=True, text=True, env=self.env(), cwd=str(self.tmp), timeout=60)

    # ---- the ledger as umwayi wrote it

    def budget_entries(self):
        return [e for e in self.entries() if e.source == "umwayi budget"]

    def reserves(self):
        return [e for e in self.budget_entries() if e.added.startswith("Reserved run ")]

    def settles(self):
        return [e for e in self.budget_entries() if e.added.startswith("Settled run ")]

    def changes(self):
        return [e for e in self.budget_entries() if e.added.startswith("units.yaml changed")]

    def log_text(self) -> str:
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def otlp_statuses(self):
        return [c.get("status") for c in self.calls() if c.get("event") == "otlp"]

    def assert_no_planted_text(self, *outputs):
        text = "".join(outputs) + self.log_text()
        for word in (PROMPT_TEXT, SECRET):
            self.assertNotIn(word, text)

    def kill_on(self):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")

    # ---- a fixed ledger, written with the checked append in this test process (the code under test is the child)

    def write_ledger(self, rows):
        """rows: (date, agent, platform, reserved_micros, tag or None for an open reservation, settled_micros)."""
        from umwayi import budget, logbook, units
        n = 0
        for when, agent, platform, reserved, tag, micros in rows:
            n += 1
            run = f"{n:016x}"
            logbook.append(self.root, budget.entry(when, budget.reserve_text(run, agent, platform, reserved),
                                                   "fixture", "fixture"))
            if tag is not None:
                reading = units.Reading(tag, micros, "fixture")
                logbook.append(self.root, budget.entry(when, budget.settle_text(run, agent, platform, reserved,
                                                                               reading, None), "fixture", "fixture"))

    def rewrite_logbook(self, text: str):
        """A hand edit with the whole-file record rewritten and the chain recomputed, so only the budget shape
        check can find it."""
        from umwayi import logbook
        entries, problems = logbook.parse(text)
        assert not problems, problems
        out = text
        prev = None
        lines = text.split("\n")
        cs_start = None
        for p in entries:
            if p.chain is not None:
                cs_start = p if cs_start is None else cs_start
        if cs_start is not None:
            prefix = "\n".join(lines[:cs_start.line - 2]) + "\n"
            prev = hashlib.sha256(prefix.encode("utf-8")).hexdigest()
            for p in entries:
                if p.line < cs_start.line:
                    continue
                value = logbook.chain_value(prev, p.text)
                i = p.line - 1 + 6  # the Chain line: heading, blank, four fields
                lines[i] = "- Chain: " + value
                prev = value
            out = "\n".join(lines)
        (self.root / "LOGBOOK.md").write_text(out, encoding="utf-8")
        (self.root / ".umwayi" / "logbook.sha256").write_text(
            hashlib.sha256(out.encode("utf-8")).hexdigest() + "\n", encoding="ascii")


def json_line(obj) -> str:
    return json.dumps(obj)
