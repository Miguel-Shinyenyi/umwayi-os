"""Command line entry point: `umwayi`.

Exit codes:
  umwayi check:  0 Yes, 2 No, 3 Ask me first
  umwayi rules due: 0 or 3, 64 for usage, 2 for a crash, never 1 (layer 13)
  usage errors:  64 (never 0, 2 or 3)
  other errors:  1
  umwayi agent:  0, 2, 3 or 64 only, never 1 (layer 10)
  umwayi budget: 0, 2, 3 or 64 only, never 1 (budget governor)
  umwayi view:   0, 1 (the tamper check failed), 2 or 64 only, never 3 (layer 12)
  umwayi decision reopen: 0 done, 1 refused (nothing changed), 2 a crash, 64 usage (layer 13)
  umwayi petition: 0 added or already open, 1 refused (nothing written), 2 a crash, 64 usage (layer 13)
"""

from __future__ import annotations

import argparse
import errno
import json
import re
import sys
from datetime import date
from pathlib import Path

from umwayi import (__version__, agents, archive, budget, decisions, elections, jobs, kill, logbook, petition, publish,
                    report, rules, schedule, taskqueue, units, view, workflow)
from umwayi.config import load_config
from umwayi.errors import UmwayiError, UsageError
from umwayi.helpers import social, steward
from umwayi.memory import load_bundle

EXIT_USAGE = 64  # usage and config errors
EXIT_ERROR = 1  # a refusal: something was checked and nothing was changed
EXIT_CRASH = 2  # an unexpected error: same code as No, so a hook treats it as blocking, never as Yes


def _today() -> str:
    """The system clock. Dates are never inferred from the queue itself."""
    return date.today().isoformat()


def _date_arg(value: str) -> str:
    if not taskqueue.is_valid_date(value):
        raise argparse.ArgumentTypeError("must be a real date in the form YYYY-MM-DD")
    return value


def _waiting_days_arg(value: str) -> int:
    if not re.fullmatch(r"\d{1,3}", value) or not 1 <= int(value) <= steward.MAX_WAITING_DAYS:
        raise argparse.ArgumentTypeError(f"must be a whole number from 1 to {steward.MAX_WAITING_DAYS}")
    return int(value)


def _within_arg(value: str) -> int:
    if not re.fullmatch(r"\d{1,4}", value) or not 0 <= int(value) <= elections.MAX_WITHIN:
        raise argparse.ArgumentTypeError(f"must be a whole number from 0 to {elections.MAX_WITHIN}")
    return int(value)


