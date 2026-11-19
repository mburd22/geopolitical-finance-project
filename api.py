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

from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import ai
from calculate_reactions import DEFENSE_TICKERS, MARKET_TICKER, load_events, load_prices
from check_events import ALLOWED
from confounds import find_confounds, load_earnings
from functools import lru_cache

import backtest
from find_analogs import STRONG_MATCH, find_analogs, load_reactions, summarize, write_thesis
from make_charts import abnormal_path

app = FastAPI(title="Defense Stock Event Tracker API")

# CORS: browsers block a page from one address (the React app on port 5173)
# reading data from another (this server on port 8000) unless the server allows it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the data once when the server starts, not on every request, so answers are fast.
PRICES = load_prices("data/prices.csv")
EVENTS = load_events("data/events.csv")
REACTIONS = load_reactions("data/event_reactions.csv")
EARNINGS = load_earnings("data/earnings.csv")


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
        "market_ticker": MARKET_TICKER,
        "price_data_ends": str(PRICES.index[-1].date()),
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
    """One event plus its day-by-day path for every ticker, ready to draw as a line chart."""
    match = EVENTS[EVENTS["date"] == pd.to_datetime(date, errors="coerce")]
    if match.empty:
        # 404 is the standard web code for "not found".
        raise HTTPException(status_code=404, detail=f"No event on {date}")
    event = match.iloc[0]

    paths = {ticker: abnormal_path(PRICES, event, ticker) for ticker in DEFENSE_TICKERS}
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
    return {"event": event_tags(event), "series": series, "confounds": confounds_for(event, ticker)}


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
            "path": [{"day": int(day), "value": to_number(value)} for day, value in average.items()],
        })
    return sorted(results, key=lambda item: item["avg_abnormal_20d"] or 0, reverse=True)


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
    found = find_analogs(event, EVENTS, top_n=new_event.top)
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
