import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from flask import current_app, g


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_db():
    """Return a per-request DB connection (stored on Flask's g object)."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def get_db_context(app):
    """Use outside of request context (e.g. seed script, scheduler)."""
    conn = sqlite3.connect(
        app.config["DATABASE_PATH"],
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
-- Master activity catalogue with XP values
CREATE TABLE IF NOT EXISTS activities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT    NOT NULL UNIQUE,   -- e.g. 'taekwondo', 'chores'
    label       TEXT    NOT NULL,
    category    TEXT    NOT NULL,          -- sports | finance | education | household | family | gaming
    xp_value    INTEGER NOT NULL DEFAULT 0,
    icon        TEXT    NOT NULL DEFAULT 'ti-star',
    color_class TEXT    NOT NULL DEFAULT 'cell-free',
    is_active   INTEGER NOT NULL DEFAULT 1
);

-- Daily activity completion log
CREATE TABLE IF NOT EXISTS daily_log (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    log_date     DATE     NOT NULL DEFAULT (date('now')),
    activity_key TEXT     NOT NULL REFERENCES activities(key),
    completed    INTEGER  NOT NULL DEFAULT 0,   -- 0=pending, 1=done, 2=skipped
    duration_min INTEGER,                        -- actual minutes
    notes        TEXT,
    logged_at    DATETIME DEFAULT (datetime('now'))
);

-- XP transaction ledger (append-only)
CREATE TABLE IF NOT EXISTS xp_ledger (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    txn_date     DATE     NOT NULL DEFAULT (date('now')),
    activity_key TEXT     REFERENCES activities(key),
    xp_delta     INTEGER  NOT NULL,             -- positive = earn, negative = spend/penalty
    reason       TEXT     NOT NULL,
    txn_at       DATETIME DEFAULT (datetime('now'))
);

-- Streak tracking
CREATE TABLE IF NOT EXISTS streaks (
    id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    streak_date     DATE     NOT NULL UNIQUE DEFAULT (date('now')),
    daily_xp        INTEGER  NOT NULL DEFAULT 0,
    target_met      INTEGER  NOT NULL DEFAULT 0,  -- 1 if daily target hit
    freeze_used     INTEGER  NOT NULL DEFAULT 0
);

-- Generated daily schedules
CREATE TABLE IF NOT EXISTS schedule_blocks (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    block_date   DATE     NOT NULL,
    activity_key TEXT     NOT NULL REFERENCES activities(key),
    start_time   TEXT     NOT NULL,   -- "09:00"
    end_time     TEXT     NOT NULL,   -- "10:00"
    is_locked    INTEGER  NOT NULL DEFAULT 1,   -- 0 = son can move, 1 = fixed
    sort_order   INTEGER  NOT NULL DEFAULT 0,
    UNIQUE(block_date, start_time)
);

-- Parent override settings (key-value store)
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at DATETIME DEFAULT (datetime('now'))
);

-- Finance: paper portfolio holdings
CREATE TABLE IF NOT EXISTS finance_holdings (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT     NOT NULL UNIQUE,
    shares        REAL     NOT NULL DEFAULT 0,
    avg_cost      REAL     NOT NULL DEFAULT 0,
    updated_at    DATETIME DEFAULT (datetime('now'))
);

-- Finance: paper trade history
CREATE TABLE IF NOT EXISTS finance_trades (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    trade_date   DATE     NOT NULL DEFAULT (date('now')),
    symbol       TEXT     NOT NULL,
    action       TEXT     NOT NULL CHECK(action IN ('buy','sell')),
    shares       REAL     NOT NULL,
    price        REAL     NOT NULL,
    notes        TEXT,
    traded_at    DATETIME DEFAULT (datetime('now'))
);

-- Finance: lesson completion
CREATE TABLE IF NOT EXISTS finance_lessons (
    id                   INTEGER  PRIMARY KEY AUTOINCREMENT,
    sort_order           INTEGER  NOT NULL DEFAULT 0,
    lesson_key           TEXT     NOT NULL UNIQUE,
    tier                 INTEGER  NOT NULL,   -- 1=literacy, 2=paper trading, 3=strategy
    title                TEXT     NOT NULL,
    content              TEXT,               -- AI-generated lesson paragraph (null until first expand)
    questions            TEXT,               -- JSON: [{question, options:[...], answer_index}, ...]
    content_generated_at DATETIME,
    quiz_passed          INTEGER  NOT NULL DEFAULT 0,
    completed            INTEGER  NOT NULL DEFAULT 0,
    completed_at         DATETIME
);

-- AI-generated coach notes (stored for parent review)
CREATE TABLE IF NOT EXISTS coach_notes (
    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
    note_date   DATE     NOT NULL DEFAULT (date('now')),
    note_type   TEXT     NOT NULL,   -- 'daily_nudge' | 'week_review' | 'alert'
    content     TEXT     NOT NULL,
    created_at  DATETIME DEFAULT (datetime('now'))
);

-- Daily quotes pool — cycled in the startup banner
CREATE TABLE IF NOT EXISTS daily_quotes (
    id         INTEGER  PRIMARY KEY AUTOINCREMENT,
    quote      TEXT     NOT NULL,
    author     TEXT     NOT NULL DEFAULT '',
    created_at DATETIME DEFAULT (datetime('now'))
);
"""


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

