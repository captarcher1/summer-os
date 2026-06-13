"""
Ollama integration — all AI calls go through this module.
Keeps the rest of the codebase decoupled from the LLM provider.
"""

import json
import logging
from typing import Optional
import requests
from flask import current_app

logger = logging.getLogger(__name__)


# ─── Gender helpers ────────────────────────────────────────────────────────────
def _gender_label(gender: str) -> str:
    """Return a natural label for the system prompt (e.g. 'boy', 'girl', 'student')."""
    g = (gender or "").strip().lower()
    if g in ("male", "boy", "m"):
        return "boy"
    if g in ("female", "girl", "f"):
        return "girl"
    return "student"


def _pronoun(gender: str) -> str:
    """Return 'he/him', 'she/her', or 'they/them'."""
    g = (gender or "").strip().lower()
    if g in ("male", "boy", "m"):
        return "he/him"
    if g in ("female", "girl", "f"):
        return "she/her"
    return "they/them"


class OllamaClient:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._session = requests.Session()

    def _chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        """Send a chat request to Ollama and return the response text."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        }
        try:
            resp = self._session.post(url, json=payload, timeout=180)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except requests.exceptions.ConnectionError:
            logger.warning("Ollama not reachable at %s — returning fallback", self.base_url)
            return self._fallback(user_prompt)
        except Exception as exc:
            logger.error("Ollama error: %s", exc)
            return self._fallback(user_prompt)

    def _fallback(self, prompt: str) -> str:
        return "AI coach is offline right now. Start Ollama with: ollama serve"

    def is_available(self) -> bool:
        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Public methods — one per use case
    # ------------------------------------------------------------------

    def generate_daily_schedule(self, context: dict) -> dict:
        """
        Generate a structured daily schedule given the context.
        Returns a list of schedule block dicts.
        """
        system = """You are a youth development coach and scheduler.
You create structured daily schedules for a 15-year-old using the Summer Growth OS.
Respond ONLY with valid JSON — no markdown, no explanation.
Output format:
{
  "blocks": [
    {"activity_key": "sports", "start_time": "07:00", "end_time": "08:00", "is_locked": 1, "sort_order": 1},
    ...
  ],
  "coach_note": "Short motivational note for the day (1-2 sentences)"
}
Available activity keys: taekwondo, sports, reading, finance_lesson, finance_trade, chores, family_time, training, gaming"""

        user = f"""Create a daily schedule for {context.get('date', 'today')}.
Day of week: {context.get('day_of_week', 'Weekday')}
Is weekend: {context.get('is_weekend', False)}
Recent XP: {context.get('recent_xp', 0)} (last 3 days)
Streak: {context.get('streak', 0)} days
Flags from balance detector: {context.get('flags', [])}
Weekly XP so far: {context.get('weekly_xp', 0)}
Parent gaming cap: {context.get('gaming_cap', 4.0)} hours
Weekend XP minimum: {context.get('weekend_xp_min', 400)}

Rules:
- Weekdays: include sports/taekwondo in morning, finance lesson midday, chores in afternoon
- Weekends: lighter structure, honour autonomy, still require weekend_xp_minimum
- Gaming only appears if daily XP target (500+) is on track — mark as earned window
- Max 4 hours gaming per day
- Balance all 6 dimensions across the week"""

        raw = self._chat(system, user, temperature=0.4)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            logger.warning("Could not parse schedule JSON from Ollama response")
            return {"blocks": [], "coach_note": raw}

    def generate_coach_note(self, xp_data: dict, balance_data: dict,
                            student_name: str = "Player",
                            student_age: str = "15",
                            student_gender: str = "unspecified") -> str:
        """Short daily nudge — 2-3 sentences max."""
        pronoun = _pronoun(student_gender)
        system = f"""You are a supportive coach for {student_name}, a {student_age}-year-old {_gender_label(student_gender)}.
