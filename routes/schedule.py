from flask import Blueprint, request, jsonify
from datetime import date
from services.scheduler import generate_schedule, get_schedule, generate_week_ahead

schedule_bp = Blueprint("schedule", __name__)


@schedule_bp.route("/today")
def today():
    return jsonify(get_schedule(date.today()))


@schedule_bp.route("/date/<string:iso_date>")
def for_date(iso_date: str):
    try:
        d = date.fromisoformat(iso_date)
    except ValueError:
        return jsonify({"error": "Invalid date format, use YYYY-MM-DD"}), 400
    return jsonify(get_schedule(d))


@schedule_bp.route("/generate", methods=["POST"])
def generate():
    """POST /schedule/generate  body: {"date": "2025-06-10", "force": true}"""
    data = request.get_json(silent=True) or {}
    iso = data.get("date")
    target = date.fromisoformat(iso) if iso else date.today()
    force = bool(data.get("force", False))
    result = generate_schedule(target, force_ai=force)
    return jsonify(result)


@schedule_bp.route("/week", methods=["POST"])
def week_ahead():
    """Pre-generate the next 7 days."""
    generate_week_ahead()
    return jsonify({"status": "ok", "message": "Week ahead scheduled"})


@schedule_bp.route("/manual", methods=["POST"])
def manual():
    """
    POST /schedule/manual
    body: {"blocks": [{"activity_key":"sports","start_time":"07:00","end_time":"08:00"}, ...]}
    Saves a manually-built schedule for today, bypassing AI.
    """
    from database.models import get_db
    data   = request.get_json(silent=True) or {}
    blocks = data.get("blocks", [])
    if not blocks:
        return jsonify({"error": "blocks array required"}), 400

    target = str(date.today())
    db     = get_db()

    db.execute("DELETE FROM schedule_blocks WHERE block_date = ?", (target,))
    db.execute("DELETE FROM daily_log WHERE log_date = ? AND completed = 0", (target,))

    seen = set()
    for i, b in enumerate(blocks):
        key   = b.get("activity_key", "")
        start = b.get("start_time", "")
        end   = b.get("end_time", "")
        if not key or not start or start in seen:
            continue
        seen.add(start)
        db.execute(
            "INSERT OR IGNORE INTO schedule_blocks"
            "(block_date, activity_key, start_time, end_time, is_locked, sort_order)"
            " VALUES(?,?,?,?,0,?)",
            (target, key, start, end, i),
        )
        if key != "gaming":
            db.execute(
                "INSERT OR IGNORE INTO daily_log(log_date, activity_key, completed)"
                " VALUES(?,?,0)",
                (target, key),
            )
    db.commit()
    return jsonify(get_schedule(date.today()))


@schedule_bp.route("/activities")
def activities():
    """Return the list of available activities for the manual schedule builder."""
    from database.models import get_db
    db = get_db()
    rows = db.execute(
        "SELECT key, label, category, xp_value, icon, color_class"
        " FROM activities WHERE is_active = 1 ORDER BY category, label"
    ).fetchall()
    return jsonify([dict(r) for r in rows])