def _lines_arg(value: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)-(\d+)", value)
    if not m:
        raise argparse.ArgumentTypeError("must look like 10-20 (first and last line, counting from 1)")
    return int(m.group(1)), int(m.group(2))


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse would exit 2, which means "No"
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="umwayi", description="umwayi-os: an AI operating system for one person and their AI helpers.")
    p.add_argument("--version", action="version", version=f"umwayi {__version__}")
    p.add_argument("--root", default=".", help="folder that holds umwayi.json and rules.yaml (default: current folder)")
    sub = p.add_subparsers(dest="command", parser_class=_Parser)

    mem = sub.add_parser("memory", help="memory commands")
    msub = mem.add_subparsers(dest="memory_command", parser_class=_Parser)
    b = msub.add_parser("bundle", help="print the context bundle for an AI helper")
    b.add_argument("--format", choices=["text", "json"], default="text")

    q = sub.add_parser("queue", help="queue commands (queue.md)")
    qsub = q.add_subparsers(dest="queue_command", parser_class=_Parser)
    ql = qsub.add_parser("list", help="list rows of the queue")
    ql.add_argument("--status", choices=taskqueue.STATUSES, help="only rows with this status")
    ql.add_argument("--kind", choices=taskqueue.KINDS, help="only rows of this kind")
    qa = qsub.add_parser("add", help="add an open task or decision")
    qa.add_argument("--kind", required=True, choices=taskqueue.KINDS)
    qa.add_argument("title", help="short title, one line, no | character")
    qa.add_argument("--recommendation", default="", help="recommendation for the owner (optional)")
    qa.add_argument("--if-not-open", action="store_true",
                    help="add nothing if an open item of the same kind with the same title is already there")
    qn = qsub.add_parser("answer", help="mark an open row as answered")
    qn.add_argument("id", help="row id, for example Q-0001")
    qn.add_argument("--answer", required=True, help="the answer text (one line, no | character, up to 500 characters)")
    qn.add_argument("--revisit-if", dest="revisit_if",
                    help="what would change your mind (one line, no | character, up to 200 characters) or none; "
                         "required for a decision, refused for a task; kept in the logbook entry, not in queue.md")
    qc = qsub.add_parser("close", help="close a row")
    qc.add_argument("id", help="row id, for example Q-0001")
    qm = qsub.add_parser("migrate", help="convert an old six column queue.md to the current layout (once)")
    for sp in (qa, qn, qc, qm):
        sp.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    dc = sub.add_parser("decision", help="decision commands (layer 13): reopen a closed decision as a new question")
    dcsub = dc.add_subparsers(dest="decision_command", parser_class=_Parser)
    dcr = dcsub.add_parser("reopen", help="reopen an answered or closed decision: one new logbook entry that links "
                                          "the old entry by its hash, and one new open decision in the queue; the "
                                          "old entry and the old row are not changed")
    dcr.add_argument("target", help="the queue id (Q-0007) or the hash of its closing entry (64 lowercase hex "
                                    "characters, the Chain value)")
    dcr.add_argument("--reason", required=True, help="why it is reopened (one line, no | character, up to 300 "
                                                     "characters)")
    dcr.add_argument("--by", required=True, help="who reopens it (one line, no | or ; character, up to 40 "
                                                 "characters)")
    dcr.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    pt = sub.add_parser("petition", help="an AI helper objects to a No rule (layer 13): one open queue item for the "
                                         "owner; it never changes the rule or any answer")
    pt.add_argument("rule_id", help="the id of a rule in rules.yaml whose verdict is no")
    pt.add_argument("--helper", required=True, help="the AI helper's name: a lowercase letter, then up to 39 "
                                                    "lowercase letters, digits, _ or -")
    pt.add_argument("--reason", required=True, help="why, one line of plain text without | (up to 200 characters); "
                                                    "kept in queue.md only, marked as untrusted, never in the logbook")
    pt.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    ar = sub.add_parser("archive", help="archive commands")
    arsub = ar.add_subparsers(dest="archive_command", parser_class=_Parser)
    am = arsub.add_parser("move", help="move a block of text out of a file into the archive")
    am.add_argument("source", help="the file to cut the block from, relative to the root")
    am.add_argument("--reason", required=True, help="why the block is moved (one line, no | character)")
    am.add_argument("--lines", type=_lines_arg, help="first and last line to move, for example 10-20")
    am.add_argument("--start", help="a line that starts the block (the whole line must match, the line is included)")
    am.add_argument("--end", help="a line that ends the block (the whole line must match, the line is included)")
    am.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")
    arsub.add_parser("verify", help="recompute every SHA-256 fingerprint and compare with archive/INDEX.md")

    c = sub.add_parser(
        "check",
        help="check an action (JSON) against the rules: Yes (0), No (2), Ask me first (3)",
    )
    c.add_argument("action", nargs="?", help="action as JSON, or '-' to read it from standard input")
    c.add_argument("--rules", help="path to rules.yaml (default: <root>/rules.yaml)")
    c.add_argument("--json", action="store_true", help="print the answer as JSON")
    c.add_argument("--no-log", action="store_true", help="dry run: do not write the logbook entry")
    c.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD for the logbook entry (default: today)")
    c.add_argument("--kill-switch", action="store_true",
                   help="answer No while the kill switch is on or its state cannot be read (the layer 9 adapters use this)")

    ru = sub.add_parser("rules", help="rules commands")
    rusub = ru.add_subparsers(dest="rules_command", parser_class=_Parser)
    rud = rusub.add_parser("due", help="list the rules that have lapsed or are due for review (changes nothing); "
                                       "0, or 3 when a rule has lapsed")
    rud.add_argument("--within", type=_within_arg, default=elections.DEFAULT_WITHIN,
                     help=f"also list rules due within this many days (default {elections.DEFAULT_WITHIN}, 0 to "
                          f"{elections.MAX_WITHIN})")
    rud.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD; a date earlier than today changes nothing")

    rn = sub.add_parser("run", help="run one job from a jobs file (asks the rules first)")
    rn.add_argument("jobfile", help="the jobs file, for example jobs.yaml")
    rn.add_argument("--job", help="the job name (needed when the file has more than one job)")
    rn.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    rp = sub.add_parser("report", help="write a progress report draft from git history")
    rp.add_argument("--since", type=_date_arg, required=True, help="first day, YYYY-MM-DD")
    rp.add_argument("--date", type=_date_arg, help="today, YYYY-MM-DD (default: the system clock)")

    pd = sub.add_parser("publish-draft", help="copy a draft to outbox/ for the owner to post by hand")
    pd.add_argument("draft", help="a file directly inside drafts/")
    pd.add_argument("--approved-by", help="the owner's name, needed when the rules say Ask me first")
    pd.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    sw = sub.add_parser("steward", help="AI helper Steward: read the queue and write a proposal draft")
    sw.add_argument("--waiting-days", type=_waiting_days_arg, default=steward.DEFAULT_WAITING_DAYS,
                    help=f"open items older than this many days count as late (default {steward.DEFAULT_WAITING_DAYS})")
    sw.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    so = sub.add_parser("social", help="AI helper social: turn an article into post drafts")
    sosub = so.add_subparsers(dest="social_command", parser_class=_Parser)
    sd = sosub.add_parser("draft", help="write one post draft per channel in umwayi.json")
    sd.add_argument("article", help="a local article file with front matter (title, link, summary)")
    sd.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    wf = sub.add_parser("workflow", help="workflow commands (workflows/NAME.yaml)")
    wfsub = wf.add_subparsers(dest="workflow_command", parser_class=_Parser)
    wv = wfsub.add_parser("validate", help="check a workflow file, report every problem with a line number")
    wv.add_argument("name", help="the workflow name, for example content-loop")
    wr = wfsub.add_parser("run", help="run the steps of a workflow in order (asks the rules for every step)")
    wr.add_argument("name", help="the workflow name, for example content-loop")
    wr.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    kl = sub.add_parser("kill", help="the kill switch: stops every AI helper, job and workflow")
    klsub = kl.add_subparsers(dest="kill_command", parser_class=_Parser)
    kon = klsub.add_parser("on", help="turn the kill switch on (creates .umwayi/KILL)")
    kon.add_argument("--reason", help="why, one line of plain text (goes into the logbook)")
    kon.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")
    koff = klsub.add_parser("off", help="turn the kill switch off (removes .umwayi/KILL)")
    koff.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")
    klsub.add_parser("status", help="show the kill switch: off (exit 0), on or unknown (exit 3)")

    ag = sub.add_parser("agent", help="the front door for AI agents (agents.yaml); exit 0, 2, 3 or 64, never 1")
    agsub = ag.add_subparsers(dest="agent_command", parser_class=_Parser)
    agv = agsub.add_parser("validate", help="check agents.yaml, report every problem with a line number")
    agl = agsub.add_parser("list", help="list the agents in agents.yaml (starts nothing)")
    agc = agsub.add_parser("check", help="can this agent be gated? runs every gate check, starts no agent")
    agc.add_argument("name", help="the agent name from agents.yaml")
    agr = agsub.add_parser("run", help="start an agent once with a prompt (Claude Code or Kiro); 0, 2, 3 or 64")
    agr.add_argument("name", help="the agent name from agents.yaml")
    agr.add_argument("source", nargs="?", help="- to read the prompt from stdin")
    agr.add_argument("--prompt", help="the prompt text (at most 100 KB; never written to the logbook)")
    agr.add_argument("--prompt-file", help="a file that holds the prompt (at most 100 KB)")
    agch = agsub.add_parser("chat", help="a chat with an agent on your terminal (transport cli); 0, 2, 3 or 64")
    agch.add_argument("name", help="the agent name from agents.yaml")
    aglog = agsub.add_parser("login", help="sign in on your terminal (Claude Code ACP: claude.ai; Kiro: kiro-cli "
                                           "login), then the login check; 0, 2, 3 or 64")
    aglog.add_argument("name", help="the agent name from agents.yaml")
    for sp in (agv, agl, agc, agr, agch, aglog):
        sp.add_argument("--agents", help="the agents file (default: agents.yaml in the root)")

    sc = sub.add_parser("schedule", help="scheduled runs through systemd user timers (layer 11); 0, 2, 3 or 64, never 1")
    scsub = sc.add_subparsers(dest="schedule_command", parser_class=_Parser)
    scv = scsub.add_parser("validate", help="check schedule.yaml, every problem with a line number (writes nothing)")
    scs = scsub.add_parser("show", help="print the unit files (or --cron lines) install would write (writes nothing)")
    scs.add_argument("name", nargs="?", help="one entry from schedule.yaml (default: every entry)")
    scs.add_argument("--cron", action="store_true", help="print the equivalent crontab lines instead (never installed)")
    scc = scsub.add_parser("check", help="compare the installed unit files with what umwayi would write (writes nothing)")
    scc.add_argument("name", nargs="?", help="one entry from schedule.yaml (default: every entry)")
    sci = scsub.add_parser("install", help="write the two unit files of one entry (asks the rules); starts nothing")
    sci.add_argument("name", help="the entry name from schedule.yaml")
    sci.add_argument("--approved-by", help="the owner's name, when the rules say Ask me first")
    scr = scsub.add_parser("remove", help="remove the two unit files umwayi wrote for one entry (asks the rules)")
    scr.add_argument("name", help="the entry name from schedule.yaml")
    for sp in (scv, scs, scc, sci, scr):
        sp.add_argument("--file", help="the schedule file inside the root (default: schedule.yaml in the root)")
    for sp in (sci, scr):
        sp.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD for the logbook entry (default: today)")

    bg = sub.add_parser("budget", help="the budget governor (units.yaml, the ledger in the logbook); 0, 2, 3 or 64, "
                                       "never 1")
    bgsub = bg.add_subparsers(dest="budget_command", parser_class=_Parser)
    bgsub.add_parser("validate", help="check units.yaml, every problem with a line number (writes nothing)")
    bgs = bgsub.add_parser("status", help="used, reserved and left per limit, and the measured, declared and unknown "
                                          "shares (writes nothing)")
    bgs.add_argument("--date", type=_date_arg, help="the day YYYY-MM-DD to show (default: today)")
    bgsub.add_parser("calibrate", help="propose per_run and per_day from 20 measured runs over 7 days (changes "
                                       "nothing)")
    bgl = bgsub.add_parser("settle-lost", help="settle every reservation that has no settle (after a SIGKILL or a "
                                               "crash), as unknown at the worst case")
    bgl.add_argument("--by", required=True, help="who settles them (your name)")
    bgl.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD for the logbook entries (default: today)")

    vw = sub.add_parser("view", help="the web interface (layer 12); 0, 1, 2 or 64, never 3")
    vwsub = vw.add_subparsers(dest="view_command", parser_class=_Parser)
    vws = vwsub.add_parser("snapshot", help="write one JSON file of counts for the page, and one logbook entry "
                                            "(no text, path or secret of any file)")
    vws.add_argument("--out", help="the file to write, inside the root, ending in .json "
                                   "(default: .umwayi/snapshot.json)")
    vws.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD, the last of the seven budget days "
                                                    "(default: today, from the system clock)")

    lg = sub.add_parser("logbook", help="logbook commands")
    lgsub = lg.add_subparsers(dest="logbook_command", parser_class=_Parser)
    lgv = lgsub.add_parser("verify", help="check the format, the hash record and the hash chain of LOGBOOK.md "
                                          "(changes nothing)")
    lgv.add_argument("--anchor", help="also compare the chain with an anchor COUNT:HEX kept elsewhere")
    lgsub.add_parser("anchor", help="print COUNT:HEX of the hash chain, to keep outside this machine (changes nothing)")
    ls = lgsub.add_parser("seal", help="record the hash of LOGBOOK.md as it is now (explicit, never automatic)")
    ls.add_argument("--by", required=True, help="who seals it, one short line of plain text")
    ls.add_argument("--chain", action="store_true",
                    help="start the hash chain on a logbook that is already sealed and intact (allowed once)")
    ls.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")
    lr = lgsub.add_parser("recover", help="cut back the torn tail an interrupted write left (explicit, never automatic)")
    lr.add_argument("--torn-tail", action="store_true", required=True,
                    help="cut LOGBOOK.md back to the last recorded entry, only if the extra bytes are exactly the "
                         "start of the entry the interrupted write intended")
    lr.add_argument("--by", required=True, help="who cuts it, one short line of plain text")
    lr.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")
    return p


