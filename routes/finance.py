from flask import Blueprint, request, jsonify
from database.models import get_db, get_student_context
from services.market_data import get_quote, get_portfolio, execute_paper_trade, get_trade_history, get_price_history
from services.ai_engine import get_ai_client

finance_bp = Blueprint("finance", __name__)


@finance_bp.route("/portfolio")
def portfolio():
    return jsonify(get_portfolio())


@finance_bp.route("/quote/<string:symbol>")
def quote(symbol: str):
    return jsonify(get_quote(symbol))


@finance_bp.route("/history/<string:symbol>")
def history(symbol: str):
    period = request.args.get("period", "3mo")
    return jsonify(get_price_history(symbol, period))


@finance_bp.route("/trade", methods=["POST"])
def trade():
    """POST /finance/trade  body: {"symbol":"AAPL","action":"buy","shares":5,"notes":"..."}"""
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol")
    action = data.get("action")
    shares = data.get("shares")

    if not all([symbol, action, shares]):
        return jsonify({"error": "symbol, action, and shares are required"}), 400

    result = execute_paper_trade(symbol, action, float(shares), data.get("notes", ""))
    return jsonify(result)


@finance_bp.route("/trades")
def trades():
    limit = int(request.args.get("limit", 20))
    return jsonify(get_trade_history(limit))


