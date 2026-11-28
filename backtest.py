# Backtest: does the analog engine actually predict anything?
#
# For every event in the database we pretend it hasn't happened yet, ask the analog
# engine what it would have predicted from the OTHER events, then compare that with
# what really happened. Two modes:
#   leave_one_out  every other event is available (more data, but uses the future)
#   past_only      only events BEFORE this one (honest: what you'd have known at the time)
#
# The engine is compared with two simple baselines, so we know if it adds anything:
#   always_up      "defense stocks beat the market after any event"
#   category       "do what the average past event of the same category did"
#
# Run:  .\.venv\Scripts\python.exe backtest.py            (report for ITA)
#       .\.venv\Scripts\python.exe backtest.py --tune     (also search for better weights)

import argparse
import itertools

import numpy as np
import pandas as pd

from calculate_reactions import load_events
from find_analogs import MIN_SIMILARITY, STRONG_MATCH, WEIGHTS, load_reactions, same_family
from uncertainty import paired_gap_ci, share_ci

TOP_N = 8
MIN_HISTORY = 15  # past_only mode skips events with fewer earlier events than this
MODES = ["leave_one_out", "past_only"]


class Backtester:
    """Precomputes how alike every pair of events is, so thousands of predictions run fast.

    This is a vectorized copy of find_analogs.similarity(); test_matches_find_analogs()
    below checks the two give identical analogs.
    """

    def __init__(self, events, reactions, ticker="ITA", horizon="20d"):
        """horizon: which move to predict, "1d", "5d" or "20d" after the event (the engine's
        normal job is 20 days; horizons.py checks the shorter ones)."""
        self.horizon = horizon
        columns = ["date", "event", f"abnormal_{horizon}"] + (["cluster"] if "cluster" in reactions else [])
        rows = reactions[reactions["ticker"] == ticker][columns]
        self.events = events.merge(rows, on=["date", "event"], how="left").reset_index(drop=True)
        e = self.events
        cat = e["category"].to_numpy()
        sev = e["severity"].astype(int).to_numpy()

        def equal(column):
            values = e[column].to_numpy()
            return (values[:, None] == values[None, :]).astype(float)

        self.related = np.array([[same_family(a, b) for b in cat] for a in cat])
        same_cat = cat[:, None] == cat[None, :]
        self.parts = {
            "category": np.where(same_cat, 1.0, np.where(self.related, 0.5, 0.0)),
            "region": equal("region"),
            "us_involved": equal("us_involved"),
            "severity": 1 - np.abs(sev[:, None] - sev[None, :]) / 2,
            "surprise": equal("surprise"),
        }
        self.actual = e[f"abnormal_{horizon}"].to_numpy()
        self.dates = e["date"].to_numpy()
        self.n = len(e)

    def similarity(self, weights):
        total = sum(weights[k] * self.parts[k] for k in self.parts)
        return np.round(total / sum(weights.values()) * 100)

    def pool(self, i, mode):
        """Which events the engine may use when predicting event i."""
        mask = np.ones(self.n, dtype=bool)
        mask[i] = False
        if mode == "past_only":
            mask &= self.dates < self.dates[i]
        return mask & ~np.isnan(self.actual)

    def predict(self, i, mode, sim):
        pool = self.pool(i, mode)
        if mode == "past_only" and pool.sum() < MIN_HISTORY:
            return None
        candidates = np.where(pool & self.related[i] & (sim[i] >= MIN_SIMILARITY))[0]
        if len(candidates) == 0:
            return None
        # Best similarity first, ties broken by most recent date (same as find_analogs).
        order = sorted(candidates, key=lambda j: (sim[i, j], self.dates[j]), reverse=True)[:TOP_N]
        values = self.actual[order]
        beat_share = (values > 0).mean()
        strong = int((sim[i, order] >= STRONG_MATCH).sum())
        # The confidence rule the engine used to show. Kept here only so the backtest can
        # show that it didn't predict accuracy (see by_confidence in score()).
        consistent = beat_share >= 0.75 or beat_share <= 0.25
        level = "high" if strong >= 6 and consistent else "medium" if strong >= 4 and consistent else "low"

        # Baselines, from the same pool so the comparison is fair.
        same_category = pool & (self.events["category"].to_numpy() == self.events.at[i, "category"])
        category_median = np.median(self.actual[same_category]) if same_category.any() else np.nan

        return {
            "predicted_median": float(np.median(values)),
            "beat_share": float(beat_share),
            "direction": "up" if beat_share >= 0.6 else "down" if beat_share <= 0.4 else "flat",
            "analogs": len(order),
            "strong": strong,
            "confidence": level,
            "category_median": float(category_median),
        }

    def run(self, mode, weights=WEIGHTS):
        sim = self.similarity(weights)
        rows = []
        for i in range(self.n):
            if np.isnan(self.actual[i]):
                continue
            prediction = self.predict(i, mode, sim)
            if prediction is None:
                continue
            event = self.events.iloc[i]
            rows.append({
                "date": event["date"].date(),
                "event": event["event"],
                "category": event["category"],
                "cluster": event.get("cluster"),
                f"actual_{self.horizon}": float(self.actual[i]),
                **prediction,
            })
        return pd.DataFrame(rows)