def _cmd_check(args, out) -> int:
    root = Path(args.root)
    rules_path = Path(args.rules) if args.rules else root / "rules.yaml"
    action_text = args.action
    if action_text == "-":
        try:
            action_text = sys.stdin.read(rules.MAX_ACTION_BYTES + 1)
        except Exception:
            action_text = None
    kill_state = kill.state(root)
    stop = kill.reason(kill_state) if args.kill_switch and kill.stopped(kill_state) else None
    decision, logged = rules.check_and_log(
        action_text, rules_path, root, args.date or _today(), log=not args.no_log,
        kill_state=kill_state if args.kill_switch else None, stop_reason=stop,
    )
    if args.json:
        data = decision.to_dict()
        data["logged"] = logged
        data["kill_switch"] = kill_state  # always there: off, on or unknown
        out.write(json.dumps(data, indent=2) + "\n")
    else:
        out.write(decision.render())
        if args.no_log:
            out.write("Nothing was logged (--no-log, dry run).\n")
    return decision.exit_code


def _cmd_rules(args, out) -> int:
    """Layer 13, `umwayi rules due`. Its own error handling: 64 for usage, 2 for anything else, never 1 (13.R3.3)."""
    try:
        code, lines = elections.due(Path(args.root), args.within, args.date)
        out.write("\n".join(lines) + "\n")
        return code
    except UsageError as e:
        sys.stderr.write(f"umwayi: error: {e}\n")
        return EXIT_USAGE
    except (Exception, KeyboardInterrupt) as e:
        try:
            sys.stderr.write(f"umwayi: rules due: stopped by an unexpected error ({type(e).__name__}). "
                             f"Exit {EXIT_CRASH}. Nothing was changed.\n")
        except Exception:
            pass
        return EXIT_CRASH


