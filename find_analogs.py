# Step 6: the analog matcher.
# Describe a new event, find the most similar past events, and summarize
# how defense stocks reacted to them.
#
# Example (run from the terminal):
#   .\.venv\Scripts\python.exe find_analogs.py --category escalation --region east_asia --us-involved yes --severity 3 --surprise yes

import argparse  # reads options typed after the script name in the terminal

import pandas as pd

from calculate_reactions import load_events

# Categories that are "cousins": not the same, but closer to each other than to, say, an election.
# Each set is one family. A match within a family earns partial credit.
CATEGORY_FAMILIES = [
    {"war_outbreak", "military_strike", "escalation", "weapons_test"},  # conflict getting hotter
    {"de_escalation"},
    {"terrorism"},
    {"coup", "election"},  # change of who's in power
    {"defense_spending"},
]

# How many points each kind of similarity is worth (scores are scaled to 0-100).
# Chosen by backtest.py --tune, scored across all 11 stocks (Nov 2026, 113 events).
# History: the first guesses (category 4, region 2, us_involved 1.5, severity 1.5, surprise 1)
# were a coin flip. A severity-heavy set tuned on ITA alone with 71 events looked better (67%)
# but was overfit: on 113 events across all stocks it fell 4.7 points below the "always beats
# the market" baseline. Matching on event type and region only, equally weighted, holds up best,
# though no weighting beats that baseline on average. Re-run the tuning whenever events are added.
WEIGHTS = {
    "category": 4.0,
    "region": 4.0,
    "us_involved": 0.0,
    "severity": 0.0,
    "surprise": 0.0,
}
STRONG_MATCH = 70  # similarity % at which we call an analog a strong match
MIN_SIMILARITY = 50  # below this, a past event isn't really comparable, so we leave it out


def same_family(a, b):
    """True if two categories belong to the same family."""
    return any(a in family and b in family for family in CATEGORY_FAMILIES)


def similarity(new_event, past_event, weights=WEIGHTS):
    """Score how alike two events are, from 0 (nothing in common) to 100 (identical tags)."""
    score = 0.0

    if new_event["category"] == past_event["category"]:
        score += weights["category"]
    elif same_family(new_event["category"], past_event["category"]):
        score += weights["category"] / 2  # half credit for a cousin

    if new_event["region"] == past_event["region"]:
        score += weights["region"]

    if new_event["us_involved"] == past_event["us_involved"]:
        score += weights["us_involved"]

    # Severity is a scale (1-3), so close counts: a difference of 1 earns half the points.
    gap = abs(int(new_event["severity"]) - int(past_event["severity"]))
    score += weights["severity"] * (1 - gap / 2)

    if new_event["surprise"] == past_event["surprise"]:
        score += weights["surprise"]

    return round(score / sum(weights.values()) * 100)


def find_analogs(new_event, events, top_n=8, weights=WEIGHTS, reactions=None):
    """Return up to top_n most similar past events, best first, with a 'similarity' column.

    reactions: if given, only events with a measured reaction can be analogs. A very recent
    event whose 20-day window hasn't finished would otherwise take a slot and then drop out.
    """
    if reactions is not None:
        measured = set(zip(reactions["date"], reactions["event"]))
        events = events[[(d, e) in measured for d, e in zip(events["date"], events["event"])]]
    # An event of an unrelated type is never a true analog, however well the other tags match:
    # a NATO spending deal is the opposite of a ceasefire, even if both are in Europe.
    related = [same_family(new_event["category"], category) for category in events["category"]]
    scored = events[related].copy()
    scored["similarity"] = [similarity(new_event, past, weights) for _, past in scored.iterrows()]
    scored = scored[scored["similarity"] >= MIN_SIMILARITY]
    # Ties are broken by date, most recent first, since recent markets are more relevant.
    return scored.sort_values(["similarity", "date"], ascending=False).head(top_n)


def load_reactions(path):
    reactions = pd.read_csv(path)
    reactions["date"] = pd.to_datetime(reactions["date"])
    return reactions


def summarize(analogs, reactions, ticker="ITA"):
    """Join the analogs to their measured reactions and compute summary statistics."""
    # merge works like a VLOOKUP in Excel: match rows from two tables on shared columns.
    matched = analogs.merge(
        reactions[reactions["ticker"] == ticker],
        on=["date", "event"],
        suffixes=("", "_reaction"),
    )
    stats = {}
    for window in ["1d", "5d", "20d"]:
        values = matched[f"abnormal_{window}"]
        stats[window] = {
            "median": values.median(),
            "low": values.min(),
            "high": values.max(),
            "beat_market": int((values > 0).sum()),
        }
    return matched, stats