def hit(direction, actual):
    """True if a directional call was right. 'flat' (no call) returns NaN."""
    if direction == "flat":
        return np.nan
    return float((actual > 0) == (direction == "up"))


def rounded(ci):
    return None if ci is None else [round(ci[0], 1), round(ci[1], 1)]


def score(results, intervals=False, horizon="20d"):
    """Summary numbers for one backtest run.

    intervals=True adds 90% bootstrap confidence intervals (see uncertainty.py) for the hit
    rates and for the engine's edge over the always-up baseline. Off by default because
    tune() scores thousands of runs and doesn't need them.
    """
    if results.empty:
        return {"events": 0}
    r = results.copy()
    actual = f"actual_{horizon}"
    r["hit"] = [hit(d, a) for d, a in zip(r["direction"], r[actual])]
    r["always_up_hit"] = (r[actual] > 0).astype(float)
    has_cat = r["category_median"].notna()
    r["category_hit"] = np.where(
        has_cat, ((r["category_median"] > 0) == (r[actual] > 0)).astype(float), np.nan)
    calls = r["hit"].notna()

    def pct(series):
        series = series.dropna()
        return round(float(series.mean()) * 100, 1) if len(series) else None

    by_confidence = {}
    for level in ["high", "medium", "low"]:
        subset = r[(r["confidence"] == level) & calls]
        by_confidence[level] = {"calls": int(len(subset)), "hit_rate": pct(subset["hit"])}

    summary = {
        "events": int(len(r)),
        "calls": int(calls.sum()),
        "coverage": round(float(calls.mean()) * 100, 1),
        "hit_rate": pct(r["hit"]),
        # Baselines judged on the SAME events the engine made a call on.
        "always_up_hit_rate": pct(r.loc[calls, "always_up_hit"]),
        "category_hit_rate": pct(r.loc[calls, "category_hit"]),
        "mae": round(float((r["predicted_median"] - r[actual]).abs().mean()), 2),
        "category_mae": round(float((r.loc[has_cat, "category_median"] - r.loc[has_cat, actual]).abs().mean()), 2),
        "by_confidence": by_confidence,
    }
    if intervals:
        made = r[calls]
        # Resample whole clusters of overlapping events when we know them (see uncertainty.py).
        clusters = made["cluster"].to_numpy() if "cluster" in made and made["cluster"].notna().all() else None
        summary["hit_rate_ci"] = rounded(share_ci(made["hit"], clusters=clusters))
        summary["always_up_ci"] = rounded(share_ci(made["always_up_hit"], clusters=clusters))
        # The gap is resampled event by event (or cluster by cluster), so engine and baseline
        # are judged on the same draws.
        summary["edge_ci"] = rounded(paired_gap_ci(made["hit"], made["always_up_hit"], clusters=clusters))
    return summary


