# Step 4: measure how each defense stock reacted to each event, compared with the market.
#
# Key idea: ABNORMAL RETURN = stock's return - market's return over the same days.
# If LMT rose 5% while SPY (the whole market) rose 2%, the abnormal return is +3%.
# That +3% is the part of the move we can plausibly link to the event.

import pandas as pd

# Each market has its own trading calendar, price file and benchmark ("the market").
# European prices are converted to euros so they're comparable with their benchmark,
# a STOXX Europe 600 fund. ITA and EUDEF are sector baskets: ITA is a US defense ETF,
# EUDEF an equal-weighted basket of the five European companies (built in download_prices.py).
MARKETS = {
    "US": {"tickers": ["LMT", "RTX", "NOC", "GD", "ITA"], "benchmark": "SPY",
           "benchmark_name": "S&P 500", "file": "data/prices.csv"},
    "EU": {"tickers": ["RHM.DE", "BA.L", "HO.PA", "SAAB-B.ST", "LDO.MI", "EUDEF"], "benchmark": "EXSA.DE",
           "benchmark_name": "STOXX Europe 600", "file": "data/prices_eu.csv"},
}
TICKER_NAMES = {
    "ITA": "US defense ETF", "LMT": "Lockheed Martin", "RTX": "RTX", "NOC": "Northrop Grumman",
    "GD": "General Dynamics", "EUDEF": "European defense basket", "RHM.DE": "Rheinmetall",
    "BA.L": "BAE Systems", "HO.PA": "Thales", "SAAB-B.ST": "Saab", "LDO.MI": "Leonardo",
}
BASKETS = {"ITA": ["LMT", "RTX", "NOC", "GD"], "EUDEF": ["RHM.DE", "BA.L", "HO.PA", "SAAB-B.ST", "LDO.MI"]}

DEFENSE_TICKERS = [t for m in MARKETS.values() for t in m["tickers"]]
MARKET_OF = {t: name for name, m in MARKETS.items() for t in m["tickers"]}
MARKET_TICKER = MARKETS["US"]["benchmark"]  # kept for older code paths: the US benchmark


def benchmark_for(ticker):
    return MARKETS[MARKET_OF[ticker]]["benchmark"]

# How many trading days after the event to measure. Day 0 is the first day markets
# could react, so a 5-day window covers day 0 through day 4.
WINDOWS = {"1d": 1, "5d": 5, "20d": 20}


def load_prices(path):
    # index_col=0 makes the date column the row labels; parse_dates turns text into real dates.
    return pd.read_csv(path, index_col=0, parse_dates=True)


def load_all_prices():
    """{"US": prices table, "EU": prices table}: each market on its own trading calendar."""
    return {name: load_prices(m["file"]) for name, m in MARKETS.items()}


def prices_for(prices, ticker):
    """The price table holding this ticker (and its benchmark)."""
    return prices[MARKET_OF[ticker]]


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
    """Return a list of result rows (one per defense ticker) for a single event.

    prices: {"US": table, "EU": table} from load_all_prices(). Each market's reaction day
    comes from its own calendar. (after_close is about the US close; European markets close
    earlier, so for news that broke during US hours Europe may really react a day later.)
    """
    rows = []
    for name, market in MARKETS.items():
        table = prices[name]
        trading_days = table.index
        day0 = first_reaction_day(trading_days, event["date"], event["after_close"])

        # The baseline is the close on the trading day BEFORE the reaction: the last price before the news.
        baseline = day0 - 1
        longest = max(WINDOWS.values())
        if baseline < 0 or day0 + longest - 1 >= len(trading_days):
            continue  # not enough price history on one side of this event in this market

        bench = table[market["benchmark"]]
        for ticker in market["tickers"]:
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
                stock_return = table[ticker].iloc[end] / table[ticker].iloc[baseline] - 1
                market_return = bench.iloc[end] / bench.iloc[baseline] - 1
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
    prices = load_all_prices()
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

    # A first summary: the average abnormal return for each sector basket by event category.
    # groupby splits the table into groups, then .agg calculates something for each group.
    for basket in BASKETS:
        rows = reactions[reactions["ticker"] == basket]
        summary = rows.groupby("category").agg(
            events=("event", "count"),
            avg_abnormal_1d=("abnormal_1d", "mean"),
            avg_abnormal_5d=("abnormal_5d", "mean"),
            avg_abnormal_20d=("abnormal_20d", "mean"),
            # The share of events where the basket beat its market over 20 days.
            beat_market_20d=("abnormal_20d", lambda values: (values > 0).mean() * 100),
        ).round(1).sort_values("avg_abnormal_20d", ascending=False)

        print()
        print(f"{basket} ({TICKER_NAMES[basket]}) vs its market, by event category, in %:")
        print(summary.to_string())