_SEED_QUOTES = [
    ("It always seems impossible until it's done.", "Nelson Mandela"),
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("You miss 100% of the shots you don't take.", "Wayne Gretzky"),
    ("Stay hungry, stay foolish.", "Steve Jobs"),
    ("Be yourself; everyone else is already taken.", "Oscar Wilde"),
    ("In the middle of every difficulty lies opportunity.", "Albert Einstein"),
    ("The best time to plant a tree was 20 years ago. The second best time is now.", "Chinese Proverb"),
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
]

def _migrate_daily_quotes(conn):
    """Create daily_quotes table if it doesn't exist, then seed fallback quotes."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_quotes (
            id         INTEGER  PRIMARY KEY AUTOINCREMENT,
            quote      TEXT     NOT NULL,
            author     TEXT     NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """)
    count = conn.execute("SELECT COUNT(*) FROM daily_quotes").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO daily_quotes(quote, author) VALUES(?,?)",
            _SEED_QUOTES,
        )


def _migrate_finance_lessons(conn):
    """Add new columns to finance_lessons if they don't exist (safe for existing DBs)."""
    new_columns = [
        ("content",              "TEXT"),
        ("questions",            "TEXT"),
        ("content_generated_at", "DATETIME"),
        ("quiz_passed",          "INTEGER NOT NULL DEFAULT 0"),
    ]
    existing = {row[1] for row in conn.execute("PRAGMA table_info(finance_lessons)").fetchall()}
    for col_name, col_def in new_columns:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE finance_lessons ADD COLUMN {col_name} {col_def}")


def init_db(app):
    """Create schema, seed on first run, and sync .env config on every startup."""
    app.teardown_appcontext(close_db)

    with get_db_context(app) as conn:
        conn.executescript(SCHEMA)
        _migrate_finance_lessons(conn)
        _migrate_daily_quotes(conn)

    # Seed activities/lessons only on first run
    with get_db_context(app) as conn:
        count = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        if count == 0:
            from database.seed import run_seed
            run_seed(conn, app.config)

    # Always sync these .env values to DB on every startup so changes take effect
    _sync_config_to_settings(app)


def _sync_config_to_settings(app):
    """Push .env config values into the settings table on every startup."""
    mappings = {
        "student_name":       app.config.get("STUDENT_NAME", "Player"),
        "parent_pin":         app.config.get("PARENT_PIN", "1234"),
        "gaming_cap_daily":   str(app.config.get("GAMING_CAP_DAILY", 4.0)),
        "weekend_xp_minimum": str(app.config.get("WEEKEND_XP_MINIMUM", 400)),
    }
    with get_db_context(app) as conn:
        for key, value in mappings.items():
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                (key, value),
            )


# ---------------------------------------------------------------------------
# Query helpers (used by routes/services)
# ---------------------------------------------------------------------------

def get_total_xp():
    db = get_db()
    row = db.execute("SELECT COALESCE(SUM(xp_delta), 0) AS total FROM xp_ledger").fetchone()
    return row["total"]


def get_daily_xp(for_date: date = None):
    target = str(for_date or date.today())
    db = get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(xp_delta), 0) AS total FROM xp_ledger WHERE txn_date = ?",
        (target,),
    ).fetchone()
    return row["total"]



def get_student_context() -> dict:
    """Return student profile fields used to personalise AI prompts."""
    return {
        "name":   get_setting("student_name",   "Player"),
        "age":    get_setting("student_age",    "15"),
        "gender": get_setting("student_gender", "unspecified"),
    }


def get_total_xp():
    db = get_db()
    row = db.execute("SELECT COALESCE(SUM(xp_delta), 0) AS total FROM xp_ledger").fetchone()
    return row["total"]


def get_schedule_for_date(for_date: date = None):
    target = str(for_date or date.today())
    db = get_db()
    return db.execute(
        """
        SELECT sb.*, a.label, a.category, a.xp_value, a.icon, a.color_class
        FROM schedule_blocks sb
        JOIN activities a ON a.key = sb.activity_key
        WHERE sb.block_date = ?
        ORDER BY sb.sort_order, sb.start_time
        """,
        (target,),
    ).fetchall()


def get_log_for_date(for_date: date = None):
    target = str(for_date or date.today())
    db = get_db()
    return db.execute(
        """
        SELECT dl.*, a.label, a.category, a.xp_value, a.icon, a.color_class
        FROM daily_log dl
        JOIN activities a ON a.key = dl.activity_key
        WHERE dl.log_date = ?
        ORDER BY dl.id
        """,
        (target,),
    ).fetchall()


def get_setting(key: str, default=None):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def upsert_setting(key: str, value: str):
    db = get_db()
    db.execute(
        "INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
        (key, str(value)),
    )
    db.commit()
