"""W19 part 2: the concerns record checker. `umwayi concerns check PATH`.

The hub doc "engineering-concerns" says every project keeps a record with one row for each of 111 engineering
concepts. Each row answers Applies, Not applicable or Deferred, gives a one sentence reason, and, for Applies,
points at evidence: a file that exists inside the repo.

The record is a markdown table with these columns, in this order:

    | number | concept | answer | reason | evidence | date |

This code checks that the record exists and is well formed. It never claims that the content is true: a reason
that says something false passes, and a file that exists is not proof that the concern is met.

Strict and fail closed: any problem is a failure, nothing is guessed or repaired, and a failure line names a row
by its line and number but never repeats text from the file (safety rule 2). Standard library only, no network, no
scheduling, nothing is written. It is a command the owner runs; no job, timer or workflow starts it.
Exit codes in the command line: 0 well formed, 2 any failure or error, 64 usage; never 1 or 3.
"""

from __future__ import annotations

import datetime
import os
import re
import stat
from pathlib import Path

from umwayi import fsutil

MAX_BYTES = 1_000_000
ANSWERS = ("Applies", "Not applicable", "Deferred")
COLUMNS = ("number", "concept", "answer", "reason", "evidence", "date")

# The 111 concepts, numbered 1 to 111 in this order, as in the hub doc engineering-concerns.
CONCEPTS = (
    "Rate limiting", "Caching", "Load balancing", "Reverse proxies", "API gateways", "CI/CD", "Docker",
    "Kubernetes", "Service discovery", "Circuit breakers", "Timeouts", "Retries", "Exponential backoff",
    "Idempotency", "Message queues", "Pub/sub", "Event-driven architecture", "Distributed transactions",
    "Saga pattern", "Dead letter queues", "Cron jobs", "WebSockets", "Long polling", "Server-sent events",
    "Database indexing", "Query optimization", "N+1 queries", "Connection pooling", "Read replicas", "Sharding",
    "Partitioning", "Replication", "Leader election", "CAP theorem", "Eventual consistency", "Optimistic locking",
    "Pessimistic locking", "Distributed locks", "Race conditions", "Deadlocks", "Memory leaks",
    "Garbage collection", "Thread safety", "Backpressure", "Autoscaling", "Horizontal scaling",
    "Vertical scaling", "CDN", "Edge caching", "Cache invalidation", "Feature flags", "Blue-green deployment",
    "Canary releases", "Rolling deployments", "Rollbacks", "Health checks", "Liveness and readiness probes",
    "Monitoring", "Logging", "Distributed tracing", "Metrics", "Alerts", "SLOs", "SLIs", "Error budgets",
    "Observability", "Secrets management", "IAM", "OAuth", "JWT rotation", "TLS", "Encryption at rest",
    "Encryption in transit", "WAF", "DDoS protection", "CORS", "CSRF", "SQL injection", "XSS", "SSRF",
    "Database migrations", "Schema versioning", "Disaster recovery", "Backups", "Failover",
    "Multi-region deployment", "Chaos engineering", "Cost optimization", "Cold starts", "Serverless limits",
    "Latency", "Throughput", "P99 latency", "Tail latency", "Network partitions", "Clock skew", "DNS",
    "TCP vs UDP", "HTTP/2 and HTTP/3", "gRPC", "Webhooks", "API versioning", "Semantic versioning",
    "Infrastructure as code", "Terraform", "Helm charts", "Build caching", "Dependency hell",
    "Production incidents", "On-call", "Postmortems",
)

