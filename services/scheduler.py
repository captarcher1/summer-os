"""
Schedule generator — builds daily schedules using the AI engine + fallback templates.
Writes schedule_blocks to the DB.
"""

from datetime import date, timedelta
from database.models import get_db
from services.ai_engine import get_ai_client
from services.balance_detector import analyse_week, suggest_rebalance
from services.xp_engine import get_weekly_xp, get_current_streak

_FALLBACK_PHRASES = ("AI coach is offline", "ollama serve", "Start Ollama")

WEEKDAY_TEMPLATE = [
    ("sports",         "07:00", "07:30", 1, 1),
    ("finance_lesson", "09:00", "09:15", 1, 2),
    ("reading",        "10:00", "10:30", 1, 3),
    ("chores",         "11:00", "12:00", 1, 4),
    ("gaming",         "16:00", "18:30", 0, 5),
]

WEEKEND_TEMPLATE = [
    ("sports",         "09:00", "10:00", 0, 1),
    ("family_time",    "11:00", "12:00", 0, 2),
    ("finance_lesson", "13:00", "13:15", 0, 3),
    ("gaming",         "15:00", "18:00", 0, 4),
]


def generate_schedule(for_date: date = None, force_ai: bool = False) -> dict:
    target = for_date or date.today()
    db = get_db()

    # Skip if schedule already exists and not forced
    existing = db.execute(
        "SELECT COUNT(*) AS cnt FROM schedule_blocks WHERE block_date = ?",
        (str(target),),
    ).fetchone()
    if existing["cnt"] > 0 and not force_ai:
        return get_schedule(target)

    is_weekend = target.weekday() >= 5
    balance_data = analyse_week()
    flags = [f["message"] for f in balance_data["flags"]]
    suggestions = suggest_rebalance(balance_data["flags"])
    streak = get_current_streak()
    weekly_xp = get_weekly_xp()

    context = {
        "date":           str(target),
        "day_of_week":    target.strftime("%A"),
        "is_weekend":     is_weekend,
        "flags":          flags,
        "suggestions":    suggestions,
        "recent_xp":      weekly_xp,
        "streak":         streak["current_streak"],
        "weekly_xp":      weekly_xp,
        "gaming_cap":     _get_setting("gaming_cap_daily", "4.0"),
        "weekend_xp_min": _get_setting("weekend_xp_minimum", "400"),
    }

    ai = get_ai_client()
    coach_note = None
    blocks_raw = []

    if ai.is_available() or force_ai:
        result = ai.generate_daily_schedule(context)
        blocks_raw = result.get("blocks", [])
        raw_note   = result.get("coach_note", "")
        # Only store coach note if it is genuine AI output, not the offline fallback
        if raw_note and not any(phrase in raw_note for phrase in _FALLBACK_PHRASES):
            coach_note = raw_note

    if not blocks_raw:
        template = WEEKEND_TEMPLATE if is_weekend else WEEKDAY_TEMPLATE
        blocks_raw = [
            {"activity_key": k, "start_time": s, "end_time": e,
             "is_locked": lock, "sort_order": o}
            for k, s, e, lock, o in template
        ]

    # Wipe today's schedule + pending log entries before re-inserting
    db.execute("DELETE FROM schedule_blocks WHERE block_date = ?", (str(target),))
    db.execute(
        "DELETE FROM daily_log WHERE log_date = ? AND completed = 0",
        (str(target),),
    )

    seen_times = set()
    for b in blocks_raw:
        t = b["start_time"]
        if t in seen_times:          # deduplicate AI output by start_time
            continue
        seen_times.add(t)
        db.execute(
            "INSERT OR IGNORE INTO schedule_blocks"
            "(block_date, activity_key, start_time, end_time, is_locked, sort_order)"
            " VALUES(?,?,?,?,?,?)",
            (str(target), b["activity_key"], t, b["end_time"],
             b.get("is_locked", 1), b.get("sort_order", 0)),
        )

    # Seed pending daily_log entries (one per activity, skip gaming)
    for b in blocks_raw:
        if b["activity_key"] != "gaming":
            db.execute(
                "INSERT OR IGNORE INTO daily_log(log_date, activity_key, completed)"
                " VALUES(?,?,0)",
                (str(target), b["activity_key"]),
            )

    # Store coach note only if genuine
    if coach_note:
        db.execute(
            "DELETE FROM coach_notes WHERE note_date = ? AND note_type = 'daily_nudge'",
            (str(target),),
        )
        db.execute(
            "INSERT INTO coach_notes(note_date, note_type, content) VALUES(?,?,?)",
            (str(target), "daily_nudge", coach_note),
        )

    db.commit()
    return get_schedule(target)


def get_schedule(for_date: date = None) -> dict:
    """Return schedule blocks + latest coach note for a given date."""
    target = for_date or date.today()
    db = get_db()

    # Use correlated subquery instead of JOIN to avoid duplicate rows
    # when daily_log has multiple entries for the same activity on the same date
    blocks = db.execute(
        """
        SELECT sb.*,
               a.label, a.category, a.xp_value, a.icon, a.color_class,
               COALESCE(
                   (SELECT completed FROM daily_log
                    WHERE activity_key = sb.activity_key
                      AND log_date = sb.block_date
                    ORDER BY id DESC LIMIT 1),
                   0
               ) AS completed
        FROM schedule_blocks sb
        JOIN activities a ON a.key = sb.activity_key
        WHERE sb.block_date = ?
        ORDER BY sb.sort_order, sb.start_time
        """,
        (str(target),),
    ).fetchall()

    note = db.execute(
        "SELECT content FROM coach_notes"
        " WHERE note_date = ? AND note_type = 'daily_nudge'"
        " ORDER BY id DESC LIMIT 1",
        (str(target),),
    ).fetchone()

    return {
        "date":       str(target),
        "blocks":     [dict(b) for b in blocks],
        "coach_note": note["content"] if note else None,
    }


def generate_week_ahead(from_date: date = None):
    start = from_date or date.today()
    for i in range(7):
        generate_schedule(start + timedelta(days=i))


def _get_setting(key: str, default: str = "") -> str:
    try:
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default
    except Exception:
        return default