Write a short, direct daily nudge (2-3 sentences). Use plain language. No corporate jargon.
Refer to {student_name} using {pronoun} pronouns. Be specific about their actual data. Be encouraging but honest."""

        user = f"""Today's data:
- Daily XP so far: {xp_data.get('daily_xp', 0)}
- Streak: {xp_data.get('streak', 0)} days
- Gaming hours earned today: {xp_data.get('gaming_hours_earned', 0)}
- Balance flags: {balance_data.get('flags', [])}
- Weakest category this week: {balance_data.get('weakest_category', 'none')}
- Strongest category: {balance_data.get('strongest_category', 'none')}
Write the nudge now."""

        return self._chat(system, user, temperature=0.8)

    def generate_week_review(self, week_data: dict,
                             student_name: str = "Player",
                             student_age: str = "15",
                             student_gender: str = "unspecified") -> str:
        """Parent-facing weekly summary with flags and recommendations."""
        system = f"""You are an analytical assistant writing a weekly report for a parent.
The student is {student_name}, a {student_age}-year-old {_gender_label(student_gender)}.
Be concise, data-driven, and specific. Flag real issues, celebrate real wins.
Max 150 words. Use plain language."""

        user = f"""Weekly data for {student_name}:
- Total XP: {week_data.get('total_xp', 0)}
- Compliance rate: {week_data.get('compliance_pct', 0)}%
- Activity breakdown: {week_data.get('breakdown', {})}
- Gaming vs earned: {week_data.get('gaming_vs_earned_pct', 100)}%
- Balance score: {week_data.get('balance_score', 0)}/100
- Alerts this week: {week_data.get('alerts', [])}
- Finance progress: {week_data.get('finance_progress', {})}
Write the parent summary now."""

        return self._chat(system, user, temperature=0.3)

    def explain_finance_concept(self, concept: str,
                                student_name: str = "Player",
                                student_age: str = "15",
                                student_gender: str = "unspecified") -> str:
        """Explain a finance concept at an age-appropriate level with a real example."""
        system = f"""You are teaching {student_name}, a {student_age}-year-old {_gender_label(student_gender)}, about personal finance and investing.
Use plain English. Give one real, concrete example (e.g. actual ticker, actual numbers).
Keep it under 120 words. End with one question to make them think."""

        user = f"Explain: {concept}"
        return self._chat(system, user, temperature=0.6)

    def analyze_trade_idea(self, symbol: str, rationale: str, market_data: dict) -> str:
        """Give feedback on a paper trade idea the student wants to make."""
        system = """You are a trading mentor reviewing a 15-year-old's paper trade idea.
Assess: rationale quality, key risks, one thing to check before trading.
Max 100 words. Be honest, not just supportive."""

        user = f"""Trade idea:
Symbol: {symbol}
Student's rationale: {rationale}
Current price: {market_data.get('price', 'unknown')}
P/E: {market_data.get('pe', 'unknown')}
52w range: {market_data.get('week52_low', '?')} – {market_data.get('week52_high', '?')}
Assess this trade."""

        return self._chat(system, user, temperature=0.4)

    def _verify_quiz_answers(self, content: str, questions: list) -> list:
        """
        Second-pass verification: given the lesson content and raw questions from the first
        AI call, ask the model to re-check every answer_index.
        Uses temperature=0.1 for near-deterministic reasoning.
        Returns the corrected questions list (or the original if parsing fails).
        """
        import re as _re
        system = """You are a quiz answer verifier for a teen finance course.
Given a lesson paragraph and its quiz questions, verify that each answer_index is correct.
For numeric/calculation questions, compute the exact answer.
For factual questions, reason step-by-step.
Respond ONLY with valid JSON — the corrected questions array (same structure, only fix answer_index values).
Output format: [{"question": "...", "options": ["A","B","C","D"], "answer_index": N}, ...]"""

        qs_text = json.dumps(questions, indent=2)
        user = f"""Lesson content:
{content}

