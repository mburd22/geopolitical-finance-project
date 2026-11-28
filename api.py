# Step 7: the back end. A small web server that answers questions from the React dashboard.
#
# Start it with:
#   .\.venv\Scripts\python.exe -m uvicorn api:app --reload
# Then open http://localhost:8000/docs to try every endpoint in your browser.
#
# An "endpoint" is one web address the server answers, like /api/events.
# Each one is a normal Python function with a decorator (@app.get or @app.post) on top
# that tells FastAPI which address it answers. FastAPI turns whatever the function
# returns into JSON: the text format browsers and JavaScript understand.

import json
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import ai
import history
import backtest
import detect
import news
import pipeline
import predict
import runup
from calculate_reactions import (
    BASKETS, DEFENSE_TICKERS, MARKET_OF, MARKETS, TICKER_NAMES, load_all_prices, load_events,
)
from check_events import ALLOWED
from confounds import find_confounds, load_earnings
from find_analogs import STRONG_MATCH, find_analogs, load_reactions, summarize, write_thesis
from make_charts import abnormal_path
from uncertainty import LEVEL, bootstrap_ci, groups_differ_p, share_ci

# The news pipeline runs in the background while the server is up.
# Set AUTO_PIPELINE=0 in .env to turn that off, or PIPELINE_EVERY_MINUTES to change how often.
AUTO_PIPELINE = os.environ.get("AUTO_PIPELINE", "1") != "0"
EVERY_MINUTES = int(os.environ.get("PIPELINE_EVERY_MINUTES", "60"))
LIVE = {"running": False, "next_run_at": None, "last_error": None}


def run_pipeline_now():
    """Run one pipeline pass, then reload data so the dashboard sees fresh prices and events."""
    LIVE["running"] = True
    try:
        summary = pipeline.run_once(log=lambda message: print(f"[pipeline] {message}"))
        if summary.get("market_refreshed"):
            load_data()
        LIVE["last_error"] = None
    except Exception as error:
        LIVE["last_error"] = f"{type(error).__name__}: {error}"
        print(f"[pipeline] failed: {LIVE['last_error']}")
    finally:
        LIVE["running"] = False


def scheduler():
    time.sleep(10)  # let the server finish starting first
    while True:
        run_pipeline_now()
        LIVE["next_run_at"] = (datetime.now(timezone.utc) + timedelta(minutes=EVERY_MINUTES)).isoformat(timespec="seconds")
        time.sleep(EVERY_MINUTES * 60)


@asynccontextmanager
async def lifespan(app):
    if AUTO_PIPELINE:
        # daemon=True: the thread stops automatically when the server stops.
        threading.Thread(target=scheduler, daemon=True).start()
    yield


app = FastAPI(title="Defense Stock Event Tracker API", lifespan=lifespan)

# CORS: browsers block a page from one address (the React app on port 5173)
# reading data from another (this server on port 8000) unless the server allows it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the data once when the server starts, not on every request, so answers are fast.
# load_data() runs again after the pipeline refreshes market data.
def load_data():
    global PRICES, EVENTS, REACTIONS, EARNINGS
    PRICES = load_all_prices()
    EVENTS = load_events("data/events.csv")
    REACTIONS = load_reactions("data/event_reactions.csv")
    EARNINGS = load_earnings("data/earnings.csv")
    if "track_record" in globals():
        track_record.cache_clear()
        runup_analysis.cache_clear()
        category_test.cache_clear()



load_data()


def price_data_ends():
    """The latest date with prices in every market."""
    return str(min(table.index[-1] for table in PRICES.values()).date())


def confounds_for(event, ticker):
    return find_confounds(PRICES, EVENTS, EARNINGS, event, ticker=ticker)


# lru_cache remembers each ticker's answer, so the backtest only runs once per ticker
# (about a second each) instead of on every request.
@lru_cache(maxsize=None)
def track_record(ticker):
    return backtest.track_record(EVENTS, REACTIONS, ticker)


def track_summary(ticker):
    """The headline backtest numbers, without the per-event rows."""
    record = track_record(ticker)
    return {mode: record[mode] for mode in backtest.MODES}

# The type of the ticker option: only these exact values are accepted.
Ticker = Literal[tuple(DEFENSE_TICKERS)]


