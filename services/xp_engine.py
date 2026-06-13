"""
XP engine — earning, levelling, streaks, and gaming hour unlocks.
All write operations commit immediately; reads are side-effect-free.
"""

from datetime import date, timedelta
from database.models import get_db
from flask import current_app


# ---------------------------------------------------------------------------
# XP earning
# ---------------------------------------------------------------------------

def log_activity_complete(activity_key: str, notes: str = "") -> dict:
    """
    Mark an activity as complete for today.
    Awards XP, checks for streak update.
    Returns {"xp_earned": int, "total_today": int, "gaming_hours": float, "level": int}
    """
    db = get_db()

    activity = db.execute(
        "SELECT * FROM activities WHERE key = ? AND is_active = 1",
        (activity_key,),
    ).fetchone()

    if not activity:
        return {"error": f"Unknown activity: {activity_key}"}

    today = str(date.today())

    # Upsert the daily_log entry
    existing = db.execute(
        "SELECT id, completed FROM daily_log WHERE log_date = ? AND activity_key = ?",
        (today, activity_key),
    ).fetchone()

    if existing and existing["completed"] == 1:
        return {"error": "Already logged today", "already_done": True}

    if existing:
        db.execute(
            "UPDATE daily_log SET completed = 1, notes = ?, logged_at = datetime('now') WHERE id = ?",
            (notes, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO daily_log(log_date, activity_key, completed, notes) VALUES(?,?,1,?)",
            (today, activity_key, notes),
        )

    xp = activity["xp_value"]
    db.execute(
        "INSERT INTO xp_ledger(txn_date, activity_key, xp_delta, reason) VALUES(?,?,?,?)",
        (today, activity_key, xp, f"Completed: {activity['label']}"),
    )

    db.commit()

    daily_xp = get_daily_xp()
    total_xp  = get_total_xp()
    _update_streak(today, daily_xp)

    return {
        "xp_earned":     xp,
        "total_today":   daily_xp,
        "gaming_hours":  calculate_gaming_hours(daily_xp),
        "level":         get_level(total_xp),
        "total_xp":      total_xp,
    }


def award_bonus_xp(amount: int, reason: str) -> int:
    """Award arbitrary XP (streak bonus, parent reward, etc.)."""
    db = get_db()
    today = str(date.today())
    db.execute(
        "INSERT INTO xp_ledger(txn_date, xp_delta, reason) VALUES(?,?,?)",
        (today, amount, reason),
    )
    db.commit()
    return get_total_xp()


# ---------------------------------------------------------------------------
# XP reads
# ---------------------------------------------------------------------------

def get_daily_xp(for_date: date = None) -> int:
    target = str(for_date or date.today())
    db = get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(xp_delta), 0) AS total FROM xp_ledger WHERE txn_date = ?",
        (target,),
    ).fetchone()
    return row["total"]


def get_total_xp() -> int:
    db = get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(xp_delta), 0) AS total FROM xp_ledger"
    ).fetchone()
    return row["total"]


def get_weekly_xp(week_start: date = None) -> int:
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    db = get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(xp_delta), 0) AS total FROM xp_ledger WHERE txn_date BETWEEN ? AND ?",
        (str(week_start), str(week_end)),
    ).fetchone()
    return row["total"]


def get_level(total_xp: int = None) -> dict:
    if total_xp is None:
        total_xp = get_total_xp()
    xp_per_level = current_app.config.get("XP_PER_LEVEL", 1000)
    level   = (total_xp // xp_per_level) + 1
    xp_in   = total_xp % xp_per_level
    xp_next = xp_per_level - xp_in
    pct     = round((xp_in / xp_per_level) * 100)
    return {
        "level":       level,
        "xp_in_level": xp_in,
        "xp_to_next":  xp_next,
        "pct_complete": pct,
        "total_xp":    total_xp,
    }


# ---------------------------------------------------------------------------
# Gaming hour unlock
# ---------------------------------------------------------------------------

def calculate_gaming_hours(daily_xp: int = None) -> float:
    """Convert today's XP into earned gaming hours using configured tiers."""
    if daily_xp is None:
        daily_xp = get_daily_xp()

    tiers = current_app.config.get("GAMING_TIERS", [
        (0,    0.0), (300, 1.0), (500, 1.5),
        (800,  2.5), (1000, 3.0), (1200, 3.5),
    ])
    cap = float(current_app.config.get("GAMING_CAP_DAILY", 4.0))

    hours = 0.0
    for threshold, unlock in reversed(tiers):
        if daily_xp >= threshold:
            hours = unlock
            break

    return min(hours, cap)


# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------

def get_current_streak() -> dict:
    db = get_db()
    today = date.today()

    rows = db.execute(
        "SELECT streak_date, target_met, freeze_used FROM streaks ORDER BY streak_date DESC LIMIT 30"
    ).fetchall()

    streak = 0
    for row in rows:
        if row["target_met"] == 1 or row["freeze_used"] == 1:
            streak += 1
        else:
            break

    return {
        "current_streak": streak,
        "freeze_available": _count_available_freezes(rows),
    }


def _count_available_freezes(rows) -> int:
    """Simple rule: 1 freeze per 7-day completed streak, max 3."""
    completed_weeks = sum(1 for r in rows[:14] if r["target_met"]) // 7
    return min(completed_weeks, 3)


def use_streak_freeze() -> dict:
    """Spend a streak freeze to protect today's streak."""
    db = get_db()
    today = str(date.today())
    streak_info = get_current_streak()

    if streak_info["freeze_available"] < 1:
        return {"error": "No streak freezes available"}

    db.execute(
        "INSERT OR REPLACE INTO streaks(streak_date, daily_xp, target_met, freeze_used) VALUES(?,?,0,1)",
        (today, get_daily_xp()),
    )
    # Charge XP cost
    db.execute(
        "INSERT INTO xp_ledger(txn_date, xp_delta, reason) VALUES(?,?,'Streak freeze used')",
        (today, -50),
    )
    db.commit()
    return {"success": True, "streaks": get_current_streak()}


def _update_streak(today: str, daily_xp: int):
    db = get_db()
    target = current_app.config.get("DAILY_XP_TARGET", 800)
    met = 1 if daily_xp >= target else 0
    db.execute(
        "INSERT OR REPLACE INTO streaks(streak_date, daily_xp, target_met) VALUES(?,?,?)",
        (today, daily_xp, met),
    )

    # Award 7-day streak bonus
    streak_info = get_current_streak()
    if streak_info["current_streak"] > 0 and streak_info["current_streak"] % 7 == 0:
        bonus = current_app.config.get("XP_RATES", {}).get("streak_7day", 500)
        db.execute(
            "INSERT INTO xp_ledger(txn_date, xp_delta, reason) VALUES(?,?,?)",
            (today, bonus, "7-day streak bonus!"),
        )

    db.commit()