Quiz questions (verify and correct each answer_index — it is 0-based):
{qs_text}

Steps for each question:
1. Read the question and all options carefully.
2. Derive or calculate the correct answer (show brief reasoning in your head, NOT in output).
3. Identify which option index (0, 1, 2, or 3) matches the correct answer.
4. Set answer_index to that index.

Return ONLY the corrected JSON array — no commentary."""

        raw = self._chat(system, user, temperature=0.1)
        try:
            result = json.loads(raw)
            if isinstance(result, list) and len(result) == len(questions):
                # Sanity-check: answer_index must be 0-3 for each question
                for item in result:
                    idx = item.get("answer_index", -1)
                    opts = item.get("options", [])
                    if not isinstance(idx, int) or idx < 0 or idx >= len(opts):
                        raise ValueError(f"Bad answer_index {idx}")
                return result
        except Exception:
            pass
        # Try extracting JSON array from response
        import re as _re
        match = _re.search(r"\[.*\]", raw, _re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list) and len(result) == len(questions):
                    return result
            except Exception:
                pass
        logger.warning("Quiz verification pass failed — using original answers")
        return questions

    def generate_lesson_content(self, lesson_key: str, title: str, tier: int,
                                student_name: str = "Player",
                                student_age: str = "15",
                                student_gender: str = "unspecified") -> dict:
        """
        Generate a lesson paragraph + 3 MCQ questions for a given finance lesson.
        Returns: {"content": str, "questions": [{"question": str, "options": [str,...], "answer_index": int}]}
        """
        tier_labels = {
            1: "financial literacy basics (budgeting, saving, compound interest)",
            2: "investing and paper trading concepts (stocks, P/E, charts, ETFs)",
            3: "advanced trading strategy (screeners, technical analysis, options)",
        }
        tier_desc = tier_labels.get(tier, "personal finance")

        system = f"""You are a personal finance educator teaching {student_name}, a {student_age}-year-old {_gender_label(student_gender)}.
Write a clear, engaging lesson and quiz. Respond ONLY with valid JSON — no markdown, no explanation.
Output format:
{{
  "content": "3-4 sentence lesson paragraph using plain English with one real-world example",
  "questions": [
    {{
      "question": "Question text?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer_index": 0
    }}
  ]
}}
Rules:
- content: 3-4 sentences, plain English, concrete example (use real numbers or tickers where relevant)
- questions: exactly 3 multiple-choice questions, 4 options each
- answer_index: 0-based index of the correct answer
- Questions must directly test understanding of the lesson content
- Difficulty appropriate for a smart {student_age}-year-old learning finance"""

        user = f"""Lesson topic: "{title}"
Tier: {tier} — {tier_desc}
Generate the lesson content and 3 quiz questions now."""

        raw = self._chat(system, user, temperature=0.4)
        parsed = None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except Exception:
                    pass

        if parsed and "content" in parsed and "questions" in parsed:
            # Second pass: verify all answer_index values are correct
            verified_questions = self._verify_quiz_answers(parsed["content"], parsed["questions"])
            parsed["questions"] = verified_questions
            return parsed

        logger.warning("Could not parse lesson content JSON for: %s", lesson_key)
        # Fallback — minimal structure so UI doesn't break
        return {
            "content": f"This lesson covers: {title}. AI coach is currently offline — start Ollama with: ollama serve",
            "questions": [
                {"question": "What is this lesson about?", "options": [title, "Budgeting", "Stocks", "Taxes"], "answer_index": 0},
                {"question": "AI is offline. Which command starts Ollama?", "options": ["ollama start", "ollama serve", "ollama run", "ollama go"], "answer_index": 1},
                {"question": "Ready to continue?", "options": ["Yes", "No", "Maybe", "Not sure"], "answer_index": 0},
            ],
        }

    def generate_daily_quote(self, student_name: str = "Player",
                             student_age: str = "15",
                             student_gender: str = "unspecified") -> dict:
        """
        Generate one short, punchy, age-appropriate quote for the daily startup banner.
        Returns: {"quote": str, "author": str}
        """
        system = f"""You generate a single fun, inspiring, or witty quote for {student_name}, a {student_age}-year-old {_gender_label(student_gender)}.