def to_number(value):
    """Convert a pandas/numpy number into a plain Python float, rounded for display."""
    return None if pd.isna(value) else round(float(value), 2)


def event_tags(event):
    """The parts of an event row that the dashboard needs, as a plain dictionary."""
    return {
        "date": str(event["date"].date()),
        "event": event["event"],
        "category": event["category"],
        "region": event["region"],
        "us_involved": event["us_involved"],
        "severity": int(event["severity"]),
        "surprise": event["surprise"],
    }


@app.get("/api/options")
def options():
    """Everything the dashboard needs to build its dropdown menus."""
    return {
        "categories": sorted(ALLOWED["category"]),
        "regions": sorted(ALLOWED["region"]),
        "tickers": DEFENSE_TICKERS,
        "markets": {
            name: {"tickers": m["tickers"], "benchmark": m["benchmark"], "benchmark_name": m["benchmark_name"],
                   "price_data_ends": str(PRICES[name].index[-1].date())}
            for name, m in MARKETS.items()
        },
        "ticker_names": TICKER_NAMES,
        "ticker_market": MARKET_OF,
        "baskets": list(BASKETS),
        "price_data_ends": price_data_ends(),
    }


@app.get("/api/events")
def list_events(ticker: Ticker = "ITA"):
    """Every event, newest first, with how the chosen ticker reacted."""
    reactions = REACTIONS[REACTIONS["ticker"] == ticker]
    merged = EVENTS.merge(reactions, on=["date", "event"], how="left", suffixes=("", "_r"))
    results = []
    for _, row in merged.sort_values("date", ascending=False).iterrows():
        item = event_tags(row)
        for window in ["1d", "5d", "20d"]:
            item[f"abnormal_{window}"] = to_number(row[f"abnormal_{window}"])
        item["confounds"] = confounds_for(row, ticker)
        results.append(item)
    return results


@app.get("/api/events/{date}")
def event_detail(date: str, ticker: Ticker = "ITA"):
    """One event plus its day-by-day path for every ticker in the chosen ticker's market."""
    match = EVENTS[EVENTS["date"] == pd.to_datetime(date, errors="coerce")]
    if match.empty:
        # 404 is the standard web code for "not found".
        raise HTTPException(status_code=404, detail=f"No event on {date}")
    event = match.iloc[0]

    paths = {t: abnormal_path(PRICES, event, t) for t in MARKETS[MARKET_OF[ticker]]["tickers"]}
    paths = {ticker: path for ticker, path in paths.items() if path is not None}
    if not paths:
        raise HTTPException(status_code=422, detail="Not enough price data around this event")

    # Charts libraries like one object per point on the x-axis:
    # [{"day": -5, "LMT": -1.2, "RTX": 0.4, ...}, {"day": -4, ...}, ...]
    days = next(iter(paths.values())).index
    series = [
        {"day": int(day), **{ticker: to_number(path[day]) for ticker, path in paths.items()}}
        for day in days
    ]
    market = MARKETS[MARKET_OF[ticker]]
    return {"event": event_tags(event), "series": series, "confounds": confounds_for(event, ticker),
            "benchmark": market["benchmark"], "benchmark_name": market["benchmark_name"]}


def interval(ci):
    """A (low, high) confidence interval as a JSON-friendly [low, high] list, or None."""
    return None if ci is None else [round(ci[0], 2), round(ci[1], 2)]


