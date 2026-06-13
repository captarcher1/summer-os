import subprocess
import threading
import time
from datetime import date
from flask import Blueprint, render_template, jsonify
from services.scheduler import generate_schedule, get_schedule
from services.xp_engine import get_daily_xp, get_weekly_xp, get_level, calculate_gaming_hours, get_current_streak
from services.xp_engine import get_weekly_xp
from services.balance_detector import analyse_week
from services.ai_engine import get_ai_client
from database.models import get_db

dashboard_bp = Blueprint("dashboard", __name__)

# ---------------------------------------------------------------------------
# Warmup state — shared across requests
# ---------------------------------------------------------------------------
_warmup = {
    "status":  "idle",   # idle | warming | ready | error
    "message": "Not started",
    "step":    0,        # 0=init 1=ollama_starting 2=model_loading 3=schedule 4=done
    "lock":    threading.Lock(),
}


def _set(status, message, step=None):
    _warmup["status"]  = status
    _warmup["message"] = message
    if step is not None:
        _warmup["step"] = step


def _start_ollama_process():
    """Launch `ollama serve` as a detached background process."""
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return True
    except FileNotFoundError:
        return False


def _run_warmup(app):
    """
    Background thread — runs inside a pushed app context so Flask
    services (config, DB) are available throughout.
    Four real stages:
      1. Check / start Ollama process
      2. Wait for Ollama API to respond
      3. Trigger first inference (model load into VRAM)
      4. Generate today's schedule
    """
    with app.app_context():
        today = date.today()
        try:
            # ── Stage 1: Check Ollama ──────────────────────────
            _set("warming", "Checking if Ollama is running…", step=1)
            ai = get_ai_client()

            if not ai.is_available():
                _set("warming", "Ollama not running — starting it now…", step=1)
                launched = _start_ollama_process()
                if not launched:
                    _set("error", "Ollama not found. Install from https://ollama.com then restart.")
                    return

                # ── Stage 2: Wait for Ollama to come up ───────
                _set("warming", "Waiting for Ollama to initialise…", step=2)
                for _ in range(30):          # up to 60 seconds
                    time.sleep(2)
                    if ai.is_available():
                        break
                else:
                    _set("error", "Ollama did not start in time. Try running `ollama serve` manually.")
                    return

            # ── Stage 3: Warm the model (first call = slow) ───
            _set("warming", "Ollama is online — loading qwen3.5:9b into memory…", step=3)
            ai._chat(
                "You are a scheduler.",
                "Reply with one word: ready",
                temperature=0.0,
            )

            # ── Stage 4: Generate schedule ─────────────────────
            _set("warming", "Model loaded — generating today's schedule…", step=4)
            generate_schedule(today, force_ai=True)

            # ── Stage 5: Generate 5 new finance lessons ────────────
            _set("warming", "Adding new finance lessons…", step=4)
            _add_finance_lessons(ai)

            _set("ready", "AI engine ready", step=4)

        except Exception as exc:
            _set("error", f"Unexpected error: {exc}")


# ---------------------------------------------------------------------------
# Page routes — all return instantly
# -----------------------------------------------------------------------------------


@dashboard_bp.route("/")
def index():
    return render_template("dashboard.html", today=date.today())


@dashboard_bp.route("/week")
def week():
    return render_template("week.html")


@dashboard_bp.route("/finance-page")
def finance_page():
    return render_template("finance.html")


@dashboard_bp.route("/rewards")
def rewards():
    return render_template("rewards.html")


@dashboard_bp.route("/parent-page")
def parent_page():
    return render_template("parent.html")


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@dashboard_bp.route("/api/warmup", methods=["POST"])
def api_warmup():
    """Kick off background warmup. Idempotent — ignores duplicate calls."""
    from flask import current_app
    app = current_app._get_current_object()   # capture real app, safe to pass to threads
    with _warmup["lock"]:
        if _warmup["status"] in ("idle", "error"):
            _set("warming", "Starting up…", step=0)
            threading.Thread(target=_run_warmup, args=(app,), daemon=True).start()
    return jsonify({"status": _warmup["status"], "message": _warmup["message"], "step": _warmup["step"]})


@dashboard_bp.route("/api/ai-status")
def api_ai_status():
    """Polled by the frontend every 2s to track warmup progress."""
    return jsonify({"status": _warmup["status"], "message": _warmup["message"], "step": _warmup["step"]})


@dashboard_bp.route("/api/daily-quotes")
def api_daily_quotes():
    """Return all stored quotes for the startup banner rotation."""
    db   = get_db()
    rows = db.execute(
        "SELECT quote, author FROM daily_quotes ORDER BY created_at DESC LIMIT 30"
    ).fetchall()
    # Reverse so oldest-first for a natural reading order, then shuffle on client
    return jsonify([{"quote": r["quote"], "author": r["author"]} for r in reversed(rows)])


@dashboard_bp.route("/api/daily-quote")
def api_daily_quote():
    """Generate a fresh fun quote via Ollama, store it in DB, and return it."""
    from database.models import get_student_context
    ctx = get_student_context()
    ai  = get_ai_client()
    result = ai.generate_daily_quote(ctx["name"], ctx["age"], ctx["gender"])

    quote  = result.get("quote", "").strip()
    author = result.get("author", "").strip()

    if quote:
        db = get_db()
        # Avoid storing exact duplicates
        exists = db.execute(
            "SELECT id FROM daily_quotes WHERE quote = ?", (quote,)
        ).fetchone()
        if not exists:
            db.execute(
                "INSERT INTO daily_quotes(quote, author) VALUES(?,?)",
                (quote, author),
            )
            db.commit()

    return jsonify(result)


@dashboard_bp.route("/guide")
def guide():
    return render_template("howto.html")


@dashboard_bp.route("/api/today")
def api_today():
    today     = date.today()
    schedule  = get_schedule(today)
    daily_xp  = get_daily_xp()
    weekly_xp = get_weekly_xp()
    level     = get_level()
    streak    = get_current_streak()
    balance   = analyse_week()

    return jsonify({
        "schedule":     schedule,
        "daily_xp":     daily_xp,
        "weekly_xp":    weekly_xp,
        "level":        level,
        "streak":       streak,
        "gaming_hours": calculate_gaming_hours(daily_xp),
        "balance":      balance,
    })


def _add_finance_lessons(ai):
    """Generate 5 new AI finance lessons and insert them if not already in the DB."""
    try:
        from database.models import get_db
        db = get_db()
        rows = db.execute(
            "SELECT lesson_key, title FROM finance_lessons"
        ).fetchall()
        existing_keys   = {r["lesson_key"] for r in rows}
        existing_titles = [r["title"] for r in rows]

        new_lessons = ai.generate_finance_lessons(existing_titles)
        added = 0
        for lesson in new_lessons:
            key   = lesson.get("lesson_key", "").strip()
            title = lesson.get("title", "").strip()
            tier  = int(lesson.get("tier", 1))
            if not key or not title:
                continue
            if key in existing_keys:
                continue
            db.execute(
                "INSERT OR IGNORE INTO finance_lessons"
                "(lesson_key, tier, title, sort_order) VALUES(?,?,?,?)",
                (key, tier, title, 1000 + added),
            )
            existing_keys.add(key)
            added += 1
        if added:
            db.commit()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Finance lesson generation failed: %s", exc)
