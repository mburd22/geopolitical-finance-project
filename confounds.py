# Confound checks: reasons an event's measured reaction might NOT be about the event.
#
# For each event we look inside its 20-trading-day measurement window for:
#   1. earnings: a company reported quarterly results (company news, not world news)
#   2. another event: a second event from our own database landed in the same window
#   3. market turmoil: the whole market (SPY) moved 3%+ in a single day, a sign that
#      something big and unrelated (a crash, a pandemic headline) was going on

import pandas as pd

from calculate_reactions import DEFENSE_TICKERS, MARKET_TICKER, WINDOWS, first_reaction_day

TURMOIL_MOVE = 3.0  # a one-day SPY move (%) big enough to count as market turmoil
WINDOW_DAYS = max(WINDOWS.values())


def load_earnings(path):
    earnings = pd.read_csv(path)
    earnings["date"] = pd.to_datetime(earnings["date"])
    return earnings


def window_dates(prices, event):
    """First and last trading day of an event's measurement window, or None if out of range."""
    day0 = first_reaction_day(prices.index, event["date"], event["after_close"])
    end = day0 + WINDOW_DAYS - 1
    if day0 < 1 or end >= len(prices):
        return None
    return prices.index[day0], prices.index[end]


def find_confounds(prices, events, earnings, event, ticker="ITA"):
    """Return a list of short warnings, each one a reason to doubt this event's numbers."""
    window = window_dates(prices, event)
    if window is None:
        return []
    start, end = window
    flags = []

    # 1. Earnings. The ETF holds all four companies, so any of their reports counts.
    companies = [t for t in DEFENSE_TICKERS if t != "ITA"] if ticker == "ITA" else [ticker]
    reports = earnings[earnings["ticker"].isin(companies) & earnings["date"].between(start, end)]
    if not reports.empty:
        first = reports.sort_values("date").iloc[0]
        names = ", ".join(sorted(reports["ticker"].unique()))
        flags.append(f"Earnings in window: {names} (first on {first['date'].date()})")

    # 2. Other events from our database inside the same window.
    others = []
    for _, other in events.iterrows():
        if other["date"] == event["date"] and other["event"] == event["event"]:
            continue  # skip the event itself
        other_window = window_dates(prices, other)
        if other_window and start <= other_window[0] <= end:
            others.append(f"{other['event']} ({other['date'].date()})")
    if others:
        flags.append("Overlaps: " + "; ".join(others))

    # 3. Market turmoil: the largest single-day SPY move inside the window.
    daily = prices[MARKET_TICKER].pct_change() * 100
    biggest = daily.loc[start:end].abs().max()
    if biggest >= TURMOIL_MOVE:
        flags.append(f"Market turmoil: SPY moved {biggest:.1f}% in one day")

    return flags


if __name__ == "__main__":
    from calculate_reactions import load_events, load_prices

    prices = load_prices("data/prices.csv")
    events = load_events("data/events.csv")
    earnings = load_earnings("data/earnings.csv")

    flagged = 0
    for _, event in events.iterrows():
        flags = find_confounds(prices, events, earnings, event)
        if flags:
            flagged += 1
            print(f"{event['date'].date()}  {event['event']}")
            for flag in flags:
                print("    -", flag)
    print(f"\n{flagged} of {len(events)} events have at least one confound (for ITA).")
