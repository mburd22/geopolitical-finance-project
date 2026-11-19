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

# How many points each kind of similarity is worth. These add up to 10.
# Changing these numbers changes what the matcher cares about most. Try it!
WEIGHTS = {
    "category": 4.0,
    "region": 2.0,
    "us_involved": 1.5,
    "severity": 1.5,
    "surprise": 1.0,
}
MAX_SCORE = sum(WEIGHTS.values())

STRONG_MATCH = 70  # similarity % at which we call an analog a strong match
MIN_SIMILARITY = 50  # below this, a past event isn't really comparable, so we leave it out


def same_family(a, b):
    """True if two categories belong to the same family."""
    return any(a in family and b in family for family in CATEGORY_FAMILIES)


def similarity(new_event, past_event):
    """Score how alike two events are, from 0 (nothing in common) to 100 (identical tags)."""
    score = 0.0

    if new_event["category"] == past_event["category"]:
        score += WEIGHTS["category"]
    elif same_family(new_event["category"], past_event["category"]):
        score += WEIGHTS["category"] / 2  # half credit for a cousin

    if new_event["region"] == past_event["region"]:
        score += WEIGHTS["region"]

    if new_event["us_involved"] == past_event["us_involved"]:
        score += WEIGHTS["us_involved"]

    # Severity is a scale (1-3), so close counts: a difference of 1 earns half the points.
    gap = abs(int(new_event["severity"]) - int(past_event["severity"]))
    score += WEIGHTS["severity"] * (1 - gap / 2)

    if new_event["surprise"] == past_event["surprise"]:
        score += WEIGHTS["surprise"]

    return round(score / MAX_SCORE * 100)


def find_analogs(new_event, events, top_n=8):
    """Return up to top_n most similar past events, best first, with a 'similarity' column."""
    # An event of an unrelated type is never a true analog, however well the other tags match:
    # a NATO spending deal is the opposite of a ceasefire, even if both are in Europe.
    related = [same_family(new_event["category"], category) for category in events["category"]]
    scored = events[related].copy()
    scored["similarity"] = [similarity(new_event, past) for _, past in scored.iterrows()]
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


def confidence(matched, stats):
    """A rough, honest label for how much to trust the result."""
    strong = int((matched["similarity"] >= STRONG_MATCH).sum())
    beat_share = stats["20d"]["beat_market"] / len(matched)
    consistent = beat_share >= 0.75 or beat_share <= 0.25  # most analogs agree on direction
    if strong >= 6 and consistent:
        return "high", strong
    if strong >= 4 and consistent:
        return "medium", strong
    return "low", strong


def write_thesis(new_event, matched, stats, ticker="ITA"):
    """Turn the numbers into a short written thesis."""
    n = len(matched)
    s20, s1 = stats["20d"], stats["1d"]
    level, strong = confidence(matched, stats)
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

    return (
        f"Thesis: {ticker} is likely to {direction} the market over the next month.\n"
        f"In {n} similar past events (closest: {closest}), {ticker} beat the market over 20 trading days "
        f"in {s20['beat_market']} of {n} cases, by a median of {s20['median']:+.1f}% "
        f"(range {s20['low']:+.1f}% to {s20['high']:+.1f}%). {speed}\n"
        f"Confidence: {level} ({strong} of {n} analogs are strong matches of {STRONG_MATCH}%+ similarity). "
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

    from calculate_reactions import load_prices
    from confounds import find_confounds, load_earnings

    prices = load_prices("data/prices.csv")
    events = load_events("data/events.csv")
    reactions = load_reactions("data/event_reactions.csv")
    earnings = load_earnings("data/earnings.csv")

    analogs = find_analogs(new_event, events, top_n=args.top)
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
    print(write_thesis(new_event, matched, stats, ticker=args.ticker))
