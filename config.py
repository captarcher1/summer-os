import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")

    # Database
    DATABASE_PATH = os.getenv("DATABASE_PATH", "summer_os.db")

    # Ollama — local LLM
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")

    # Market data (Alpha Vantage free tier — 25 calls/day)
    # Get a free key at: https://www.alphavantage.co/support/#api-key
    ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "demo")

    # Program config
    SUMMER_START = os.getenv("SUMMER_START", "2025-06-01")
    SUMMER_END = os.getenv("SUMMER_END", "2025-08-31")
    STUDENT_NAME = os.getenv("STUDENT_NAME", "Player")
    PARENT_PIN = os.getenv("PARENT_PIN", "1234")  # PIN to access parent tab

    # XP thresholds
    XP_PER_LEVEL = 1000          # XP needed per level
    DAILY_XP_TARGET = 800        # Target for full gaming unlock
    WEEKEND_XP_MINIMUM = int(os.getenv("WEEKEND_XP_MINIMUM", "400"))

    # Gaming caps (hours)
    GAMING_CAP_DAILY = float(os.getenv("GAMING_CAP_DAILY", "4.0"))

    # XP rates — source of truth (also seeded into DB)
    XP_RATES = {
        "taekwondo":        100,
        "sports":           100,
        "reading":          100,
        "finance_lesson":   150,
        "finance_trade":    75,
        "chores":           500,
        "family_time":      200,
        "training":         200,
        "streak_7day":      500,
        "streak_freeze":    -50,   # cost to use a freeze
    }

    # Gaming unlock tiers (XP earned → hours unlocked)
    GAMING_TIERS = [
        (0,    0.0),
        (300,  1.0),
        (500,  1.5),
        (800,  2.5),
        (1000, 3.0),
        (1200, 3.5),
    ]


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