def _cmd_run(args, out) -> int:
    r = jobs.run(Path(args.root), Path(args.jobfile), args.job, args.date or _today())
    out.write("\n".join(r.lines) + "\n")
    return r.code


def _cmd_report(args, out) -> int:
    rep, rel = report.make(Path(args.root), args.since, args.date or _today())
    out.write(f"Wrote {rel}: {len(rep.commits)} commits from {rep.since} to {rep.until}.\n")
    out.write("It is a draft. Nothing was published or pushed.\n")
    return 0


def _cmd_publish(args, out) -> int:
    r = publish.publish(Path(args.root), args.draft, args.date or _today(), args.approved_by)
    out.write("\n".join(r.lines) + "\n")
    return r.code


def _cmd_helper(result, out) -> int:
    out.write("\n".join(result.lines) + "\n")
    return result.code


def _cmd_logbook(args, out) -> int:
    root = Path(args.root)
    if args.logbook_command == "seal":
        r = logbook.seal(root, args.date or _today(), args.by, start_chain=args.chain)
        out.write(f"Sealed LOGBOOK.md: {r.entries_before} earlier entries, hash recorded.\n")
        out.write(f"SHA-256: {r.sha256}\n")
        return 0
    if args.logbook_command == "recover":
        r = logbook.recover_torn_tail(root, args.date or _today(), args.by)
        out.write(f"Cut back a torn tail of {r.cut} bytes from LOGBOOK.md.\n")
        if r.logged:
            out.write("The logbook is intact again, and the cut is in the logbook.\n")
        else:
            out.write("The interrupted write was a seal, so nothing could be logged: "
                      "run 'umwayi logbook seal --by NAME' again.\n")
        return 0
    if args.logbook_command == "anchor":
        try:
            count, value = logbook.anchor(root)
        except UsageError:
            raise
        except UmwayiError as e:
            sys.stderr.write(f"umwayi: {e}\n")
            return EXIT_CRASH  # a logbook that does not verify is never anchored: exit 2, like a refused agent start
        out.write(f"{count}:{value}\n")
        out.write("Keep this anchor outside this machine: in the hub repository's sync log and on the Kiro Notion "
                  "page, weekly and before each submission. Check it later with "
                  f"umwayi logbook verify --anchor {count}:{value}\n")
        return 0
    report = logbook.verify(root, logbook.parse_anchor(args.anchor) if args.anchor is not None else None)
    if not report.problems:
        out.write(f"ok: {report.entries} entries, the format is valid and the hash matches the record\n")
        for note in report.notes + ([report.chain_note] if report.chain_note else []):
            out.write(f"info: {note}\n")
        return 0
    for note in report.notes:
        out.write(f"info: {note}\n")
    for p in report.problems:
        out.write(f"problem: {p.render()}\n")
    out.write(f"{len(report.problems)} problem(s) found\n")
    return 1


