# Make a prediction for every newly detected event, and score old predictions once
# their 20-trading-day window has passed. Predictions are locked in when made, so the
# live track record can't be quietly revised after the fact.

import json
from datetime import datetime, timezone

import pandas as pd

from backtest import track_record
from calculate_reactions import DEFENSE_TICKERS, MARKET_TICKER, first_reaction_day, measure_event
from find_analogs import STRONG_MATCH, find_analogs, summarize, write_thesis

WINDOW_DAYS = 20


def ensure_tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY,
            event_id INTEGER, ticker TEXT, made_at TEXT,
            predicted_median REAL, beat_share REAL, direction TEXT,   -- 'up', 'down' or 'flat'
            n_analogs INTEGER, strong_matches INTEGER,
            analogs_json TEXT, thesis TEXT,
            actual_20d REAL, hit INTEGER, scored_at TEXT,
            UNIQUE(event_id, ticker)
        );
    """)


def as_event(row):
    """A detected-event database row in the shape the analysis functions expect."""
    return {
        "date": pd.Timestamp(row["event_date"]), "event": row["name"], "category": row["category"],
        "region": row["region"], "us_involved": row["us_involved"], "severity": row["severity"],
        "surprise": row["surprise"], "after_close": row["after_close"],
    }


def predict_new(db, events, reactions, log=print):
    """Predict every active event that doesn't have predictions yet. Returns how many events."""
    ensure_tables(db)
    rows = db.execute("SELECT * FROM detected_events WHERE status = 'active' AND id NOT IN "
                      "(SELECT DISTINCT event_id FROM predictions)").fetchall()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = {t: track_record(events, reactions, t) for t in DEFENSE_TICKERS} if rows else {}
    for row in rows:
        tags = {k: row[k] for k in ("category", "region", "us_involved", "severity", "surprise")}
        analogs = find_analogs(tags, events)
        for ticker in DEFENSE_TICKERS:
            if analogs.empty:
                db.execute("INSERT OR IGNORE INTO predictions (event_id, ticker, made_at, direction, n_analogs) "
                           "VALUES (?, ?, ?, 'flat', 0)", (row["id"], ticker, now))
                continue
            matched, stats = summarize(analogs, reactions, ticker=ticker)
            beat_share = stats["20d"]["beat_market"] / len(matched)
            direction = "up" if beat_share >= 0.6 else "down" if beat_share <= 0.4 else "flat"
            top = [{"date": str(a.date.date()), "event": a.event, "similarity": int(a.similarity),
                    "abnormal_20d": round(float(a.abnormal_20d), 2)} for a in matched.head(5).itertuples()]
            thesis = write_thesis(tags, matched, stats, ticker=ticker, track_record=records[ticker])
            db.execute(
                "INSERT OR IGNORE INTO predictions (event_id, ticker, made_at, predicted_median, beat_share, direction, "
                "n_analogs, strong_matches, analogs_json, thesis) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row["id"], ticker, now, round(float(stats["20d"]["median"]), 2), round(beat_share, 3), direction,
                 len(matched), int((matched["similarity"] >= STRONG_MATCH).sum()), json.dumps(top), thesis))
    db.commit()
    if rows:
        log(f"Made predictions for {len(rows)} new events")
    return len(rows)


def progress(prices, row, ticker):
    """How the stock has done vs the market since the event, so far. None if markets haven't reacted yet."""
    event = as_event(row)
    day0 = first_reaction_day(prices.index, event["date"], event["after_close"])
    if day0 >= len(prices) or day0 < 1:
        return None
    last = min(day0 + WINDOW_DAYS - 1, len(prices) - 1)
    base = day0 - 1
    stock = prices[ticker].iloc[last] / prices[ticker].iloc[base] - 1
    market = prices[MARKET_TICKER].iloc[last] / prices[MARKET_TICKER].iloc[base] - 1
    return {"days": int(last - day0 + 1), "abnormal": round(float(stock - market) * 100, 2),
            "reaction_day": str(prices.index[day0].date())}


def score_due(db, prices, log=print):
    """Score predictions whose full 20-day window is now in the price data."""
    ensure_tables(db)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    due = db.execute("SELECT p.id, p.ticker, p.direction, e.* FROM predictions p JOIN detected_events e "
                     "ON e.id = p.event_id WHERE p.scored_at IS NULL").fetchall()
    scored = 0
    for row in due:
        results = measure_event(prices, as_event(row))  # [] until the window is complete
        actual = next((r["abnormal_20d"] for r in results if r["ticker"] == row["ticker"]), None)
        if actual is None:
            continue
        hit = None if row["direction"] == "flat" else int((actual > 0) == (row["direction"] == "up"))
        db.execute("UPDATE predictions SET actual_20d = ?, hit = ?, scored_at = ? WHERE id = ?",
                   (actual, hit, now, row[0]))
        scored += 1
    db.commit()
    if scored:
        log(f"Scored {scored} predictions whose 20-day window has closed")
    return scored


def live_scorecard(db, ticker):
    """Hit rate of scored live predictions for one ticker (excluding dismissed events)."""
    row = db.execute(
        "SELECT count(*) AS scored, sum(hit) AS hits, sum(CASE WHEN hit IS NOT NULL THEN 1 ELSE 0 END) AS calls, "
        "sum(CASE WHEN actual_20d > 0 THEN 1 ELSE 0 END) AS ups "
        "FROM predictions p JOIN detected_events e ON e.id = p.event_id "
        "WHERE p.ticker = ? AND p.scored_at IS NOT NULL AND e.status = 'active'", (ticker,)).fetchone()
    pending = db.execute(
        "SELECT count(*) FROM predictions p JOIN detected_events e ON e.id = p.event_id "
        "WHERE p.ticker = ? AND p.scored_at IS NULL AND e.status = 'active'", (ticker,)).fetchone()[0]
    calls = row["calls"] or 0
    return {
        "scored": row["scored"], "calls": calls, "pending": pending,
        "hit_rate": round(100 * row["hits"] / calls, 1) if calls else None,
        "always_up_hit_rate": round(100 * row["ups"] / row["scored"], 1) if row["scored"] else None,
    }
