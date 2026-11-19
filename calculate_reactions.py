# Step 4: measure how each defense stock reacted to each event, compared with the market.
#
# Key idea: ABNORMAL RETURN = stock's return - market's return over the same days.
# If LMT rose 5% while SPY (the whole market) rose 2%, the abnormal return is +3%.
# That +3% is the part of the move we can plausibly link to the event.

import pandas as pd

DEFENSE_TICKERS = ["LMT", "RTX", "NOC", "GD", "ITA"]
MARKET_TICKER = "SPY"

# How many trading days after the event to measure. Day 0 is the first day markets
# could react, so a 5-day window covers day 0 through day 4.
WINDOWS = {"1d": 1, "5d": 5, "20d": 20}


def load_prices(path):
    # index_col=0 makes the date column the row labels; parse_dates turns text into real dates.
    return pd.read_csv(path, index_col=0, parse_dates=True)


def load_events(path):
    events = pd.read_csv(path, dtype=str)
    events = events.apply(lambda column: column.str.strip())
    events["date"] = pd.to_datetime(events["date"])
    return events.sort_values("date").reset_index(drop=True)


def first_reaction_day(trading_days, event_date, after_close):
    """Return the position of the first trading day the market could react to the event."""
    # searchsorted finds where event_date would slot into the sorted list of trading days.
    # side="left" lands ON the event date if it was a trading day (news broke during or before the session).
    # side="right" skips past it (news broke after the close, so the reaction starts the next day).
    # Weekends and holidays aren't in the list, so both naturally roll forward to the next open day.
    side = "right" if after_close == "yes" else "left"
    return trading_days.searchsorted(event_date, side=side)


def measure_event(prices, event):
    """Return a list of result rows (one per defense ticker) for a single event."""
    trading_days = prices.index
    day0 = first_reaction_day(trading_days, event["date"], event["after_close"])

    # The baseline is the close on the trading day BEFORE the reaction: the last price before the news.
    baseline = day0 - 1
    longest = max(WINDOWS.values())
    if baseline < 0 or day0 + longest - 1 >= len(trading_days):
        return []  # not enough price history on one side of this event, so skip it

    rows = []
    for ticker in DEFENSE_TICKERS:
        row = {
            "date": event["date"].date(),
            "event": event["event"],
            "category": event["category"],
            "region": event["region"],
            "reaction_day": trading_days[day0].date(),
            "ticker": ticker,
        }
        for name, days in WINDOWS.items():
            end = day0 + days - 1
            # .iloc picks rows by position. Return = end price / start price - 1.
            stock_return = prices[ticker].iloc[end] / prices[ticker].iloc[baseline] - 1
            market_return = prices[MARKET_TICKER].iloc[end] / prices[MARKET_TICKER].iloc[baseline] - 1
            # Multiply by 100 to store percentages, round to keep the file readable.
            row[f"return_{name}"] = round(stock_return * 100, 2)
            row[f"market_{name}"] = round(market_return * 100, 2)
            row[f"abnormal_{name}"] = round((stock_return - market_return) * 100, 2)
        rows.append(row)
    return rows


# Everything below only runs when you run THIS file directly
# (python calculate_reactions.py). When another script does
# "from calculate_reactions import load_prices", Python skips this block,
# so it can reuse the functions above without redoing all the calculations.
if __name__ == "__main__":
    prices = load_prices("data/prices.csv")
    events = load_events("data/events.csv")

    all_rows = []
    skipped = []
    # .iterrows() loops over a table one row at a time.
    for _, event in events.iterrows():
        rows = measure_event(prices, event)
        if rows:
            all_rows.extend(rows)  # extend adds every item from one list onto another
        else:
            skipped.append(event["event"])

    reactions = pd.DataFrame(all_rows)
    reactions.to_csv("data/event_reactions.csv", index=False)

    # Count events by date AND name together: two different events can share a name
    # (there are two "Trump wins US election" rows, in 2016 and 2024).
    event_count = len(reactions[["date", "event"]].drop_duplicates())
    print(f"Measured {event_count} events x {len(DEFENSE_TICKERS)} tickers = {len(reactions)} rows")
    print("Saved to data/event_reactions.csv")
    if skipped:
        print("Skipped (not enough price data):", skipped)

    # A first summary: the average abnormal return for the defense ETF (ITA) by event category.
    # groupby splits the table into groups, then .agg calculates something for each group.
    ita = reactions[reactions["ticker"] == "ITA"]
    summary = ita.groupby("category").agg(
        events=("event", "count"),
        avg_abnormal_1d=("abnormal_1d", "mean"),
        avg_abnormal_5d=("abnormal_5d", "mean"),
        avg_abnormal_20d=("abnormal_20d", "mean"),
        # The share of events where ITA beat the market over 20 days.
        beat_market_20d=("abnormal_20d", lambda values: (values > 0).mean() * 100),
    ).round(1).sort_values("avg_abnormal_20d", ascending=False)

    print()
    print("ITA (defense ETF) vs the market, by event category, in %:")
    print(summary.to_string())