def track_record_sentence(record, ticker):
    """One sentence on how often the engine has been right for this stock, from backtest.track_record()."""
    loo, past = record["leave_one_out"], record["past_only"]
    return (f"Track record: in backtests the engine called {ticker}'s direction right "
            f"{loo['hit_rate']:.0f}% of the time ({past['hit_rate']:.0f}% using only earlier events), "
            f"vs {loo['always_up_hit_rate']:.0f}% for simply assuming defense beats the market.")


def write_thesis(new_event, matched, stats, ticker="ITA", track_record=None):
    """Turn the numbers into a short written thesis.

    track_record: optional backtest results (see backtest.track_record). An earlier version
    showed a high/medium/low confidence label here, but the backtest showed it didn't predict
    accuracy ("high" calls were right less often than "low" ones), so the real hit rate is shown instead.
    """
    n = len(matched)
    s20, s1 = stats["20d"], stats["1d"]
    strong = int((matched["similarity"] >= STRONG_MATCH).sum())
    closest = ", ".join(f"{row.event} ({row.date.year})" for row in matched.head(3).itertuples())

    if s20["beat_market"] / n >= 0.6:
        direction = "outperform"
    elif s20["beat_market"] / n <= 0.4:
        direction = "underperform"
    else:
        direction = "track"

    if abs(s1["median"]) >= 1:
        speed = f"Markets have usually reacted right away (median day-one move {s1['median']:+.1f}%)."
    else:
        speed = (f"Day one has usually been quiet (median {s1['median']:+.1f}%), "
                 f"so most of any move tends to build over the following weeks.")

    warning = ""
    if not (matched["region"] == new_event["region"]).any():
        warning = f"\nWarning: none of these analogs happened in {new_event['region']}, so treat this with extra caution."

    # If confound checks were run (see confounds.py), say how many analogs are affected,
    # and what the result looks like using only the "clean" ones.
    if "confounds" in matched.columns:
        flagged = matched["confounds"].apply(len) > 0
        if flagged.any():
            warning += (f"\nConfounds: {int(flagged.sum())} of {n} analogs had earnings, another event "
                        f"or market turmoil in their window.")
            clean = matched.loc[~flagged, "abnormal_20d"]
            if len(clean) >= 3:
                warning += (f" Using only the {len(clean)} clean analogs, the median 20-day result "
                            f"is {clean.median():+.1f}% ({int((clean > 0).sum())} of {len(clean)} beat the market).")
            else:
                warning += " Too few clean analogs to compare separately."

    record = f"{track_record_sentence(track_record, ticker)} " if track_record else ""
    return (
        f"Thesis: {ticker} is likely to {direction} the market over the next month.\n"
        f"In {n} similar past events (closest: {closest}), {ticker} beat the market over 20 trading days "
        f"in {s20['beat_market']} of {n} cases, by a median of {s20['median']:+.1f}% "
        f"(range {s20['low']:+.1f}% to {s20['high']:+.1f}%). {speed}\n"
        f"{record}{strong} of {n} analogs are close matches ({STRONG_MATCH}%+ similarity). "
        f"This is a historical base rate, not a forecast or investment advice."
        f"{warning}"
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Find past events similar to a new one.")
    parser.add_argument("--category", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--us-involved", choices=["yes", "no"], required=True)
    parser.add_argument("--severity", choices=["1", "2", "3"], required=True)
    parser.add_argument("--surprise", choices=["yes", "no"], required=True)
    parser.add_argument("--ticker", default="ITA")
    parser.add_argument("--top", type=int, default=8)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    new_event = {
        "category": args.category,
        "region": args.region,
        "us_involved": args.us_involved,
        "severity": args.severity,
        "surprise": args.surprise,
    }

    from calculate_reactions import load_all_prices
    from confounds import find_confounds, load_earnings

    prices = load_all_prices()
    events = load_events("data/events.csv")
    reactions = load_reactions("data/event_reactions.csv")
    earnings = load_earnings("data/earnings.csv")

    analogs = find_analogs(new_event, events, top_n=args.top, reactions=reactions)
    if analogs.empty:
        print("No comparable past events found. Try adding more events of this type to data/events.csv.")
        raise SystemExit  # stop the script here
    matched, stats = summarize(analogs, reactions, ticker=args.ticker)
    matched["confounds"] = [
        find_confounds(prices, events, earnings, row, ticker=args.ticker) for _, row in matched.iterrows()
    ]

    print("Your event:", new_event)
    print()
    print(f"Most similar past events ({args.ticker} vs the market, %):")
    columns = ["similarity", "date", "event", "category", "abnormal_1d", "abnormal_5d", "abnormal_20d"]
    table = matched[columns].copy()
    table["date"] = table["date"].dt.date
    print(table.to_string(index=False))
    print()
    from backtest import track_record
    record = track_record(events, reactions, args.ticker)
    print(write_thesis(new_event, matched, stats, ticker=args.ticker, track_record=record))
