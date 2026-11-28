# Print the live track record for one stock: every event the pipeline detected, the
# prediction locked in for it, how the stock has done since, and the final score.
#
#   .\.venv\Scripts\python.exe live_report.py                 ITA, active events
#   .\.venv\Scripts\python.exe live_report.py --ticker RHM.DE
#   .\.venv\Scripts\python.exe live_report.py --all           include dismissed events
#
# It only ever READS data/news.db (the database is opened read-only), so it's safe to run
# while the API server or the pipeline is running.

import argparse
import sqlite3
import sys

import news
from calculate_reactions import DEFENSE_TICKERS, load_all_prices
from predict import live_scorecard, progress

CALL = {"up": "beat market", "down": "lag market", "flat": "no call"}


def open_read_only(path=None):
    """Open the live database read-only, or return None if it doesn't exist yet."""
    path = path or news.DB_PATH
    if not path.exists():
        return None
    # mode=ro: SQLite refuses any write through this connection.
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def has_table(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def signed(value):
    return "    —" if value is None else f"{value:+5.1f}%"


def report_rows(db, prices, ticker, include_dismissed=False):
    """One dict per detected event, newest first, with its prediction and result for `ticker`."""
    statuses = ("active", "dismissed") if include_dismissed else ("active",)
    rows = db.execute(
        f"SELECT e.*, p.direction, p.predicted_median, p.n_analogs, p.actual_20d, p.hit, p.scored_at "
        f"FROM detected_events e LEFT JOIN predictions p ON p.event_id = e.id AND p.ticker = ? "
        f"WHERE e.status IN ({','.join('?' * len(statuses))}) ORDER BY e.event_time DESC",
        (ticker, *statuses)).fetchall()
    out = []
    for row in rows:
        so_far = progress(prices, row, ticker) if row["scored_at"] is None else None
        if row["direction"] is None:
            result = "no prediction yet"
        elif row["scored_at"] is not None:
            result = "no call" if row["hit"] is None else ("RIGHT" if row["hit"] else "WRONG")
        else:
            result = f"pending, day {so_far['days']} of 20" if so_far else "pending, markets not open yet"
        out.append({
            "date": row["event_date"], "name": row["name"], "category": row["category"],
            "status": row["status"], "call": CALL.get(row["direction"], "—"),
            "predicted": row["predicted_median"], "n_analogs": row["n_analogs"],
            "actual": row["actual_20d"] if row["scored_at"] is not None else (so_far or {}).get("abnormal"),
            "result": result,
        })
    return out


def print_report(db, prices, ticker, include_dismissed=False, out=print):
    rows = report_rows(db, prices, ticker, include_dismissed)
    card = live_scorecard(db, ticker)
    out(f"Live record for {ticker}: {len(rows)} events, {card['scored']} scored, {card['pending']} pending")
    if card["calls"]:
        out(f"  Hit rate {card['hit_rate']}% on {card['calls']} calls; "
            f"'always beats the market' would have been right {card['always_up_hit_rate']}%")
    else:
        out("  No scored calls yet: a prediction is scored 20 trading days after its event.")
    out("")
    out(f"{'date':10}  {'call':11}  {'pred.':>6}  {'actual':>6}  {'result':28}  event")
    for r in rows:
        name = r["name"] if r["status"] == "active" else f"[dismissed] {r['name']}"
        out(f"{r['date']:10}  {r['call']:11}  {signed(r['predicted'])}  {signed(r['actual'])}  "
            f"{r['result']:28}  {name[:70]}")
    out("")
    out("pred. = median 20-day move vs the market in similar past events; actual = so far, or final once scored.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print the live prediction record for one stock.")
    parser.add_argument("--ticker", default="ITA", choices=DEFENSE_TICKERS)
    parser.add_argument("--all", action="store_true", help="include dismissed events")
    args = parser.parse_args()

    db = open_read_only()
    if db is None or not has_table(db, "detected_events") or not has_table(db, "predictions"):
        print("No live data yet. Start the API server or run: .\\.venv\\Scripts\\python.exe pipeline.py")
        sys.exit(0)
    print_report(db, load_all_prices(), args.ticker, include_dismissed=args.all)
    db.close()
