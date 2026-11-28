# Step 5: turn the event reactions into charts, saved as PNG images in the "charts" folder.

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # draw straight to image files instead of opening windows
import matplotlib.pyplot as plt  # pyplot is matplotlib's main charting toolkit
import pandas as pd

# Reuse the functions we already wrote, instead of copying them here.
# This works because of the `if __name__ == "__main__":` line in calculate_reactions.py.
from calculate_reactions import (
    MARKETS, benchmark_for, expected_prices, first_reaction_day, load_all_prices, load_events, prices_for,
)

DAYS_BEFORE = 5   # how many trading days to show before the event
DAYS_AFTER = 20   # and after

# Events to draw individual charts for, picked by date. Add your own!
SHOWCASE_DATES = ["2022-02-24", "2022-02-27", "2023-10-07", "2025-06-24"]

CHARTS = Path("charts")


def abnormal_path(prices, event, ticker):
    """Day-by-day cumulative abnormal return (in %) around one event, for one ticker.

    Returns a pandas Series: the index is the day relative to the event
    (-5 ... 0 ... +19) and each value is how far the stock has pulled ahead of
    (or fallen behind) its market since the close just before the news.
    prices: {"US": table, "EU": table}.
    """
    table = prices_for(prices, ticker)
    bench = benchmark_for(ticker)
    day0 = first_reaction_day(table.index, event["date"], event["after_close"])
    baseline = day0 - 1
    first, last = day0 - DAYS_BEFORE, day0 + DAYS_AFTER - 1
    if first < 0 or last >= len(table):
        return None

    # "market" here is what the abnormal-return model expected (with the default model,
    # simply the benchmark's own move; see ABNORMAL_MODEL in calculate_reactions.py).
    expected = expected_prices(table, ticker, bench, day0)
    stock = table[ticker].iloc[first:last + 1] / table[ticker].iloc[baseline] - 1
    market = expected.iloc[first:last + 1] / expected.iloc[baseline] - 1
    path = (stock - market) * 100
    path.index = range(-DAYS_BEFORE, DAYS_AFTER)  # relabel rows as relative days
    return path


def style_axes(ax, title):
    """Shared look for every chart: reference lines, labels, light grid."""
    ax.axhline(0, color="gray", linewidth=0.8)                  # the "matched the market" line
    ax.axvline(0, color="black", linewidth=1, linestyle="--")   # day 0: first reaction day
    ax.set_xlabel("Trading days relative to the event (0 = first day markets could react)")
    ax.set_ylabel("Return vs the market (%)")
    ax.set_title(title, fontsize=12, loc="left")
    ax.grid(alpha=0.3)


def chart_event(prices, event):
    """One line per defense ticker, showing how it moved vs the market around one event."""
    fig, ax = plt.subplots(figsize=(10, 5.5))  # a figure (the image) with one set of axes
    for ticker in MARKETS["US"]["tickers"]:
        path = abnormal_path(prices, event, ticker)
        if path is not None:
            # Make the ETF stand out, since it represents the whole sector.
            width = 3 if ticker == "ITA" else 1.5
            ax.plot(path.index, path.values, label=ticker, linewidth=width)
    style_axes(ax, f"{event['event']} ({event['date'].date()})")
    ax.legend()
    fig.tight_layout()
    file = CHARTS / f"event_{event['date'].date()}.png"
    fig.savefig(file, dpi=120)
    plt.close(fig)  # free the memory before drawing the next chart
    return file


def category_paths(prices, events):
    """Average ITA path for each event category. Returns {category: (path, number_of_events)}."""
    results = {}
    for category, group in events.groupby("category"):
        paths = [abnormal_path(prices, event, "ITA") for _, event in group.iterrows()]
        paths = [p for p in paths if p is not None]  # a "list comprehension" that filters out gaps
        if paths:
            # Put the paths side by side as columns, then average across each row (each day).
            results[category] = (pd.concat(paths, axis=1).mean(axis=1), len(paths))
    return results


def chart_categories(paths):
    """The classic event-study chart: average reaction over time, one line per category."""
    fig, ax = plt.subplots(figsize=(11, 6))
    # Sort so the legend lists categories from best to worst final result.
    ordered = sorted(paths.items(), key=lambda item: item[1][0].iloc[-1], reverse=True)
    for category, (path, count) in ordered:
        ax.plot(path.index, path.values, label=f"{category} ({count})", linewidth=2)
    style_axes(ax, "ITA defense ETF vs the market: average reaction by event type")
    ax.legend(title="Category (events)", fontsize=9)
    fig.tight_layout()
    file = CHARTS / "category_paths.png"
    fig.savefig(file, dpi=120)
    plt.close(fig)
    return file


def chart_category_bars(paths):
    """Bar chart of the average 20-day result per category: green above the market, red below."""
    final = {category: path.iloc[-1] for category, (path, _) in paths.items()}
    final = dict(sorted(final.items(), key=lambda item: item[1]))
    colors = ["#2e7d32" if value > 0 else "#c62828" for value in final.values()]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    bars = ax.barh(list(final.keys()), list(final.values()), color=colors)
    ax.bar_label(bars, fmt="%+.1f%%", padding=3)  # write each value at the end of its bar
    ax.axvline(0, color="gray", linewidth=0.8)
    # Leave room on both sides so the value labels don't collide with the category names.
    values = list(final.values())
    ax.set_xlim(min(min(values), 0) - 1, max(max(values), 0) + 1)
    ax.set_xlabel("Average return vs the market, 20 trading days after (%)")
    ax.set_title("Which events help defense stocks? (ITA, 20-day abnormal return)", loc="left")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    file = CHARTS / "category_bars.png"
    fig.savefig(file, dpi=120)
    plt.close(fig)
    return file


if __name__ == "__main__":
    CHARTS.mkdir(exist_ok=True)
    prices = load_all_prices()
    events = load_events("data/events.csv")

    saved = []
    for date in SHOWCASE_DATES:
        match = events[events["date"] == pd.Timestamp(date)]
        if match.empty:
            print(f"No event found on {date}, skipping")
            continue
        saved.append(chart_event(prices, match.iloc[0]))

    paths = category_paths(prices, events)
    saved.append(chart_categories(paths))
    saved.append(chart_category_bars(paths))

    print("Saved charts:")
    for file in saved:
        print(" -", file)
