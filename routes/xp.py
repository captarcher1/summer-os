from flask import Blueprint, request, jsonify
from services.xp_engine import (
    log_activity_complete, award_bonus_xp,
    get_daily_xp, get_total_xp, get_weekly_xp,
    get_level, calculate_gaming_hours, get_current_streak, use_streak_freeze,
)

xp_bp = Blueprint("xp", __name__)


@xp_bp.route("/log", methods=["POST"])
def log_activity():
    """POST /xp/log  body: {"activity_key": "taekwondo", "notes": "..."}"""
    data = request.get_json(silent=True) or {}
    key = data.get("activity_key")
    if not key:
        return jsonify({"error": "activity_key required"}), 400

    result = log_activity_complete(key, notes=data.get("notes", ""))
    return jsonify(result)


@xp_bp.route("/status")
def status():
    from database.models import get_setting
    daily_xp  = get_daily_xp()
    total_xp  = get_total_xp()
    weekly_xp = get_weekly_xp()
    level     = get_level(total_xp)
    streak    = get_current_streak()

    return jsonify({
        "daily_xp":      daily_xp,
        "weekly_xp":     weekly_xp,
        "total_xp":      total_xp,
        "level":         level,
        "streak":        streak,
        "gaming_hours":  calculate_gaming_hours(daily_xp),
        "student_name":  get_setting("student_name", "Player"),
    })


@xp_bp.route("/freeze", methods=["POST"])
def freeze():
    """Use a streak freeze."""
    result = use_streak_freeze()
    return jsonify(result)


@xp_bp.route("/bonus", methods=["POST"])
def bonus():
    """POST /xp/bonus  body: {"amount": 100, "reason": "..."}  (parent use only)"""
    data = request.get_json(silent=True) or {}
    amount = data.get("amount")
    reason = data.get("reason", "Parent bonus")
    if not amount:
        return jsonify({"error": "amount required"}), 400
    total = award_bonus_xp(int(amount), reason)
    return jsonify({"total_xp": total, "awarded": amount})
