"""M4 g and h, the first part: goal shares and windows, as pure functions. Nothing calls them yet.

A long-running goal carries a share of one provider's allowance, a whole percent (the owner writes it). From the share the governor derives
three caps and checks a task against all three before the task starts:

  monthly cap = share of the month's allowance (free credits have no month: the pacing horizon is the month and the credits at acceptance
                are its allowance, Q8)
  weekly cap  = share of the weekly allowance, and never more than the monthly cap left spread over the weeks left
  daily cap   = the weekly cap left spread over the days left in the week, and never more than the day's share of M4 b

A task that does not fit a cap left WAITS (the widest window it does not fit is named) ("waiting, daily cap", weekly or monthly); it is not failed. A task larger than an empty
daily window is refused with the fixed reason `task_larger_than_cap` and goes to the owner. The shares of all goals on one provider may not
add up above 100 percent minus a reserve for the owner's own use (20 percent, Q9): a goal that would break the sum is refused with
`share_over_allocated`. Windows follow the owner's local day and week (Nairobi, UTC+3, no daylight saving), never UTC: a time after 21:00 UTC
is already tomorrow in Nairobi. Every number is a whole UU and rounds down. These functions spend nothing, read no file and call no command;
a goal share is a check before a task starts (cooperative), it does not stop a provider from being used outside umwayi.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

NAIROBI = timezone(timedelta(hours=3), "Africa/Nairobi")
DEFAULT_RESERVE_PCT = 20
TOO_BIG = "task_larger_than_cap"
OVER_ALLOCATED = "share_over_allocated"
CAPS = ("daily cap", "weekly cap", "monthly cap")


def nairobi_day(now_utc: datetime) -> str:
    """The Nairobi calendar day (YYYY-MM-DD) of an aware time. A naive time is refused: guessing a zone is the UTC mistake."""
    if now_utc.tzinfo is None:
        raise ValueError("the time must carry a zone")
    return now_utc.astimezone(NAIROBI).date().isoformat()


def days_left_in_week(now_utc: datetime) -> int:
    """Days left in the Nairobi week, today included (the week starts on Monday): 7 on a Monday, 1 on a Sunday."""
    if now_utc.tzinfo is None:
        raise ValueError("the time must carry a zone")
    return 7 - now_utc.astimezone(NAIROBI).weekday()


def _pct(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
        raise ValueError("a share is a whole percent from 1 to 100")
    return value


def shares_ok(existing: list, new_share: int, reserve_pct: int = DEFAULT_RESERVE_PCT) -> tuple:
    """(True, None), or (False, "share_over_allocated") when the shares of the goals on one provider plus the new one pass 100 - reserve."""
    _pct(new_share)
    if not isinstance(reserve_pct, int) or isinstance(reserve_pct, bool) or not 0 <= reserve_pct <= 99:
        raise ValueError("the reserve is a whole percent from 0 to 99")
    total = sum(_pct(s) for s in existing) + new_share
    return (True, None) if total <= 100 - reserve_pct else (False, OVER_ALLOCATED)


def caps(share_pct: int, month_allowance_uu: int, weekly_allowance_uu: int | None, daily_share_uu: int | None,
         used_month_uu: int = 0, used_week_uu: int = 0, weeks_left: int = 1, days_left: int = 7, horizon_days: int = 30) -> dict:
    """The three caps of a goal, whole and rounded down: the full ones (an empty window) and what is left after what the goal has used.

    `weekly_allowance_uu` None (free credits) means the month's allowance spread over `horizon_days`, per 7 days. `daily_share_uu` None
    (no pacing for this provider) means no daily ceiling beyond the weekly cap spread over the days left."""
    share = _pct(share_pct)
    for name, v in (("month allowance", month_allowance_uu), ("used this month", used_month_uu), ("used this week", used_week_uu)):
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ValueError(f"{name} is a whole number of UU, 0 or more")
    if weekly_allowance_uu is None:
        weekly_allowance_uu = month_allowance_uu * 7 // max(1, horizon_days)
    weeks_left, days_left = max(1, weeks_left), max(1, min(7, days_left))
    monthly = month_allowance_uu * share // 100
    monthly_left = max(0, monthly - used_month_uu)
    weekly_full = min(weekly_allowance_uu * share // 100, monthly // max(1, weeks_left))
    weekly = min(weekly_allowance_uu * share // 100, monthly_left // weeks_left)
    weekly_left = max(0, weekly - used_week_uu)
    daily_full = weekly_full // 7 if daily_share_uu is None else min(weekly_full // 7, max(0, daily_share_uu))
    daily = weekly_left // days_left if daily_share_uu is None else min(weekly_left // days_left, max(0, daily_share_uu))
    return {"daily_full": daily_full, "daily_left": daily, "weekly_left": weekly_left, "monthly_left": monthly_left}


def cap_gate(estimate_uu: int, c: dict, used_today_uu: int = 0) -> tuple:
    """(decision, reason) for a task of `estimate_uu` UU against the caps of `caps`.

    ("yes", None): it fits all three. ("wait", "daily cap" | "weekly cap" | "monthly cap"): the WIDEST window it does not fit, because that
    is how long it must wait (a task over the week's room waits for the next week, not for tomorrow); the task stays in the queue until
    that window opens. ("refuse", "task_larger_than_cap"): it is larger than an empty daily window, so no day would
    ever let it run; it goes to the owner."""
    if not isinstance(estimate_uu, int) or isinstance(estimate_uu, bool) or estimate_uu < 0:
        raise ValueError("an estimate is a whole number of UU, 0 or more")
    if estimate_uu > c["daily_full"]:
        return "refuse", TOO_BIG
    if estimate_uu > c["monthly_left"]:
        return "wait", "monthly cap"
    if estimate_uu > c["weekly_left"]:
        return "wait", "weekly cap"
    if estimate_uu > max(0, c["daily_left"] - max(0, used_today_uu)):
        return "wait", "daily cap"
    return "yes", None


def log_line(decision: str, reason: str | None, goal: str) -> str:
    """The logbook line of a decision: the goal's name is a label the owner wrote, shown once and never the estimate's source."""
    if decision == "yes":
        return f"goal {goal}: fits its share, the task may start"
    if decision == "wait":
        return f"goal {goal}: waiting, {reason}"
    return f"goal {goal}: refused, {reason}"
