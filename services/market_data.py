"""
Market data service — wraps yfinance for paper trading.
yfinance is free, unlimited, and requires no API key.
Alpha Vantage key (optional) is used for richer fundamental data.
"""

import logging
from datetime import date
from database.models import get_db
from flask import current_app

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    logger.warning("yfinance not installed — market data unavailable. Run: pip install yfinance")


# ---------------------------------------------------------------------------
# Quote fetching
# ---------------------------------------------------------------------------

def get_quote(symbol: str) -> dict:
    """Fetch current price and key fundamentals for a ticker."""
    if not YF_AVAILABLE:
        return {"error": "yfinance not installed", "symbol": symbol}
    try:
        ticker = yf.Ticker(symbol.upper())
        info = ticker.fast_info
        hist = ticker.history(period="5d")

        price = float(info.last_price) if hasattr(info, "last_price") else None
        if price is None and not hist.empty:
            price = float(hist["Close"].iloc[-1])

        full_info = ticker.info
        return {
            "symbol":         symbol.upper(),
            "price":          round(price, 2) if price else None,
            "name":           full_info.get("longName", symbol),
            "pe":             full_info.get("trailingPE"),
            "market_cap":     full_info.get("marketCap"),
            "week52_high":    full_info.get("fiftyTwoWeekHigh"),
            "week52_low":     full_info.get("fiftyTwoWeekLow"),
            "day_change_pct": round(full_info.get("regularMarketChangePercent", 0), 2),
        }
    except Exception as exc:
        logger.error("Quote fetch failed for %s: %s", symbol, exc)
        return {"error": str(exc), "symbol": symbol}


def get_price_history(symbol: str, period: str = "3mo") -> list:
    """Return daily OHLCV as a list of dicts (for charts)."""
    if not YF_AVAILABLE:
        return []
    try:
        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period=period)
        return [
            {
                "date":   str(idx.date()),
                "open":   round(row.Open, 2),
                "high":   round(row.High, 2),
                "low":    round(row.Low, 2),
                "close":  round(row.Close, 2),
                "volume": int(row.Volume),
            }
            for idx, row in hist.iterrows()
        ]
    except Exception as exc:
        logger.error("History fetch failed for %s: %s", symbol, exc)
        return []


# ---------------------------------------------------------------------------
# Paper portfolio
# ---------------------------------------------------------------------------

def get_portfolio() -> dict:
    """
    Return paper holdings with current prices and P&L.
    """
    db = get_db()
    holdings = db.execute("SELECT * FROM finance_holdings WHERE shares > 0").fetchall()

    positions = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        q = get_quote(h["symbol"])
        price = q.get("price") or h["avg_cost"]
        current_value = price * h["shares"]
        cost_basis = h["avg_cost"] * h["shares"]
        gain = current_value - cost_basis
        gain_pct = (gain / cost_basis * 100) if cost_basis > 0 else 0

        positions.append({
            "symbol":        h["symbol"],
            "shares":        h["shares"],
            "avg_cost":      round(h["avg_cost"], 2),
            "current_price": round(price, 2),
            "current_value": round(current_value, 2),
            "cost_basis":    round(cost_basis, 2),
            "gain":          round(gain, 2),
            "gain_pct":      round(gain_pct, 2),
            "name":          q.get("name", h["symbol"]),
        })

        total_value += current_value
        total_cost  += cost_basis

    total_gain = total_value - total_cost
    total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0

    return {
        "positions":       positions,
        "total_value":     round(total_value, 2),
        "total_cost":      round(total_cost, 2),
        "total_gain":      round(total_gain, 2),
        "total_gain_pct":  round(total_gain_pct, 2),
    }


def execute_paper_trade(symbol: str, action: str, shares: float, notes: str = "") -> dict:
    """
    Execute a paper trade (buy or sell).
    Returns {"success": bool, "message": str, "portfolio": dict}
    """
    if action not in ("buy", "sell"):
        return {"success": False, "message": "action must be 'buy' or 'sell'"}

    q = get_quote(symbol)
    if "error" in q or not q.get("price"):
        return {"success": False, "message": f"Could not get price for {symbol}"}

    price = q["price"]
    db = get_db()

    if action == "buy":
        existing = db.execute(
            "SELECT * FROM finance_holdings WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
        if existing:
            new_shares = existing["shares"] + shares
            new_avg = ((existing["avg_cost"] * existing["shares"]) + (price * shares)) / new_shares
            db.execute(
                "UPDATE finance_holdings SET shares = ?, avg_cost = ?, updated_at = datetime('now') WHERE symbol = ?",
                (new_shares, new_avg, symbol.upper()),
            )
        else:
            db.execute(
                "INSERT INTO finance_holdings(symbol, shares, avg_cost) VALUES(?,?,?)",
                (symbol.upper(), shares, price),
            )

    elif action == "sell":
        existing = db.execute(
            "SELECT * FROM finance_holdings WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
        if not existing or existing["shares"] < shares:
            return {"success": False, "message": f"Insufficient shares of {symbol}"}
        new_shares = existing["shares"] - shares
        if new_shares == 0:
            db.execute("DELETE FROM finance_holdings WHERE symbol = ?", (symbol.upper(),))
        else:
            db.execute(
                "UPDATE finance_holdings SET shares = ?, updated_at = datetime('now') WHERE symbol = ?",
                (new_shares, symbol.upper()),
            )

    # Dedup guard: reject exact same trade if one was placed in the last 10 seconds
    recent = db.execute(
        "SELECT id FROM finance_trades WHERE symbol=? AND action=? AND shares=? AND price=?"
        " AND traded_at >= datetime('now', '-10 seconds')",
        (symbol.upper(), action, shares, price),
    ).fetchone()
    if recent:
        return {"success": False, "message": "Duplicate trade detected — please wait before resubmitting"}

    db.execute(
        "INSERT INTO finance_trades(trade_date, symbol, action, shares, price, notes, traded_at)"
        " VALUES(?,?,?,?,?,?,datetime('now'))",
        (str(date.today()), symbol.upper(), action, shares, price, notes),
    )
    db.commit()

    return {
        "success":   True,
        "message":   f"{action.title()} {shares} shares of {symbol.upper()} at ${price:.2f}",
        "portfolio": get_portfolio(),
    }


def get_trade_history(limit: int = 20) -> list:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM finance_trades ORDER BY traded_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