@app.get("/api/categories")
def categories(ticker: Ticker = "ITA"):
    """Average reaction by event category: summary numbers plus an average day-by-day path."""
    results = []
    reactions = REACTIONS[REACTIONS["ticker"] == ticker]
    for category, group in EVENTS.groupby("category"):
        rows = reactions[reactions["category"] == category]
        paths = [abnormal_path(PRICES, event, ticker) for _, event in group.iterrows()]
        paths = [p for p in paths if p is not None]
        average = pd.concat(paths, axis=1).mean(axis=1) if paths else pd.Series(dtype=float)
        results.append({
            "category": category,
            "events": len(rows),
            "avg_abnormal_1d": to_number(rows["abnormal_1d"].mean()),
            "avg_abnormal_5d": to_number(rows["abnormal_5d"].mean()),
            "avg_abnormal_20d": to_number(rows["abnormal_20d"].mean()),
            "beat_market_20d_pct": to_number((rows["abnormal_20d"] > 0).mean() * 100),
            # 90% bootstrap ranges: where the true average plausibly sits, given so few events.
            # Resampled by cluster: events with overlapping windows move together (uncertainty.py).
            "ci_1d": interval(bootstrap_ci(rows["abnormal_1d"], clusters=rows["cluster"])),
            "ci_5d": interval(bootstrap_ci(rows["abnormal_5d"], clusters=rows["cluster"])),
            "ci_20d": interval(bootstrap_ci(rows["abnormal_20d"], clusters=rows["cluster"])),
            "beat_market_ci": interval(share_ci((rows["abnormal_20d"] > 0).astype(float), clusters=rows["cluster"])),
            "ci_level": LEVEL,
            "path": [{"day": int(day), "value": to_number(value)} for day, value in average.items()],
        })
    return sorted(results, key=lambda item: item["avg_abnormal_20d"] or 0, reverse=True)


@lru_cache(maxsize=None)
def category_test(ticker):
    rows = REACTIONS[REACTIONS["ticker"] == ticker]
    return {
        "ticker": ticker, "events": int(len(rows)), "categories": int(rows["category"].nunique()),
        **{f"p_{w}": round(groups_differ_p(rows[f"abnormal_{w}"], rows["category"]), 3) for w in ("1d", "5d", "20d")},
    }


@app.get("/api/category-test")
def category_test_results(ticker: Ticker = "ITA"):
    """Does event type explain the reaction at all? A permutation test (see uncertainty.py):
    the share of random relabellings whose category averages spread out at least as much as
    the real ones. Small (under 0.05) means event type matters; large means it could be luck."""
    return category_test(ticker)


# A Pydantic model describes the shape of data we expect to RECEIVE.
# FastAPI checks every request against it and rejects bad input with a clear error,
# so the rest of our code can trust what it gets.
class NewEvent(BaseModel):
    category: Literal[tuple(sorted(ALLOWED["category"]))]
    region: Literal[tuple(sorted(ALLOWED["region"]))]
    us_involved: Literal["yes", "no"]
    severity: Literal["1", "2", "3"]
    surprise: Literal["yes", "no"]
    ticker: Ticker = "ITA"
    top: int = Field(default=8, ge=1, le=20)  # ge/le: "greater or equal" / "less or equal"


def run_analogs(new_event: NewEvent):
    """Shared by both analog endpoints: find analogs and package everything as JSON-ready data."""
    event = new_event.model_dump()  # turn the Pydantic model into a plain dictionary
    found = find_analogs(event, EVENTS, top_n=new_event.top, reactions=REACTIONS)
    if found.empty:
        return {"analogs": [], "stats": None, "thesis": None, "track_record": None}

    matched, stats = summarize(found, REACTIONS, ticker=new_event.ticker)
    matched["confounds"] = [confounds_for(row, new_event.ticker) for _, row in matched.iterrows()]
    record = track_summary(new_event.ticker)
    return {
        "analogs": [
            {
                **event_tags(row),
                "similarity": int(row["similarity"]),
                "abnormal_1d": to_number(row["abnormal_1d"]),
                "abnormal_5d": to_number(row["abnormal_5d"]),
                "abnormal_20d": to_number(row["abnormal_20d"]),
                "confounds": row["confounds"],
            }
            for _, row in matched.iterrows()
        ],
        "stats": {
            window: {key: to_number(value) for key, value in values.items()}
            for window, values in stats.items()
        },
        "thesis": write_thesis(event, matched, stats, ticker=new_event.ticker, track_record=record),
        "track_record": {
            "hit_rate": record["leave_one_out"]["hit_rate"],
            "past_only_hit_rate": record["past_only"]["hit_rate"],
            "always_up_hit_rate": record["leave_one_out"]["always_up_hit_rate"],
            "strong_matches": int((matched["similarity"] >= STRONG_MATCH).sum()),
            "total": len(matched),
        },
    }


@app.post("/api/analogs")
def analogs(new_event: NewEvent):
    """The analog matcher: similar past events, summary stats and a template thesis."""
    return run_analogs(new_event)


