# Is Europe's reaction to events just the post-2022 rearmament rally?
#
# European defense stocks have beaten their market by a lot since Russia invaded Ukraine,
# so "they beat the market after events" could simply be that trend. This splits the sample
# at the invasion and, in each half, compares the 20 days after events with ordinary 20-day
# spells from the same years (the control from runup.py).
#
# Run:  .\.venv\Scripts\python.exe regimes.py

import pandas as pd

from calculate_reactions import BASKETS, load_all_prices, prices_for
from find_analogs import load_reactions
from runup import AFTER_DAYS, ordinary_days
from uncertainty import bootstrap_ci

CUT = pd.Timestamp("2022-02-24")  # Russia's full-scale invasion of Ukraine
RUNUP_DAYS = 60                   # ordinary_days() starts after this much history


def ordinary_spells(prices, ticker):
    """Ordinary 20-day spells (from runup.ordinary_days) with the date each one starts."""
    table = prices_for(prices, ticker)
    spells = ordinary_days(prices, ticker, RUNUP_DAYS)
    spells.index = table.index[RUNUP_DAYS:len(table) - AFTER_DAYS:AFTER_DAYS][:len(spells)]
    return spells["after"]


def describe(values, clusters=None):
    ci = bootstrap_ci(values, clusters=clusters)
    return {"n": int(len(values)), "avg": round(float(values.mean()), 2),
            "ci": None if ci is None else [round(ci[0], 2), round(ci[1], 2)],
            "beat_pct": round(float((values > 0).mean() * 100), 1)}


def split_summary(reactions, prices, ticker, cut=CUT):
    """{"before": {...}, "from": {...}}, each with "events" and "ordinary" summaries."""
    rows = reactions[reactions["ticker"] == ticker]
    spells = ordinary_spells(prices, ticker)
    out = {}
    for name, in_half, spell_half in [("before", rows["date"] < cut, spells.index < cut),
                                      ("from", rows["date"] >= cut, spells.index >= cut)]:
        half = rows[in_half]
        out[name] = {"events": describe(half["abnormal_20d"], half.get("cluster")),
                     "ordinary": describe(spells[spell_half])}
    return out


if __name__ == "__main__":
    reactions = load_reactions("data/event_reactions.csv")
    prices = load_all_prices()
    print(f"20-day return vs the market, split at {CUT.date()}: after events vs ordinary spells\n")
    for ticker in BASKETS:
        for half, parts in split_summary(reactions, prices, ticker).items():
            e, o = parts["events"], parts["ordinary"]
            print(f"{ticker:6} {half:6} events {e['n']:3}: avg {e['avg']:+5.1f}% (90% {e['ci'][0]:+.1f} to "
                  f"{e['ci'][1]:+.1f}), beat {e['beat_pct']:.0f}%  |  ordinary {o['n']:3}: avg {o['avg']:+5.1f}%, "
                  f"beat {o['beat_pct']:.0f}%")
