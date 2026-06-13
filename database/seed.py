"""
Seed data — activities, XP rates, default settings, and finance lessons.
Called once on first run by init_db().
"""

ACTIVITIES = [
    # (key, label, category, xp_value, icon, color_class)
    ("taekwondo",       "Taekwondo practice",       "sports",    100, "ti-tournament",       "cell-tkd"),
    ("sports",          "Sports / movement",         "sports",    100, "ti-barbell",          "cell-sport"),
    ("reading",         "Reading (30 min)",          "education", 100, "ti-book",             "cell-read"),
    ("finance_lesson",  "Finance lesson",            "finance",   150, "ti-currency-dollar",  "cell-fin"),
    ("finance_trade",   "Paper trade",               "finance",    75, "ti-trending-up",      "cell-fin"),
    ("chores",          "Chores (full list)",        "household", 500, "ti-home-2",           "cell-chore"),
    ("family_time",     "Family time (1 hr)",        "family",    200, "ti-users",            "cell-fam"),
    ("training",        "Training session",          "sports",    200, "ti-run",              "cell-sport"),
    ("gaming",          "Gaming (earned window)",    "gaming",      0, "ti-device-gamepad-2", "cell-game"),
]

DEFAULT_SETTINGS = [
    ("gaming_cap_daily",    "4.0"),
    ("weekend_xp_minimum",  "400"),
    ("parent_pin",          "1234"),
    ("student_name",        "Player"),
    ("summer_start",        "2025-06-01"),
    ("summer_end",          "2025-08-31"),
    ("ai_coach_enabled",    "1"),
]

FINANCE_LESSONS = [
    # Tier 1 — Financial literacy
    (1, "what_is_money",        1, "What is money and why it has value"),
    (2, "budgeting_basics",     1, "Budgeting basics — income, expenses, savings"),
    (3, "compound_interest",    1, "Compound interest — the 8th wonder"),
    (4, "savings_goals",        1, "Setting and tracking savings goals"),
    (5, "inflation_basics",     1, "Inflation and purchasing power"),
    (6, "credit_basics",        1, "Credit, debt, and why it matters"),
    (7, "types_of_accounts",    1, "Savings vs checking vs investment accounts"),
    (8, "taxes_intro",          1, "Why taxes exist and how they work"),
    (9, "emergency_fund",       1, "Emergency funds — why 3-6 months matters"),
    (10, "net_worth",           1, "Net worth — assets minus liabilities"),
    # Tier 2 — Paper trading
    (11, "what_is_a_stock",     2, "What is a stock and how exchanges work"),
    (12, "reading_a_chart",     2, "Reading a price chart — trends, support, resistance"),
    (13, "pe_ratio",            2, "P/E ratio — what the market is paying for earnings"),
    (14, "market_cap",          2, "Market cap and company size"),
    (15, "etfs_vs_stocks",      2, "ETFs vs individual stocks — diversification"),
    (16, "buy_your_first",      2, "Place your first paper trade"),
    (17, "position_sizing",     2, "Position sizing — how much to risk"),
    (18, "stop_loss",           2, "Stop-loss orders — protecting your downside"),
    (19, "portfolio_review",    2, "Weekly portfolio review process"),
    (20, "risk_reward",         2, "Risk/reward ratio — the core of every trade"),
    # Tier 3 — Strategy (unlocks after Tier 2 complete)
    (21, "screeners",           3, "Stock screeners — finding ideas systematically"),
    (22, "fundamental_analysis",3, "Fundamental analysis — reading earnings"),
    (23, "technical_signals",   3, "Technical signals — moving averages, RSI"),
    (24, "options_intro",       3, "Options — calls, puts, and why they exist"),
    (25, "building_a_system",   3, "Building a personal trading system"),
]


def run_seed(conn, config):
    """Insert seed data into a fresh database."""
    conn.executemany(
        "INSERT OR IGNORE INTO activities(key, label, category, xp_value, icon, color_class) VALUES(?,?,?,?,?,?)",
        ACTIVITIES,
    )

    # Override XP rates from config if provided
    for key, xp in config.get("XP_RATES", {}).items():
        conn.execute(
            "UPDATE activities SET xp_value = ? WHERE key = ?",
            (xp, key),
        )

    conn.executemany(
        "INSERT OR IGNORE INTO settings(key, value) VALUES(?,?)",
        DEFAULT_SETTINGS,
    )

    conn.executemany(
        "INSERT OR IGNORE INTO finance_lessons(sort_order, lesson_key, tier, title) VALUES(?,?,?,?)",
        FINANCE_LESSONS,
    )