@lru_cache(maxsize=None)
def runup_analysis(ticker, window):
    return runup.analyze(REACTIONS, PRICES, ticker, window)


@app.get("/api/runup")
def runup_results(ticker: Ticker = "ITA", window: Literal["20d", "60d"] = "60d"):
    """Does a big run-up before an event predict a weaker (or stronger) move after it?"""
    a = runup_analysis(ticker, window)
    col = f"runup_{window}"
    return {
        "ticker": ticker, "window": window, "events": a["events"],
        "event_corr": a["event_corr"], "event_p": a["event_p"],
        "ordinary_corr": a["ordinary_corr"], "ordinary_days": a["ordinary_days"],
        "thirds": [
            {"third": str(name), "events": int(r["events"]), "avg_runup": to_number(r["avg_runup"]),
             "avg_after": to_number(r["avg_after"]), "beat_market": to_number(r["beat_market"])}
            for name, r in a["thirds"].iterrows()
        ],
        "points": [
            {"date": str(r["date"])[:10], "event": r["event"], "category": r["category"],
             "runup": to_number(r[col]), "after": to_number(r["abnormal_20d"])}
            for _, r in a["points"].iterrows()
        ],
    }


@app.get("/api/backtest")
def backtest_results(ticker: Ticker = "ITA"):
    """How often the analog engine has been right, against simple baselines, plus every prediction."""
    record = track_record(ticker)
    # Every event has a leave-one-out prediction; early events have no past-only one
    # (too little history), so start from leave-one-out and add past-only where it exists.
    past = record["past_only_rows"][["date", "event", "direction"]].rename(columns={"direction": "direction_past"})
    rows = record["leave_one_out_rows"].merge(past, on=["date", "event"], how="left")
    rows = rows.sort_values("date", ascending=False)
    predictions = [
        {
            "date": str(row["date"]),
            "event": row["event"],
            "category": row["category"],
            "actual_20d": to_number(row["actual_20d"]),
            "predicted_median": to_number(row["predicted_median"]),
            "direction": row["direction"],
            "hit": None if row["direction"] == "flat" else bool((row["actual_20d"] > 0) == (row["direction"] == "up")),
            "past_direction": None if pd.isna(row.get("direction_past")) else row["direction_past"],
        }
        for _, row in rows.iterrows()
    ]
    return {"summary": track_summary(ticker), "weights": backtest.WEIGHTS, "predictions": predictions}


# ---------- Optional Claude features (need ANTHROPIC_API_KEY in .env) ----------

@app.post("/api/claude-thesis")
def claude_thesis(new_event: NewEvent):
    """The same analysis, with the thesis written by Claude instead of the template."""
    result = run_analogs(new_event)
    if not result["analogs"]:
        raise HTTPException(status_code=422, detail="No analogs to write a thesis about")
    tags = {k: v for k, v in new_event.model_dump().items() if k not in ("ticker", "top")}
    try:
        text = ai.write_thesis(tags, result["analogs"], result["stats"], result["track_record"], new_event.ticker)
    except ai.ClaudeUnavailable as error:
        # 503 means "service unavailable": the feature exists but can't run right now.
        raise HTTPException(status_code=503, detail=str(error))
    return {"thesis": text}


class Headline(BaseModel):
    headline: str = Field(min_length=10, max_length=500)


@app.post("/api/parse-headline")
def parse_headline(body: Headline):
    """Turn a news headline into the tags the analog matcher needs."""
    try:
        return ai.parse_headline(body.headline)
    except ai.ClaudeUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error))


# ---------- Live: events found automatically in the news ----------

def live_db():
    db = news.connect()
    detect.ensure_tables(db)
    predict.ensure_tables(db)
    return db


