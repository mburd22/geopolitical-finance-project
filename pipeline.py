# The automatic loop: refresh market data (once a day), fetch news, detect events,
# predict, and score old predictions.
#
#   .\.venv\Scripts\python.exe pipeline.py              run once
#   .\.venv\Scripts\python.exe pipeline.py --loop 60    keep running, every 60 minutes
#
# The API server also runs this in the background (see api.py), so with the dashboard
# open, it keeps itself up to date.

import argparse
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import detect
import news
import predict
from calculate_reactions import load_all_prices, load_events
from classify import is_relevant
from find_analogs import load_reactions
from refresh import refresh_market_data

MARKET_REFRESH_HOURS = 12
_lock = threading.Lock()  # never let two runs overlap (the API might trigger one while another runs)

# Every run also writes what it did to a log file, so you can see what happened while you
# weren't watching (the API server's console scrolls away). When the file passes about 1 MB
# it's renamed pipeline.log.1 (replacing any older one) and a fresh file starts.
LOG_PATH = Path(__file__).parent / "data" / "pipeline.log"
LOG_MAX_BYTES = 1_000_000


def write_log_line(message):
    LOG_PATH.parent.mkdir(exist_ok=True)
    if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
        LOG_PATH.replace(LOG_PATH.with_name(LOG_PATH.name + ".1"))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"{stamp}  {message}\n")


def also_to_file(log):
    """Wrap a log function so every message is also written to LOG_PATH."""
    def both(message):
        log(message)
        write_log_line(message)
    return both


def last_market_refresh(db):
    db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    row = db.execute("SELECT value FROM meta WHERE key = 'market_refreshed_at'").fetchone()
    return datetime.fromisoformat(row[0]) if row else None


def run_once(force_market=False, log=print):
    """One full pass. Returns a summary dict (also stored in the runs table and the log file)."""
    log = also_to_file(log)
    if not _lock.acquire(blocking=False):
        log("Run skipped: a run is already in progress")
        return {"skipped": "a run is already in progress"}
    try:
        log("Run started")
        started = datetime.now(timezone.utc)
        db = news.connect()
        summary = {"started_at": started.isoformat(timespec="seconds")}

        last = last_market_refresh(db)
        if force_market or last is None or started - last > timedelta(hours=MARKET_REFRESH_HOURS):
            log("Refreshing market data...")
            summary["market_refreshed"] = refresh_market_data(quiet=True)
            if summary["market_refreshed"]:
                db.execute("INSERT OR REPLACE INTO meta VALUES ('market_refreshed_at', ?)", (started.isoformat(),))
                db.commit()

        articles, errors = news.fetch_all(log=log)
        summary["fetched"] = len(articles)
        summary["feed_errors"] = errors
        summary["new_articles"] = news.store(db, articles, is_relevant)
        log(f"{summary['new_articles']} new articles")

        summary["new_events"] = len(detect.detect(db, log=log))

        events = load_events("data/events.csv")
        reactions = load_reactions("data/event_reactions.csv")
        prices = load_all_prices()
        summary["predicted"] = predict.predict_new(db, events, reactions, log=log)
        summary["scored"] = predict.score_due(db, prices, log=log)

        summary["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.execute("INSERT INTO runs (started_at, finished_at, summary) VALUES (?, ?, ?)",
                   (summary["started_at"], summary["finished_at"], json.dumps(summary)))
        db.commit()
        db.close()
        log(f"Run finished: {summary['new_articles']} new articles, {summary['new_events']} new events, "
            f"{summary['predicted']} predicted, {summary['scored']} scored"
            + (f", {len(errors)} sources failed" if errors else ""))
        return summary
    except Exception as error:
        log(f"Run failed: {type(error).__name__}: {error}")
        raise
    finally:
        _lock.release()


def run_forever(every_minutes, log=print):
    while True:
        try:
            run_once(log=log)
        except Exception:  # keep the loop alive through a bad run (run_once already logged it)
            pass
        time.sleep(every_minutes * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", type=int, metavar="MINUTES", help="keep running every N minutes")
    parser.add_argument("--refresh-market", action="store_true", help="refresh market data even if recent")
    args = parser.parse_args()
    if args.loop:
        run_forever(args.loop)
    else:
        print(json.dumps(run_once(force_market=args.refresh_market), indent=2))