_NUMBER = re.compile(r"[0-9]{1,6}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SEPARATOR_CELL = re.compile(r":?-{3,}:?")


def numbered_concepts() -> list[tuple[int, str]]:
    """The list as (number, name) pairs, numbered 1 to 111."""
    return list(enumerate(CONCEPTS, start=1))


def _cells(line: str) -> list[str] | None:
    s = line.strip()
    if len(s) < 2 or not s.startswith("|") or not s.endswith("|"):
        return None
    return [c.strip() for c in s[1:-1].split("|")]


def _valid_date(text: str) -> bool:
    if not _DATE.fullmatch(text):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _evidence_ok(evidence: str, root: Path) -> bool:
    """True only for a regular file that really sits inside the repo root: a relative path with no `..` part,
    not absolute, and, after every link is followed, still inside the root. Nothing is read from the file."""
    if not evidence or any(ord(ch) < 32 or ord(ch) == 127 for ch in evidence):
        return False
    if evidence.startswith(("/", "~")) or "\\" in evidence or ":" in evidence:
        return False
    if any(part == ".." for part in evidence.split("/")):
        return False
    try:
        real_root = root.resolve(strict=True)
        real = (real_root / evidence).resolve(strict=True)
        if not real.is_relative_to(real_root):
            return False
        return stat.S_ISREG(os.stat(real).st_mode)
    except (OSError, ValueError, RuntimeError):
        return False


def check_text(text: str, root: Path) -> list[str]:
    """The failures of a record, one line each, in a fixed order. An empty list means the record is well formed."""
    root = Path(root)
    lines = text.splitlines()
    header_at = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")), None)
    if header_at is None:
        return ["no table found: the record needs a table with the columns " + ", ".join(COLUMNS)]
    header = _cells(lines[header_at])
    if header is None or tuple(header) != COLUMNS:
        return [f"line {header_at + 1}: the table header must be exactly: " + " | ".join(COLUMNS)]
    sep = _cells(lines[header_at + 1]) if header_at + 1 < len(lines) else None
    if sep is None or len(sep) != len(COLUMNS) or not all(_SEPARATOR_CELL.fullmatch(c) for c in sep):
        return [f"line {header_at + 2}: the header must be followed by a separator row such as | --- | --- |"]

    failures: list[str] = []
    seen: dict[int, int] = {}
    for i in range(header_at + 2, len(lines)):
        raw = lines[i]
        if not raw.strip().startswith("|"):
            continue
        at = f"line {i + 1}"
        cells = _cells(raw)
        if cells is None or len(cells) != len(COLUMNS):
            failures.append(f"{at}: the row must have exactly {len(COLUMNS)} columns")
            continue
        number, concept, answer, reason, evidence, date = cells
        n = None
        if not _NUMBER.fullmatch(number) or str(int(number)) != number:
            failures.append(f"{at}: the number is not a plain whole number")
        elif not 1 <= int(number) <= len(CONCEPTS):
            failures.append(f"{at}: the number is outside 1 to {len(CONCEPTS)}")
        elif int(number) in seen:
            failures.append(f"{at}: number {number} is a duplicate of line {seen[int(number)]}")
        else:
            n = int(number)
            seen[n] = i + 1
        who = f"{at}, number {n}" if n else at
        if n and concept != CONCEPTS[n - 1]:
            failures.append(f"{who}: the concept does not match the name of number {n}")
        if answer not in ANSWERS:
            failures.append(f"{who}: the answer must be Applies, Not applicable or Deferred")
        if not reason.strip():
            failures.append(f"{who}: the reason is empty")
        if answer == "Applies" and not _evidence_ok(evidence, root):
            failures.append(f"{who}: an Applies row needs evidence, a file inside the repo that exists")
        if not _valid_date(date):
            failures.append(f"{who}: the date must be a real date written YYYY-MM-DD")
    for k, name in numbered_concepts():
        if k not in seen:
            failures.append(f"number {k} ({name}) is missing")
    return failures


def check_file(path: Path, root: Path) -> list[str]:
    """Read the record at `path` (a regular file, UTF-8, at most MAX_BYTES) and check it against the repo `root`."""
    try:
        data = fsutil.read_regular(Path(path), MAX_BYTES)
    except fsutil.TooBig:
        return [f"the record is larger than {MAX_BYTES} bytes"]
    except OSError:
        return ["the record cannot be read: it must be a regular file that exists"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ["the record is not valid UTF-8 text"]
    return check_text(text, Path(root))