@app.get("/api/live/status")
def live_status():
    db = live_db()
    last = db.execute("SELECT summary FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    counts = db.execute("SELECT (SELECT count(*) FROM articles), (SELECT count(*) FROM detected_events "
                        "WHERE status = 'active'), (SELECT count(*) FROM detected_events WHERE status = 'dismissed')").fetchone()
    market = pipeline.last_market_refresh(db)
    db.close()
    return {
        "running": LIVE["running"], "auto": AUTO_PIPELINE, "every_minutes": EVERY_MINUTES,
        "next_run_at": LIVE["next_run_at"], "last_error": LIVE["last_error"],
        "last_run": json.loads(last[0]) if last else None,
        "classifier": "claude" if ai.claude_configured() else "rules",
        "articles": counts[0], "events": counts[1], "dismissed": counts[2],
        "market_refreshed_at": market.isoformat(timespec="seconds") if market else None,
        "price_data_ends": price_data_ends(),
    }


@app.post("/api/live/run")
def live_run():
    """Start a pipeline pass now, in the background. Poll /api/live/status to see when it finishes."""
    if LIVE["running"]:
        return {"started": False, "reason": "already running"}
    threading.Thread(target=run_pipeline_now, daemon=True).start()
    return {"started": True}


@app.get("/api/live/events")
def live_events(ticker: Ticker = "ITA", include_dismissed: bool = False, limit: int = 50):
    db = live_db()
    statuses = ("active", "dismissed") if include_dismissed else ("active",)
    rows = db.execute(
        f"SELECT * FROM detected_events WHERE status IN ({','.join('?' * len(statuses))}) "
        "ORDER BY event_time DESC LIMIT ?", (*statuses, min(limit, 200))).fetchall()
    results = []
    for row in rows:
        headlines = [dict(h) for h in db.execute(
            "SELECT title, source, url, published_at FROM articles WHERE event_id = ? "
            "ORDER BY published_at LIMIT 6", (row["id"],))]
        p = db.execute("SELECT * FROM predictions WHERE event_id = ? AND ticker = ?", (row["id"], ticker)).fetchone()
        prediction = None
        if p:
            prediction = {
                "direction": p["direction"], "predicted_median": p["predicted_median"], "beat_share": p["beat_share"],
                "n_analogs": p["n_analogs"], "strong_matches": p["strong_matches"], "made_at": p["made_at"],
                "analogs": json.loads(p["analogs_json"] or "[]"), "thesis": p["thesis"],
                "actual_20d": p["actual_20d"], "hit": None if p["hit"] is None else bool(p["hit"]),
                "scored": p["scored_at"] is not None,
            }
        results.append({
            "id": row["id"], "name": row["name"], "event_date": row["event_date"], "event_time": row["event_time"],
            "after_close": row["after_close"], "category": row["category"], "region": row["region"],
            "us_involved": row["us_involved"], "severity": int(row["severity"]), "surprise": row["surprise"],
            "n_articles": row["n_articles"], "n_sources": row["n_sources"], "classifier": row["classifier"],
            "reasoning": row["reasoning"], "status": row["status"], "headlines": headlines,
            "prediction": prediction, "progress": predict.progress(PRICES, row, ticker),
            "runup_60d": predict.runup_before(PRICES, row, ticker),
            "history": live_history(ticker, row["category"]),
            "engine_record": engine_record(ticker),
        })
    db.close()
    return results


def live_history(ticker, category):
    """The base rate for a live event: shown first, because the engine has no proven edge."""
    rates = history.base_rates(REACTIONS, ticker, category, type_test_p=category_test(ticker)["p_20d"])
    return None if rates is None else {**rates, "text": history.summary_text(rates)}


def engine_record(ticker):
    """The engine's backtested hit rate next to the always-up rule, and whether its edge is real."""
    loo = track_summary(ticker)["leave_one_out"]
    low, high = loo["edge_ci"]
    return {"hit_rate": loo["hit_rate"], "always_up_hit_rate": loo["always_up_hit_rate"],
            "edge_ci": loo["edge_ci"], "proven_edge": low > 0}


@app.get("/api/live/scorecard")
def live_scorecard(ticker: Ticker = "ITA"):
    db = live_db()
    card = predict.live_scorecard(db, ticker)
    db.close()
    return card


@app.post("/api/live/events/{event_id}/{action}")
def live_event_action(event_id: int, action: Literal["dismiss", "restore"]):
    """Hide a false positive (or bring it back). Dismissed events don't count in the live scorecard."""
    db = live_db()
    status = "dismissed" if action == "dismiss" else "active"
    changed = db.execute("UPDATE detected_events SET status = ? WHERE id = ?", (status, event_id)).rowcount
    db.commit()
    db.close()
    if not changed:
        raise HTTPException(status_code=404, detail="No such event")
    return {"id": event_id, "status": status}