def _cmd_memory_bundle(args, out) -> int:
    config = load_config(Path(args.root))
    bundle = load_bundle(config)
    out.write(bundle.to_json() + "\n" if args.format == "json" else bundle.render())
    return 0


def _cmd_queue(args, out) -> int:
    root = Path(args.root)
    cmd = args.queue_command
    if cmd == "list":
        rows = taskqueue.list_rows(root, status=args.status, kind=args.kind)
        if not rows:
            out.write("No rows.\n")
            return 0
        for r in rows:
            line = f"{r.id}  {r.kind:<8}  {r.status:<8}  {r.answered or '-':<10}  {r.title}"
            if r.recommendation:
                line += f"  [recommendation: {r.recommendation}]"
            if r.answer:
                line += f"  [answer: {r.answer}]"
            out.write(line + "\n")
        return 0
    when = args.date or _today()
    if cmd == "add" and args.if_not_open:
        row, added = taskqueue.add_once(root, args.kind, args.title, args.recommendation, when)
        out.write(f"{'Added' if added else 'Already open, nothing added:'} {row.id} ({row.kind}): {row.title}\n")
    elif cmd == "add":
        row = taskqueue.add(root, args.kind, args.title, args.recommendation, when)
        out.write(f"Added {row.id} ({row.kind}): {row.title}\n")
    elif cmd == "answer":
        row = taskqueue.answer(root, args.id, args.answer, when, revisit_if=args.revisit_if)
        out.write(f"Answered {row.id} on {row.answered}\n")
    elif cmd == "close":
        row = taskqueue.close(root, args.id, when)
        out.write(f"Closed {row.id}\n")
    else:
        count = taskqueue.migrate(root, when)
        out.write(f"Migrated queue.md: {count} rows now have an answer column\n")
    return 0


