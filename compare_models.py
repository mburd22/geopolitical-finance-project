# Does the choice of abnormal-return model change any conclusion?
#
# Re-measures every event with each model in calculate_reactions.MODELS:
#   market  stock return - market return (beta 1, no alpha), the project default
#   beta    stock return - (alpha + beta x market return), fitted on the 120 trading days
#           ending 10 days before each event
# then reruns the headline numbers on each: category averages, the backtest across all 11
# stocks, and the run-up test. Nothing is saved; it only prints a side-by-side report.
#
# Run:  .\.venv\Scripts\python.exe compare_models.py            (about a minute)
#       .\.venv\Scripts\python.exe compare_models.py --tune     (also re-tune weights per model, slow)

import argparse

import numpy as np
import pandas as pd

import runup
from backtest import MODES, Backtester, score, tune
from calculate_reactions import (
    DEFENSE_TICKERS, MARKETS, MODELS, first_reaction_day, fit_market_model, load_all_prices, load_events,
    measure_all,
)
from find_analogs import WEIGHTS


def category_table(reactions, ticker):
    """Average 20-day abnormal return and beat-the-market rate per category, for one ticker."""
    rows = reactions[reactions["ticker"] == ticker]
    return rows.groupby("category").agg(
        events=("abnormal_20d", "size"),
        avg_20d=("abnormal_20d", "mean"),
        beat_pct=("abnormal_20d", lambda v: (v > 0).mean() * 100),
    ).round(1)


def backtest_summary(events, reactions):
    """Engine hit rate and the always-up baseline, averaged over every ticker, per mode."""
    out = {}
    for mode in MODES:
        scores = [score(Backtester(events, reactions, ticker=t).run(mode, WEIGHTS)) for t in DEFENSE_TICKERS]
        out[mode] = {
            "engine": round(float(np.mean([s["hit_rate"] for s in scores])), 1),
            "always_up": round(float(np.mean([s["always_up_hit_rate"] for s in scores])), 1),
            "coverage": round(float(np.mean([s["coverage"] for s in scores])), 1),
        }
    return out


def event_betas(prices, events):
    """Each ticker's fitted beta averaged across events: how far the beta model departs from beta 1."""
    betas = {}
    for name, market in MARKETS.items():
        table = prices[name]
        for ticker in market["tickers"]:
            values = []
            for date, after in zip(events["date"], events["after_close"]):
                fit = fit_market_model(table, ticker, market["benchmark"],
                                       first_reaction_day(table.index, date, after))
                if fit:
                    values.append(fit[1])
            betas[ticker] = round(float(np.mean(values)), 2)
    return betas


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune", action="store_true")
    args = parser.parse_args()

    prices = load_all_prices()
    events = load_events("data/events.csv")
    measured = {}
    for model in MODELS:
        reactions = measure_all(prices, events, model)[0]
        reactions["date"] = pd.to_datetime(reactions["date"])  # as load_reactions() would read it back
        measured[model] = reactions

    print("Average fitted beta per stock (vs its own market), across events:")
    print(event_betas(prices, events))

    for ticker in ["ITA", "EUDEF"]:
        tables = [category_table(measured[m], ticker).add_prefix(f"{m}_") for m in MODELS]
        print(f"\n{ticker}: 20-day abnormal return by category, in %")
        print(pd.concat(tables, axis=1).sort_values(f"{MODELS[0]}_avg_20d", ascending=False).to_string())

    print("\nHow much the two models disagree per event (20-day abnormal, all tickers):")
    a = measured["market"].set_index(["date", "event", "ticker"])["abnormal_20d"]
    b = measured["beta"].set_index(["date", "event", "ticker"])["abnormal_20d"]
    print(f"  correlation {a.corr(b):.3f}, mean absolute gap {(a - b).abs().mean():.2f} points, "
          f"sign flips {int(((a > 0) != (b > 0)).sum())} of {len(a)}")

    print("\nBacktest, averaged over all 11 stocks (current weights):")
    for model in MODELS:
        print(f"  {model:7}", backtest_summary(events, measured[model]))

    # The always-up baseline is "defense beats the market after an event". Is that about
    # events at all? Compare with how often each stock beat its market over ANY 20 days.
    print("\nHow often each stock beat its market over 20 trading days: after events vs on ordinary days")
    print(f"{'ticker':10}" + "".join(f"{m + ' events':>15}{m + ' ordinary':>17}" for m in MODELS))
    for ticker in DEFENSE_TICKERS:
        cells = []
        for model in MODELS:
            rows = measured[model]
            after_events = (rows.loc[rows["ticker"] == ticker, "abnormal_20d"] > 0).mean() * 100
            ordinary = (runup.ordinary_days(prices, ticker, 60, model=model)["after"] > 0).mean() * 100
            cells.append(f"{after_events:>14.1f}%{ordinary:>16.1f}%")
        print(f"{ticker:10}" + "".join(cells))

    print("\nRun-up test (60d run-up vs 20d after): event vs ordinary-day rank correlation")
    print(f"{'ticker':10}" + "".join(f"{m + ' event':>14}{m + ' ordinary':>17}" for m in MODELS))
    for ticker in DEFENSE_TICKERS:
        cells = []
        for model in MODELS:
            result = runup.analyze(measured[model], prices, ticker, "60d", model=model)
            cells.append(f"{result['event_corr']:>14}{result['ordinary_corr']:>17}")
        print(f"{ticker:10}" + "".join(cells))

    if args.tune:
        for model in MODELS:
            print(f"\nTuning weights across all tickers with the {model} model (a few minutes)...")
            table = tune(events, measured[model])
            print(table.head(5).to_string(index=False))
            current = table
            for key, value in WEIGHTS.items():
                current = current[current[key] == value]
            print("Current weights:", current.to_string(index=False, header=False) if len(current) else "(not in grid)")
