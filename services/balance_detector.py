"""
Balance detector — analyses logs to spot burnout, overruns, and category neglect.
Returns structured flags that feed into the AI scheduler and parent alerts.
"""

from datetime import date, timedelta
from database.models import get_db


CATEGORY_TARGETS = {
    "sports":    3,   # sessions per week
    "finance":   4,
    "education": 3,
    "household": 4,
    "family":    2,
}

GAMING_OVERRUN_THRESHOLD = 1.15  # 15% over earned hours = flag


def analyse_week(week_start: date = None) -> dict:
    """
    Full weekly balance analysis.
    Returns: {"flags": [...], "balance_score": int, "breakdown": {...}, "weakest": str, "strongest": str}
    """
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=6)
    db = get_db()

    logs = db.execute(
        """
        SELECT dl.activity_key, dl.completed, a.category, a.xp_value
        FROM daily_log dl
        JOIN activities a ON a.key = dl.activity_key
        WHERE dl.log_date BETWEEN ? AND ? AND dl.completed = 1
        """,
        (str(week_start), str(week_end)),
    ).fetchall()

    flags = []
    breakdown = {}

    for row in logs:
        cat = row["category"]
        breakdown[cat] = breakdown.get(cat, 0) + 1

    # Check category minimums
    for category, target in CATEGORY_TARGETS.items():
        actual = breakdown.get(category, 0)
        if actual < target:
            flags.append({
                "type":     "low_category",
                "category": category,
                "message":  f"{category.title()} below target: {actual}/{target} sessions this week",
                "severity": "warning" if actual >= target // 2 else "alert",
            })

    # Check gaming overrun
    gaming_flag = _check_gaming_overrun(week_start, week_end, db)
    if gaming_flag:
        flags.append(gaming_flag)

    # Check consecutive missed days
    missed_flag = _check_missed_days(week_start, week_end, db)
    if missed_flag:
        flags.append(missed_flag)

    balance_score = _compute_balance_score(breakdown, flags)
    cats_sorted = sorted(CATEGORY_TARGETS, key=lambda c: breakdown.get(c, 0))

    return {
        "flags":            flags,
        "balance_score":    balance_score,
        "breakdown":        breakdown,
        "weakest_category": cats_sorted[0] if cats_sorted else None,
        "strongest_category": cats_sorted[-1] if cats_sorted else None,
    }


def get_today_flags() -> list:
    """Quick daily check — returns flags for the AI coach note."""
    today = date.today()
    db = get_db()
    flags = []

    # Gaming overrun today
    gaming_flag = _check_gaming_overrun(today, today, db)
    if gaming_flag:
        flags.append(gaming_flag)

    # No movement logged by midday (heuristic — check if it's after 12)
    hour = date.today().timetuple().tm_hour  # use current hour
    movement = db.execute(
        "SELECT COUNT(*) AS cnt FROM daily_log WHERE log_date = ? AND category IN ('sports') AND completed = 1",
        (str(today),),
    ).fetchone()
    if hour >= 12 and movement and movement["cnt"] == 0:
        flags.append({
            "type":     "no_movement",
            "message":  "No movement logged yet today",
            "severity": "warning",
        })

    return flags


def suggest_rebalance(flags: list) -> list:
    """
    Given a list of flags, return suggested schedule adjustments.
    Used by the scheduler to auto-correct tomorrow's plan.
    """
    suggestions = []
    for flag in flags:
        if flag["type"] == "low_category":
            cat = flag["category"]
            suggestions.append({
                "action":   "add_activity",
                "category": cat,
                "message":  f"Add an extra {cat} session tomorrow to catch up",
            })
        elif flag["type"] == "gaming_overrun":
            suggestions.append({
                "action":  "reduce_gaming",
                "message": "Trim tomorrow's gaming window by 1 hour to rebalance",
            })
    return suggestions


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_gaming_overrun(start, end, db) -> dict | None:
    from services.xp_engine import get_daily_xp, calculate_gaming_hours

    # Sum XP earned on days in range
    xp_row = db.execute(
        "SELECT COALESCE(SUM(xp_delta), 0) AS total FROM xp_ledger WHERE txn_date BETWEEN ? AND ?",
        (str(start), str(end)),
    ).fetchone()
    total_xp = xp_row["total"] if xp_row else 0

    # Approximate earned gaming hours for the period
    # (simplified: use avg daily XP → hours per day × days)
    days = max((date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days + 1, 1)
    avg_daily_xp = total_xp / days
    earned_hrs_per_day = calculate_gaming_hours(int(avg_daily_xp))
    earned_total = earned_hrs_per_day * days

    # Actual gaming sessions logged
    gaming_sessions = db.execute(
        "SELECT COUNT(*) AS cnt FROM daily_log WHERE log_date BETWEEN ? AND ? AND activity_key = 'gaming' AND completed = 1",
        (str(start), str(end)),
    ).fetchone()
    actual_sessions = gaming_sessions["cnt"] if gaming_sessions else 0

    # Each session assumed 2 hr avg if we don't have duration data
    actual_hrs = actual_sessions * 2.0

    if earned_total > 0 and actual_hrs > earned_total * GAMING_OVERRUN_THRESHOLD:
        return {
            "type":     "gaming_overrun",
            "message":  f"Gaming {round(actual_hrs, 1)}h vs {round(earned_total, 1)}h earned",
            "severity": "warning",
        }
    return None


def _check_missed_days(start, end, db) -> dict | None:
    """Flag if 2+ consecutive days have zero completed activities."""
    rows = db.execute(
        "SELECT log_date, COUNT(*) AS cnt FROM daily_log WHERE log_date BETWEEN ? AND ? AND completed = 1 GROUP BY log_date",
        (str(start), str(end)),
    ).fetchall()
    active_days = {row["log_date"] for row in rows}

    today = date.today()
    check_end = min(date.fromisoformat(str(end)), today)
    check_start = date.fromisoformat(str(start))

    consecutive = 0
    max_consecutive = 0
    d = check_start
    while d <= check_end:
        if str(d) not in active_days:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0
        d += timedelta(days=1)

    if max_consecutive >= 2:
        return {
            "type":     "consecutive_misses",
            "message":  f"{max_consecutive} consecutive days with no activity logged",
            "severity": "alert",
        }
    return None


def _compute_balance_score(breakdown: dict, flags: list) -> int:
    """
    0–100 score.
    Start at 100, subtract per flag severity.
    """
    score = 100
    for flag in flags:
        if flag["severity"] == "alert":
            score -= 15
        elif flag["severity"] == "warning":
            score -= 8
    return max(0, min(100, score))