def _cmd_archive(args, out) -> int:
    root = Path(args.root)
    if args.archive_command == "move":
        has_markers = args.start is not None or args.end is not None
        if (args.lines is None) == (not has_markers) or (has_markers and (args.start is None or args.end is None)):
            sys.stderr.write("umwayi archive move: error: give either --lines, or both --start and --end\n")
            return EXIT_USAGE
        r = archive.move(
            root, args.source, args.reason, args.date or _today(),
            lines=args.lines, start=args.start, end=args.end,
        )
        out.write(f"Moved lines {r.first_line}-{r.last_line} of {r.source} to {r.archive_path}\n")
        out.write(f"Id: {r.id}\n")
        out.write(f"Words: {r.words}\n")
        out.write(f"SHA-256: {r.sha256}\n")
        out.write(f"Pointer line left in {r.source}: {r.pointer}\n")
        out.write(f"To put it back later: umwayi archive restore {r.id} (this command is not built yet)\n")
        return 0
    results = archive.verify(root)
    counts = {s: 0 for s in (archive.OK, archive.CHANGED, archive.MISSING, archive.NOT_IN_INDEX)}
    for r in results:
        counts[r.status] += 1
        out.write(f"{r.id}  {r.status}  {r.path}\n")
    out.write(
        f"Checked {len(results)} archive files: {counts[archive.OK]} ok, {counts[archive.CHANGED]} changed, "
        f"{counts[archive.MISSING]} missing, {counts[archive.NOT_IN_INDEX]} not in the index\n"
    )
    return 0 if counts[archive.OK] == len(results) else 1