@finance_bp.route("/lessons")
def lessons():
    db = get_db()
    # Return lessons without answer_index — frontend must not see correct answers
    rows = db.execute(
        "SELECT id, sort_order, lesson_key, tier, title, completed, completed_at, quiz_passed, "
        "CASE WHEN content IS NOT NULL THEN 1 ELSE 0 END as has_content "
        "FROM finance_lessons ORDER BY sort_order"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@finance_bp.route("/lessons/<string:lesson_key>/content")
def lesson_content(lesson_key: str):
    """
    On-demand lesson content generation.
    First call triggers Ollama and stores result; subsequent calls return cached DB value.
    Returns: {content, questions} — questions have NO answer_index (strips it for security).
    """
    import json as _json
    db = get_db()
    row = db.execute(
        "SELECT lesson_key, tier, title, content, questions FROM finance_lessons WHERE lesson_key = ?",
        (lesson_key,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Lesson not found"}), 404

    # Cache hit — content already generated
    if row["content"] and row["questions"]:
        try:
            qs = _json.loads(row["questions"])
            # Strip answer_index before sending to client
            safe_qs = [{"question": q["question"], "options": q["options"]} for q in qs]
            return jsonify({"content": row["content"], "questions": safe_qs})
        except Exception:
            pass  # Fall through to regenerate if JSON is corrupt

    # Cache miss — generate via Ollama
    ai  = get_ai_client()
    ctx = get_student_context()
    result = ai.generate_lesson_content(
        row["lesson_key"], row["title"], row["tier"],
        ctx["name"], ctx["age"], ctx["gender"],
    )

    content = result.get("content", "")
    questions = result.get("questions", [])

    # Store full result (with answer_index) in DB
    db.execute(
        "UPDATE finance_lessons SET content = ?, questions = ?, content_generated_at = datetime('now') "
        "WHERE lesson_key = ?",
        (content, _json.dumps(questions), lesson_key),
    )
    db.commit()

    # Return questions without answer_index
    safe_qs = [{"question": q["question"], "options": q["options"]} for q in questions]
    return jsonify({"content": content, "questions": safe_qs})


@finance_bp.route("/lessons/<string:lesson_key>/submit-quiz", methods=["POST"])
def submit_quiz(lesson_key: str):
    """
    POST body: {"answers": [int, int, int]}  (0-based indices of selected options)
    Validates answers server-side against stored answer_index values.
    Returns: {passed: bool, correct: [bool, bool, bool], score: int}
    If passed, marks quiz_passed=1 in DB.
    """
    import json as _json
    data = request.get_json(silent=True) or {}
    submitted = data.get("answers", [])

    db = get_db()
    row = db.execute(
        "SELECT questions, quiz_passed FROM finance_lessons WHERE lesson_key = ?",
        (lesson_key,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Lesson not found"}), 404

    if not row["questions"]:
        return jsonify({"error": "Lesson content not generated yet — expand the lesson first"}), 400

    try:
        questions = _json.loads(row["questions"])
    except Exception:
        return jsonify({"error": "Lesson data is corrupt — try refreshing the lesson"}), 500

    correct_flags = []
    for i, q in enumerate(questions):
        expected = q.get("answer_index", -1)
        given = submitted[i] if i < len(submitted) else -1
        correct_flags.append(int(given) == expected)

    score = sum(correct_flags)
    passed = score == len(questions)  # All 3 must be correct

    if passed and not row["quiz_passed"]:
        db.execute(
            "UPDATE finance_lessons SET quiz_passed = 1 WHERE lesson_key = ?",
            (lesson_key,),
        )
        db.commit()

    return jsonify({"passed": passed, "correct": correct_flags, "score": score, "total": len(questions)})


@finance_bp.route("/lessons/<string:lesson_key>/force-pass", methods=["POST"])
def force_pass_lesson(lesson_key: str):
    """
    Called after 2 failed quiz attempts — marks quiz_passed=1 so student can still claim XP.
    This is intentional: after 2 tries the answers are revealed and they've engaged with the content.
    """
    db = get_db()
    row = db.execute(
        "SELECT lesson_key FROM finance_lessons WHERE lesson_key = ?",
        (lesson_key,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Lesson not found"}), 404

    db.execute(
        "UPDATE finance_lessons SET quiz_passed = 1 WHERE lesson_key = ?",
        (lesson_key,),
    )
    db.commit()
    return jsonify({"ok": True, "lesson": lesson_key})


@finance_bp.route("/lessons/<string:lesson_key>/complete", methods=["POST"])
def complete_lesson(lesson_key: str):
    """Awards XP only if quiz has been passed."""
    db = get_db()
    row = db.execute(
        "SELECT quiz_passed, completed FROM finance_lessons WHERE lesson_key = ?",
        (lesson_key,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Lesson not found"}), 404

    if not row["quiz_passed"]:
        return jsonify({"error": "Complete the quiz correctly before claiming XP"}), 403

    if row["completed"]:
        return jsonify({"lesson": lesson_key, "xp": 0, "message": "Already completed"})

    db.execute(
        "UPDATE finance_lessons SET completed = 1, completed_at = datetime('now') WHERE lesson_key = ?",
        (lesson_key,),
    )
    db.commit()

    from services.xp_engine import log_activity_complete
    result = log_activity_complete("finance_lesson")
    return jsonify({"lesson": lesson_key, "xp": result})


@finance_bp.route("/explain", methods=["POST"])
def explain():
    """POST /finance/explain  body: {"concept": "P/E ratio"}"""
    data = request.get_json(silent=True) or {}
    concept = data.get("concept")
    if not concept:
        return jsonify({"error": "concept required"}), 400
    ai  = get_ai_client()
    ctx = get_student_context()
    explanation = ai.explain_finance_concept(concept, ctx["name"], ctx["age"], ctx["gender"])
    return jsonify({"concept": concept, "explanation": explanation})


@finance_bp.route("/analyze-trade", methods=["POST"])
def analyze_trade():
    """POST /finance/analyze-trade  body: {"symbol":"AAPL","rationale":"I think..."}"""
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol")
    rationale = data.get("rationale", "No rationale provided")
    if not symbol:
        return jsonify({"error": "symbol required"}), 400
    market = get_quote(symbol)
    ai = get_ai_client()
    feedback = ai.analyze_trade_idea(symbol, rationale, market)
    return jsonify({"symbol": symbol, "feedback": feedback, "market_data": market})