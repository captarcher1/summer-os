from flask import Blueprint, request, jsonify, session
from database.models import get_db, get_setting, upsert_setting, get_student_context
from services.balance_detector import analyse_week
from services.xp_engine import get_weekly_xp, get_total_xp, get_level, get_current_streak
from services.ai_engine import get_ai_client

parent_bp = Blueprint("parent", __name__)


def _verify_pin(provided: str) -> bool:
    stored = get_setting("parent_pin", "1234")
    return provided == stored


@parent_bp.route("/verify", methods=["POST"])
def verify():
    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin", ""))
    if _verify_pin(pin):
        session["parent_auth"] = True
        return jsonify({"authenticated": True})
    return jsonify({"authenticated": False, "error": "Wrong PIN"}), 401


@parent_bp.route("/dashboard")
def dashboard():
    balance   = analyse_week()
    weekly_xp = get_weekly_xp()
    total_xp  = get_total_xp()
    level     = get_level(total_xp)
    streak    = get_current_streak()

    db = get_db()
    # Compliance: completed / (completed + pending) for this week
    from datetime import date, timedelta
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    logs = db.execute(
        "SELECT completed, COUNT(*) AS cnt FROM daily_log WHERE log_date >= ? GROUP BY completed",
        (str(week_start),),
    ).fetchall()

    done = sum(r["cnt"] for r in logs if r["completed"] == 1)
    total_logged = sum(r["cnt"] for r in logs)
    compliance = round((done / total_logged * 100)) if total_logged > 0 else 0

    # Recent coach notes / alerts
    notes = db.execute(
        "SELECT * FROM coach_notes ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    xp_per_dollar  = float(get_setting("xp_per_dollar", "500"))
    dollars_earned = round(total_xp / xp_per_dollar, 2) if xp_per_dollar > 0 else 0

    return jsonify({
        "weekly_xp":     weekly_xp,
        "total_xp":      total_xp,
        "level":         level,
        "streak":        streak,
        "compliance":    compliance,
        "balance":       balance,
        "coach_notes":   [dict(n) for n in notes],
        "dollars_earned": dollars_earned,
        "settings": {
            "gaming_cap_daily":   get_setting("gaming_cap_daily",   "4.0"),
            "weekend_xp_minimum": get_setting("weekend_xp_minimum", "400"),
            "student_name":       get_setting("student_name",        "Player"),
            "student_age":        get_setting("student_age",         "15"),
            "student_gender":     get_setting("student_gender",      "unspecified"),
            "xp_per_dollar":      get_setting("xp_per_dollar",       "500"),
        },
    })


@parent_bp.route("/settings", methods=["POST"])
def update_settings():
    """POST /parent/settings  body: {"gaming_cap_daily":"3.5","weekend_xp_minimum":"500"}"""
    data = request.get_json(silent=True) or {}
    allowed = {
        "gaming_cap_daily", "weekend_xp_minimum", "student_name",
        "weekend_mode", "ai_coach_enabled",
        "student_age", "student_gender", "xp_per_dollar",
    }
    updated = {}
    for key, val in data.items():
        if key in allowed:
            upsert_setting(key, str(val))
            updated[key] = val
    return jsonify({"updated": updated})


@parent_bp.route("/bonus-xp", methods=["POST"])
def bonus_xp():
    """Award or deduct XP manually. body: {"amount": 200, "reason": "great attitude"}"""
    data = request.get_json(silent=True) or {}
    amount = data.get("amount")
    reason = data.get("reason", "Parent award")
    if amount is None:
        return jsonify({"error": "amount required"}), 400
    from services.xp_engine import award_bonus_xp
    total = award_bonus_xp(int(amount), reason)
    return jsonify({"awarded": amount, "total_xp": total})


@parent_bp.route("/week-review", methods=["GET"])
def week_review():
    """AI-generated parent weekly summary."""
    balance   = analyse_week()
    weekly_xp = get_weekly_xp()
    streak    = get_current_streak()

    db = get_db()
    from datetime import date, timedelta
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    logs = db.execute(
        "SELECT completed, COUNT(*) AS cnt FROM daily_log WHERE log_date >= ? GROUP BY completed",
        (str(week_start),),
    ).fetchall()
    done  = sum(r["cnt"] for r in logs if r["completed"] == 1)
    total = sum(r["cnt"] for r in logs)

    week_data = {
        "total_xp":             weekly_xp,
        "compliance_pct":       round((done / total * 100)) if total else 0,
        "breakdown":            balance["breakdown"],
        "balance_score":        balance["balance_score"],
        "alerts":               [f["message"] for f in balance["flags"]],
        "gaming_vs_earned_pct": 112,   # TODO: wire real gaming overrun calc
        "finance_progress": {},
    }

    ai  = get_ai_client()
    ctx = get_student_context()
    summary = ai.generate_week_review(week_data, ctx["name"], ctx["age"], ctx["gender"])
    return jsonify({"summary": summary, "data": week_data})


@parent_bp.route("/xp-rates", methods=["GET"])
def get_xp_rates():
    """Return current XP value for each activity."""
    db = get_db()
    rows = db.execute(
        "SELECT key, label, category, xp_value FROM activities WHERE is_active = 1 ORDER BY category, label"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@parent_bp.route("/xp-rates", methods=["POST"])
def update_xp_rates():
    """
    POST /parent/xp-rates
    body: {"taekwondo": 150, "chores": 600, ...}
    """
    data = request.get_json(silent=True) or {}
    db = get_db()
    updated = {}
    for key, value in data.items():
        try:
            xp = int(value)
            db.execute(
                "UPDATE activities SET xp_value = ? WHERE key = ?",
                (xp, key),
            )
            updated[key] = xp
        except (ValueError, TypeError):
            continue
    db.commit()
    return jsonify({"updated": updated})


@parent_bp.route("/reset", methods=["POST"])
def reset_app():
    """
    POST /parent/reset
    body: {"pin": "1234", "categories": ["xp_ledger", "daily_logs", ...]}
    Selectively wipes progress based on requested categories.
    Pass "all" in categories (or omit) to wipe everything.

    Valid categories:
      xp_ledger       — XP transaction ledger
      daily_logs      — daily activity log + AI coach notes
      streaks         — streak history
      schedules       — generated schedule blocks
      finance_trades  — paper trades + portfolio holdings
      lesson_progress — lesson completion flags (keeps titles & content)
    """
    data       = request.get_json(silent=True) or {}
    pin        = str(data.get("pin", ""))
    categories = data.get("categories", ["all"])

    if not _verify_pin(pin):
        return jsonify({"success": False, "error": "Incorrect PIN"}), 401

    if not categories:
        return jsonify({"success": False, "error": "Select at least one category to reset"}), 400

    # Normalise: "all" expands to every category
    ALL_CATS = {"xp_ledger", "daily_logs", "streaks", "schedules", "finance_trades", "lesson_progress"}
    if "all" in categories:
        selected = ALL_CATS
    else:
        selected = ALL_CATS & set(categories)   # ignore unknown values

    if not selected:
        return jsonify({"success": False, "error": "No valid categories selected"}), 400

    db  = get_db()
    ops = []   # human-readable summary for the response

    if "xp_ledger" in selected:
        db.execute("DELETE FROM xp_ledger")
        ops.append("XP ledger")

    if "daily_logs" in selected:
        db.execute("DELETE FROM daily_log")
        db.execute("DELETE FROM coach_notes")
        ops.append("daily logs & coach notes")

    if "streaks" in selected:
        db.execute("DELETE FROM streaks")
        ops.append("streaks")

    if "schedules" in selected:
        db.execute("DELETE FROM schedule_blocks")
        ops.append("schedules")

    if "finance_trades" in selected:
        db.execute("DELETE FROM finance_trades")
        db.execute("DELETE FROM finance_holdings")
        ops.append("finance trades & portfolio")

    if "lesson_progress" in selected:
        db.execute(
            "UPDATE finance_lessons SET completed = 0, completed_at = NULL, quiz_passed = 0"
        )
        ops.append("lesson completion flags")

    db.commit()
    return jsonify({
        "success": True,
        "cleared": list(selected),
        "message": "Reset complete — cleared: " + ", ".join(ops) + ". Lesson content & settings preserved.",
    })


@parent_bp.route("/generate-lessons", methods=["POST"])
def generate_lessons():
    """
    POST /parent/generate-lessons
    body: {"tier": 1|2|3}
    Calls Ollama to generate 5 new lessons for the selected tier and inserts them.
    Returns: {added: int, lessons: [...]}
    """
    data = request.get_json(silent=True) or {}
    tier = int(data.get("tier", 1))
    if tier not in (1, 2, 3):
        return jsonify({"error": "tier must be 1, 2, or 3"}), 400

    db = get_db()
    # Collect ALL existing keys (not just this tier) to avoid cross-tier key collisions
    all_existing = db.execute("SELECT lesson_key, title, tier FROM finance_lessons").fetchall()
    existing_titles = [r["title"] for r in all_existing if r["tier"] == tier]
    existing_keys   = {r["lesson_key"] for r in all_existing}

    # Current max sort_order for this tier
    max_order_row = db.execute(
        "SELECT MAX(sort_order) AS mo FROM finance_lessons WHERE tier = ?", (tier,)
    ).fetchone()
    next_order = (max_order_row["mo"] or 0) + 1

    ai  = get_ai_client()
    # Pass existing_keys so ai_engine can pre-filter before returning
    new = ai.generate_finance_lessons(existing_titles, existing_keys=existing_keys, target=5)

    added   = []
    db_skipped = 0   # only counts DB-level failures (e.g. constraint errors)
    for lesson in new:
        key   = lesson.get("lesson_key", "").strip().lower().replace(" ", "_")
        title = lesson.get("title", "").strip()
        if not key or not title:
            continue
        try:
            db.execute(
                "INSERT INTO finance_lessons(sort_order, lesson_key, tier, title) VALUES(?,?,?,?)",
                (next_order, key, tier, title),
            )
            existing_keys.add(key)
            added.append({"lesson_key": key, "title": title, "tier": tier})
            next_order += 1
        except Exception:
            db_skipped += 1

    db.commit()
    return jsonify({"added": len(added), "lessons": added})


@parent_bp.route("/change-pin", methods=["POST"])
def change_pin():
    """
    POST /parent/change-pin
    body: {"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"}
    """
    data        = request.get_json(silent=True) or {}
    current_pin = str(data.get("current_pin", ""))
    new_pin     = str(data.get("new_pin", ""))
    confirm_pin = str(data.get("confirm_pin", ""))

    if not _verify_pin(current_pin):
        return jsonify({"success": False, "error": "Current PIN is incorrect"}), 401
    if len(new_pin) < 4:
        return jsonify({"success": False, "error": "New PIN must be at least 4 digits"}), 400
    if new_pin != confirm_pin:
        return jsonify({"success": False, "error": "New PIN and confirmation do not match"}), 400

    upsert_setting("parent_pin", new_pin)
    return jsonify({"success": True, "message": "PIN updated successfully"})