def _cmd_agent(args, out) -> int:
    """Layer 10. Its own error handling: 64 for usage and config, 2 for anything else, never 1."""
    try:
        if args.agent_command == "validate":
            return _cmd_helper(agents.validate_file(Path(args.root), args.agents), out)
        if args.agent_command == "list":
            return _cmd_helper(agents.list_agents(Path(args.root), args.agents), out)
        if args.agent_command == "run":
            if args.source not in (None, "-"):
                raise UsageError("agent run: the only word allowed after the name is - (read the prompt from stdin)")
            prompt = agents.read_prompt(args.prompt, args.prompt_file, args.source == "-", sys.stdin.buffer)
            return _cmd_helper(agents.run_agent(Path(args.root), args.name, prompt, _today, args.agents), out)
        if args.agent_command == "chat":
            return _cmd_helper(agents.chat_agent(Path(args.root), args.name, _today, args.agents, out), out)
        if args.agent_command == "login":
            return _cmd_helper(agents.login_agent(Path(args.root), args.name, _today, args.agents), out)
        return _cmd_helper(agents.check_agent(Path(args.root), args.name, args.agents), out)
    except UsageError as e:
        sys.stderr.write(f"umwayi: error: {e}\n")
        return EXIT_USAGE
    except (Exception, KeyboardInterrupt) as e:
        try:
            sys.stderr.write(f"umwayi: agent: stopped by an unexpected error ({type(e).__name__}). "
                             f"Exit {EXIT_CRASH}. Nothing was started.\n")
        except Exception:
            pass
        return EXIT_CRASH


def _cmd_budget(args, out) -> int:
    """The budget governor. Its own error handling: 64 for usage and config, 2 for anything else, never 1."""
    root = Path(args.root)
    try:
        cmd = args.budget_command
        if cmd == "validate":
            code, lines = units.validate(root, _today())
        elif cmd == "status":
            code, lines = budget.status(root, args.date or _today(), _today())
        elif cmd == "calibrate":
            code, lines = budget.calibrate(root, _today())
        else:
            code, lines = budget.settle_lost(root, args.date or _today(), args.by)
        out.write("\n".join(lines) + "\n")
        return code
    except UsageError as e:
        sys.stderr.write(f"umwayi: error: {e}\n")
        return EXIT_USAGE
    except UmwayiError as e:
        sys.stderr.write(f"umwayi: {e}\n")
        return EXIT_CRASH
    except (Exception, KeyboardInterrupt) as e:
        try:
            sys.stderr.write(f"umwayi: budget: stopped by an unexpected error ({type(e).__name__}). "
                             f"Exit {EXIT_CRASH}. Nothing was started.\n")
        except Exception:
            pass
        return EXIT_CRASH


def _cmd_view(args, out) -> int:
    """Layer 12. Its own error handling: 0, 1 (the tamper check, from view.snapshot), 2 or 64, never 3."""
    try:
        code, lines = view.snapshot(Path(args.root), args.out, args.date or _today())
        out.write("\n".join(lines) + "\n")
        return code
    except UsageError as e:
        sys.stderr.write(f"umwayi: error: {e}\n")
        return EXIT_USAGE
    except UmwayiError as e:
        sys.stderr.write(f"umwayi: {e}\n")
        return EXIT_CRASH
    except OSError as e:
        if e.errno == errno.ENAMETOOLONG:
            sys.stderr.write("umwayi: error: a path is longer than this system allows. Nothing was changed.\n")
            return EXIT_USAGE
        return _crashed(e)
    except (Exception, KeyboardInterrupt) as e:
        return _crashed(e)


def _cmd_schedule(args, out) -> int:
    """Layer 11. Its own error handling: 64 for usage and config, 2 for anything else, never 1 (11.R6)."""
    root = Path(args.root)
    try:
        cmd = args.schedule_command
        if cmd == "validate":
            return _cmd_helper(schedule.validate_file(root, args.file), out)
        if cmd == "show":
            return _cmd_helper(schedule.show(root, args.name, args.cron, args.file), out)
        if cmd == "check":
            return _cmd_helper(schedule.check(root, args.name, args.file), out)
        if cmd == "install":
            return _cmd_helper(schedule.install(root, args.name, args.date or _today(), args.approved_by, args.file),
                               out)
        return _cmd_helper(schedule.remove(root, args.name, args.date or _today(), args.file), out)
    except UsageError as e:
        sys.stderr.write(f"umwayi: error: {e}\n")
        return EXIT_USAGE
    except UmwayiError as e:
        sys.stderr.write(f"umwayi: {e}\n")
        return EXIT_CRASH
    except (Exception, KeyboardInterrupt) as e:
        try:
            sys.stderr.write(f"umwayi: schedule: stopped by an unexpected error ({type(e).__name__}). "
                             f"Exit {EXIT_CRASH}. Nothing was started.\n")
        except Exception:
            pass
        return EXIT_CRASH


