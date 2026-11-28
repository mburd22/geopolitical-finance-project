# Confound checks: reasons an event's measured reaction might NOT be about the event.
#
# For each event we look inside its 20-trading-day measurement window for:
#   1. earnings: a company reported quarterly results (company news, not world news)
#   2. another event: a second event from our own database landed in the same window
#   3. market turmoil: the whole market (SPY) moved 3%+ in a single day, a sign that
#      something big and unrelated (a crash, a pandemic headline) was going on

from pathlib import Path

import pandas as pd

from calculate_reactions import BASKETS, MARKETS, WINDOWS, benchmark_for, first_reaction_day, prices_for

TURMOIL_MOVE = 3.0  # a one-day SPY move (%) big enough to count as market turmoil
WINDOW_DAYS = max(WINDOWS.values())


# Yahoo has no past results dates for BAE Systems or Thales, so these are entered by hand,
# each with the web page it was checked against (the "source" column). download_earnings.py
# rewrites data/earnings.csv but never touches this file.
MANUAL_EARNINGS = Path(__file__).parent / "data" / "earnings_manual.csv"


def load_earnings(path, manual=MANUAL_EARNINGS):
    """Earnings dates from Yahoo (path) plus the hand-entered ones, without duplicates."""
    earnings = pd.read_csv(path)
    if manual and Path(manual).exists():
        extra = pd.read_csv(manual)[["ticker", "date"]]
        earnings = pd.concat([earnings, extra], ignore_index=True)
    earnings["date"] = pd.to_datetime(earnings["date"])
    return earnings.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"]).reset_index(drop=True)


def window_dates(table, event):
    """First and last trading day of an event's measurement window in one market's price table."""
    day0 = first_reaction_day(table.index, event["date"], event["after_close"])
    end = day0 + WINDOW_DAYS - 1
    if day0 < 1 or end >= len(table):
        return None
    return table.index[day0], table.index[end]


def find_confounds(prices, events, earnings, event, ticker="ITA"):
    """Return a list of short warnings, each one a reason to doubt this event's numbers.

    prices: {"US": table, "EU": table}. The checks use the ticker's own market.
    """
    table = prices_for(prices, ticker)
    window = window_dates(table, event)
    if window is None:
        return []
    start, end = window
    flags = []

    # 1. Earnings. A basket (ITA, EUDEF) holds several companies, so any of their reports counts.
    companies = BASKETS.get(ticker, [ticker])
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
        other_window = window_dates(table, other)
        if other_window and start <= other_window[0] <= end:
            others.append(f"{other['event']} ({other['date'].date()})")
    if others:
        flags.append("Overlaps: " + "; ".join(others))

    # 3. Market turmoil: the largest single-day move in this market's benchmark inside the window.
    bench = benchmark_for(ticker)
    daily = table[bench].pct_change() * 100
    biggest = daily.loc[start:end].abs().max()
    if biggest >= TURMOIL_MOVE:
        flags.append(f"Market turmoil: {bench} moved {biggest:.1f}% in one day")

    return flags


if __name__ == "__main__":
    from calculate_reactions import load_all_prices, load_events

    prices = load_all_prices()
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
