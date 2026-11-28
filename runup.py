# Does a big run-up before an event predict a weaker reaction after it?
#
# For every event we know (from calculate_reactions.py):
#   runup_60d / runup_20d  how far the stock had beaten its market in the 60 / 20 trading days before
#   abnormal_20d           how far it beat its market in the 20 trading days after
#
# Two questions, answered separately because they mean different things:
#   1. Is there a relationship at all? (rank correlation, and averages by run-up third)
#   2. Is it special to events, or do defense stocks just mean-revert on any day?
#      We repeat the same measurement on ordinary days as a control.
#
# Run:  .\.venv\Scripts\python.exe runup.py

import numpy as np
import pandas as pd

from calculate_reactions import (
    BASKETS, DEFENSE_TICKERS, abnormal, benchmark_for, expected_prices, load_all_prices, prices_for,
)
from find_analogs import load_reactions

AFTER_DAYS = 20
RNG = np.random.default_rng(0)  # fixed seed so the permutation test gives the same answer each run


def rank_corr(x, y):
    """Spearman rank correlation: does a higher x tend to go with a higher y (+1) or lower y (-1)?"""
    return float(pd.Series(x).rank().corr(pd.Series(y).rank()))


def permutation_p(x, y, shuffles=5000):
    """How often a correlation at least this negative appears if run-ups and outcomes are shuffled at random."""
    observed = rank_corr(x, y)
    y = np.asarray(y)
    count = sum(rank_corr(x, RNG.permutation(y)) <= observed for _ in range(shuffles))
    return (count + 1) / (shuffles + 1)


def by_thirds(frame, runup_col):
    """Average later move and beat-the-market rate for the lowest, middle and highest third of run-ups."""
    labels = ["lowest third", "middle third", "highest third"]
    thirds = pd.qcut(frame[runup_col], 3, labels=labels)
    table = frame.groupby(thirds, observed=True).agg(
        events=("abnormal_20d", "size"),
        avg_runup=(runup_col, "mean"),
        avg_after=("abnormal_20d", "mean"),
        beat_market=("abnormal_20d", lambda v: (v > 0).mean() * 100),
    )
    return table.round(1)


def event_sample(reactions, ticker, runup_col):
    rows = reactions[reactions["ticker"] == ticker].dropna(subset=[runup_col, "abnormal_20d"])
    return rows[["date", "event", "category", runup_col, "abnormal_20d"]]


def ordinary_days(prices, ticker, runup_days, step=AFTER_DAYS, model=None):
    """The same before/after measurement on ordinary days, every `step` trading days so windows
    don't overlap. Returns a DataFrame with columns runup and after."""
    table = prices_for(prices, ticker)
    bench = benchmark_for(ticker)
    rows = []
    for base in range(runup_days, len(table) - AFTER_DAYS, step):
        # Treat the day after `base` as a pretend reaction day, exactly as for a real event.
        expected = expected_prices(table, ticker, bench, base + 1, model)
        before = abnormal(table, ticker, expected, base - runup_days, base)
        after = abnormal(table, ticker, expected, base, base + AFTER_DAYS)
        rows.append({"runup": before * 100, "after": after * 100})
    return pd.DataFrame(rows)


def analyze(reactions, prices, ticker, window="60d", model=None):
    """Everything the dashboard and the report need for one ticker.
    model: the abnormal-return model the reactions were measured with (default ABNORMAL_MODEL)."""
    col = f"runup_{window}"
    events = event_sample(reactions, ticker, col)
    control = ordinary_days(prices, ticker, int(window[:-1]), model=model)
    return {
        "ticker": ticker,
        "window": window,
        "events": len(events),
        "event_corr": round(rank_corr(events[col], events["abnormal_20d"]), 3),
        "event_p": round(permutation_p(events[col].to_numpy(), events["abnormal_20d"].to_numpy()), 4),
        "ordinary_corr": round(rank_corr(control["runup"], control["after"]), 3),
        "ordinary_days": len(control),
        "thirds": by_thirds(events, col),
        "points": events,
    }


if __name__ == "__main__":
    reactions = load_reactions("data/event_reactions.csv")
    prices = load_all_prices()

    for window in ["60d", "20d"]:
        print(f"\n===== Run-up over the {window} before the event vs the 20 days after =====")
        print(f"{'ticker':10} {'events':>6} {'event corr':>10} {'p-value':>8} {'ordinary-day corr':>17}")
        for ticker in DEFENSE_TICKERS:
            a = analyze(reactions, prices, ticker, window)
            print(f"{ticker:10} {a['events']:>6} {a['event_corr']:>10} {a['event_p']:>8} {a['ordinary_corr']:>17}")
        for basket in BASKETS:
            a = analyze(reactions, prices, basket, window)
            print(f"\n{basket}, by run-up third:")
            print(a["thirds"].to_string())