def main(argv: list[str] | None = None, out=None) -> int:
    out = out or sys.stdout
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else EXIT_USAGE
    try:
        if args.command == "check":
            return _cmd_check(args, out)
        if args.command == "rules" and getattr(args, "rules_command", None):
            return _cmd_rules(args, out)
        if args.command == "agent" and getattr(args, "agent_command", None):
            return _cmd_agent(args, out)
        if args.command == "schedule" and getattr(args, "schedule_command", None):
            return _cmd_schedule(args, out)
        if args.command == "budget" and getattr(args, "budget_command", None):
            return _cmd_budget(args, out)
        if args.command == "view" and getattr(args, "view_command", None) == "snapshot":
            return _cmd_view(args, out)
        if args.command == "queue" and getattr(args, "queue_command", None):
            return _cmd_queue(args, out)
        if args.command == "petition":
            r = petition.petition(Path(args.root), args.rule_id, args.helper, args.reason, args.date or _today())
            out.write("\n".join(petition.render(r)) + "\n")
            return 0
        if args.command == "decision" and getattr(args, "decision_command", None) == "reopen":
            r = decisions.reopen(Path(args.root), args.target, args.reason, args.by, args.date or _today())
            out.write("\n".join(decisions.render(r)) + "\n")
            return 0
        if args.command == "workflow" and getattr(args, "workflow_command", None) == "validate":
            return _cmd_helper(workflow.validate_file(Path(args.root), args.name), out)
        if args.command == "workflow" and getattr(args, "workflow_command", None) == "run":
            return _cmd_helper(workflow.run(Path(args.root), args.name, args.date or _today()), out)
        if args.command == "kill" and getattr(args, "kill_command", None) == "on":
            return _cmd_helper(kill.turn_on(Path(args.root), args.date or _today(), args.reason), out)
        if args.command == "kill" and getattr(args, "kill_command", None) == "off":
            return _cmd_helper(kill.turn_off(Path(args.root), args.date or _today()), out)
        if args.command == "kill" and getattr(args, "kill_command", None) == "status":
            return _cmd_helper(kill.status(Path(args.root)), out)
        if args.command == "steward":
            return _cmd_helper(steward.run(Path(args.root), args.date or _today(), args.waiting_days), out)
        if args.command == "social" and getattr(args, "social_command", None) == "draft":
            return _cmd_helper(social.draft(Path(args.root), args.article, args.date or _today()), out)
        if args.command == "run":
            return _cmd_run(args, out)
        if args.command == "report":
            return _cmd_report(args, out)
        if args.command == "publish-draft":
            return _cmd_publish(args, out)
        if args.command == "logbook" and getattr(args, "logbook_command", None):
            return _cmd_logbook(args, out)
        if args.command == "archive" and getattr(args, "archive_command", None):
            return _cmd_archive(args, out)
        if args.command == "memory" and getattr(args, "memory_command", None) == "bundle":
            return _cmd_memory_bundle(args, out)
    except UsageError as e:
        sys.stderr.write(f"umwayi: error: {e}\n")
        return EXIT_USAGE
    except UmwayiError as e:
        sys.stderr.write(f"umwayi: {e}\n")
        return EXIT_ERROR
    except OSError as e:
        if e.errno != errno.ENAMETOOLONG:
            return _crashed(e)
        # S.2: a path argument longer than the system allows is a usage error, not a crash; the path is not printed
        sys.stderr.write("umwayi: error: a path is longer than this system allows. Nothing was changed.\n")
        return EXIT_USAGE
    except (Exception, KeyboardInterrupt) as e:
        return _crashed(e)
    parser.print_usage(sys.stderr)
    return EXIT_USAGE


def _crashed(e: BaseException) -> int:
    """An unexpected error: exit 2, like No. Never print the message: it may hold file content or a secret. The type
    name is enough to start."""
    try:
        sys.stderr.write(
            f"umwayi: stopped by an unexpected error ({type(e).__name__}). Exit {EXIT_CRASH}. "
            "Check 'umwayi logbook verify' and the files this command works on.\n"
        )
    except Exception:
        pass
    return EXIT_CRASH


if __name__ == "__main__":
    sys.exit(main())
