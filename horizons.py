# Would the analog engine do better predicting a shorter move?
#
# The engine predicts whether a stock beats its market over the 20 trading days after an
# event. But a permutation test (uncertainty.groups_differ_p, shown on the By event type
# tab) says event type goes with the day-1 and 5-day moves far more than with the 20-day
# move. So this reruns the same backtest, same weights, at all three horizons, averaged over
# all 11 stocks, next to the "always beats the market" baseline.
#
# Run:  .\.venv\Scripts\python.exe horizons.py

import numpy as np

from backtest import MODES, Backtester, score
from calculate_reactions import DEFENSE_TICKERS, MARKET_OF, WINDOWS, load_events
from find_analogs import WEIGHTS, load_reactions


def horizon_scores(events, reactions, horizon, weights=WEIGHTS, tickers=DEFENSE_TICKERS):
    """{mode: {ticker: score}} for one horizon."""
    out = {mode: {} for mode in MODES}
    for ticker in tickers:
        bt = Backtester(events, reactions, ticker=ticker, horizon=horizon)
        for mode in MODES:
            out[mode][ticker] = score(bt.run(mode, weights), intervals=True, horizon=horizon)
    return out


def summary(scores, tickers):
    engine = np.mean([scores[t]["hit_rate"] for t in tickers])
    baseline = np.mean([scores[t]["always_up_hit_rate"] for t in tickers])
    clear_wins = sum(scores[t]["edge_ci"][0] > 0 for t in tickers)
    clear_losses = sum(scores[t]["edge_ci"][1] < 0 for t in tickers)
    return engine, baseline, clear_wins, clear_losses


if __name__ == "__main__":
    events = load_events("data/events.csv")
    reactions = load_reactions("data/event_reactions.csv")
    groups = {"all 11": DEFENSE_TICKERS,
              "US": [t for t in DEFENSE_TICKERS if MARKET_OF[t] == "US"],
              "Europe": [t for t in DEFENSE_TICKERS if MARKET_OF[t] == "EU"]}

    print("Share of directional calls right, engine vs 'always beats the market', by horizon.")
    print("Clear win/loss = stocks whose 90% range for (engine - baseline) is entirely above/below zero.\n")
    print(f"{'horizon':8} {'mode':14} {'stocks':7} {'engine':>7} {'baseline':>9} {'edge':>6} {'clear wins':>11} {'clear losses':>13}")
    for horizon in WINDOWS:
        scores = horizon_scores(events, reactions, horizon)
        for mode in MODES:
            for name, tickers in groups.items():
                engine, baseline, wins, losses = summary(scores[mode], tickers)
                print(f"{horizon:8} {mode:14} {name:7} {engine:6.1f}% {baseline:8.1f}% {engine - baseline:+6.1f} "
                      f"{wins:>11} {losses:>13}")
        print()