def track_record(events, reactions, ticker="ITA", weights=WEIGHTS):
    """Backtest summary for both modes, plus each event's prediction (for charts and tables)."""
    bt = Backtester(events, reactions, ticker=ticker)
    record = {}
    for mode in MODES:
        results = bt.run(mode, weights)
        record[mode] = score(results, intervals=True)
        record[f"{mode}_rows"] = results
    return record


def tune(events, reactions):
    """Try many weight combinations, scoring each across EVERY ticker in both modes.

    Tuning on one stock overfits: in Nov 2026 a set tuned on ITA alone looked 5 points better
    than the baseline there, but fell 4.7 points below it across all stocks. Averaging over
    11 stocks and both modes makes it much harder for luck to win.
    Returns a table, best first, by average points above the "always beats the market" baseline.
    """
    from calculate_reactions import DEFENSE_TICKERS

    testers = [Backtester(events, reactions, ticker=t) for t in DEFENSE_TICKERS]
    grid = {
        "category": [2, 4, 6],
        "region": [0, 1, 2, 4],
        "us_involved": [0, 1.5, 3],
        "severity": [0, 1.5, 3],
        "surprise": [0, 1, 2],
    }
    rows = []
    for values in itertools.product(*grid.values()):
        weights = dict(zip(grid.keys(), values))
        row = dict(weights)
        for mode in MODES:
            scores = [score(bt.run(mode, weights)) for bt in testers]
            row[f"{mode}_hit"] = round(float(np.mean([s["hit_rate"] for s in scores])), 1)
            row[f"{mode}_edge"] = round(float(np.mean([s["hit_rate"] - s["always_up_hit_rate"] for s in scores])), 1)
            row[f"{mode}_coverage"] = round(float(np.mean([s["coverage"] for s in scores])), 1)
        rows.append(row)
    table = pd.DataFrame(rows)
    # An engine that rarely makes a call isn't useful.
    table = table[(table["leave_one_out_coverage"] >= 60) & (table["past_only_coverage"] >= 60)]
    table["edge"] = (table["leave_one_out_edge"] + table["past_only_edge"]) / 2
    return table.sort_values("edge", ascending=False)


def test_matches_find_analogs(events, reactions):
    """Safety check: the fast version must pick the same analogs as find_analogs()."""
    from find_analogs import find_analogs
    bt = Backtester(events, reactions)
    sim = bt.similarity(WEIGHTS)
    for i in range(0, bt.n, 7):
        tags = events.iloc[i][["category", "region", "us_involved", "severity", "surprise"]].to_dict()
        pool = events.drop(index=i)
        slow = find_analogs(tags, pool, top_n=TOP_N, reactions=reactions)["event"].tolist()
        candidates = np.where(bt.pool(i, "leave_one_out") & bt.related[i] & (sim[i] >= MIN_SIMILARITY))[0]
        fast_idx = sorted(candidates, key=lambda j: (sim[i, j], bt.dates[j]), reverse=True)[:TOP_N]
        fast = bt.events.loc[fast_idx, "event"].tolist()
        assert slow == fast, f"Mismatch for {events.iloc[i]['event']}:\n{slow}\n{fast}"
    print("Check passed: fast backtester matches find_analogs()")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="ITA")
    parser.add_argument("--tune", action="store_true")
    args = parser.parse_args()

    events = load_events("data/events.csv")
    reactions = load_reactions("data/event_reactions.csv")
    test_matches_find_analogs(events, reactions)

    bt = Backtester(events, reactions, ticker=args.ticker)
    for mode in MODES:
        results = bt.run(mode)
        results.to_csv(f"data/backtest_{mode}_{args.ticker}.csv", index=False)
        print(f"\n=== {mode} ({args.ticker}) ===")
        for key, value in score(results, intervals=True).items():
            print(f"  {key}: {value}")

    if args.tune:
        print("\nSearching weights across all tickers (takes a few minutes)...")
        table = tune(events, reactions)
        print("Top 10 weight sets by average points above the always-up baseline:")
        print(table.head(10).to_string(index=False))
        current = table
        for key, value in WEIGHTS.items():
            current = current[current[key] == value]
        print("\nCurrent weights:")
        print(current.to_string(index=False) if len(current) else "  (not in the search grid)")