Respond ONLY with valid JSON — no markdown, no explanation.
Output format: {{"quote": "The quote text here.", "author": "Person or Source"}}
Rules:
- Keep the quote under 20 words.
- Choose quotes that are motivating, funny, or thought-provoking — appropriate for a {student_age}-year-old.
- Vary between sports figures, inventors, comedians, entrepreneurs, and fictional characters.
- Never use corporate jargon or clichés like "hustle" or "grind"."""

        user = f"Generate one fresh quote for {student_name} today."

        raw = self._chat(system, user, temperature=0.95)
        try:
            result = json.loads(raw)
            if "quote" in result:
                return result
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group())
                    if "quote" in result:
                        return result
                except Exception:
                    pass
        # Fallback quotes if Ollama is offline
        import random
        fallbacks = [
            {"quote": "It always seems impossible until it's done.", "author": "Nelson Mandela"},
            {"quote": "The secret of getting ahead is getting started.", "author": "Mark Twain"},
            {"quote": "You miss 100% of the shots you don't take.", "author": "Wayne Gretzky"},
            {"quote": "Stay hungry, stay foolish.", "author": "Steve Jobs"},
            {"quote": "Be yourself; everyone else is already taken.", "author": "Oscar Wilde"},
        ]
        return random.choice(fallbacks)

    def generate_finance_lessons(self, existing_titles: list,
                                 existing_keys: set = None,
                                 target: int = 5) -> list:
        """
        Generate `target` new unique finance lesson titles not already in the DB.
        Requests (target + 3) from Ollama to buffer for expected deduplication,
        then deduplicates against existing_keys client-side before returning.
        Returns a list of dicts: [{"tier": int, "title": str, "lesson_key": str}]
        """
        ask_for = target + 3   # over-request to survive dedup losses
        existing_keys = existing_keys or set()

        system = f"""You are a personal finance educator for teenagers.
Generate exactly {ask_for} unique finance lesson titles for a 15-year-old.
Respond ONLY with valid JSON — no markdown, no explanation.
Output format: [
  {{"tier": 1, "title": "Lesson title here", "lesson_key": "snake_case_key"}},
  ...
]
Rules:
- Return EXACTLY {ask_for} items — no more, no fewer.
- lesson_key must be unique lowercase snake_case (e.g. "reading_a_stock_chart").
- Do NOT repeat or closely paraphrase any existing lesson.
- Tier 1 = financial literacy basics, Tier 2 = investing/trading concepts, Tier 3 = advanced strategy."""

        existing_sample = ", ".join(existing_titles[:40]) if existing_titles else "none"
        user = f"""Existing lessons to AVOID (do not repeat these topics or keys): {existing_sample}
Generate {ask_for} brand-new lessons now."""

        raw = self._chat(system, user, temperature=0.7)

        # Parse response
        candidates = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                candidates = parsed
        except json.JSONDecodeError:
            import re
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                try:
                    candidates = json.loads(match.group())
                except Exception:
                    pass

        # Deduplicate against existing keys (AI may still repeat despite instructions)
        seen_keys = set(existing_keys)
        unique = []
        for item in candidates:
            key = (item.get("lesson_key") or "").strip().lower().replace(" ", "_")
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            item["lesson_key"] = key
            unique.append(item)
            if len(unique) >= target:
                break

        return unique


def get_ai_client() -> OllamaClient:
    """Factory - returns a client using the current app config."""
    return OllamaClient(
        base_url=current_app.config["OLLAMA_BASE_URL"],
        model=current_app.config["OLLAMA_MODEL"],
    )
