# "What history says": the base rate for a new event, in plain words.
#
# The analog engine hasn't beaten the simple "defense always beats the market" rule in the
# backtest. So for a live event, the honest first answer is the base rate: how this stock did
# after past events of the same type, how it did after any event, and whether event type has
# actually been a reliable guide for this stock (the permutation test in uncertainty.py).

from uncertainty import bootstrap_ci, groups_differ_p

MATTERS_BELOW = 0.05  # permutation-test share under which event type counts as a real guide
DAYS_TEXT = {"1d": "on the first day", "5d": "over 5 trading days", "20d": "over 20 trading days"}


def base_rates(reactions, ticker, category, window="20d", type_test_p=None):
    """Numbers for one stock and event type, or None if the stock has no measured events.

    type_test_p: the permutation-test share for this stock and window, if already worked out
    (the API caches it per stock); otherwise it's computed here.
    """
    rows = reactions[reactions["ticker"] == ticker]
    if rows.empty:
        return None
    col = f"abnormal_{window}"
    same = rows.loc[rows["category"] == category, col].dropna()
    every = rows[col].dropna()
    if type_test_p is None:
        type_test_p = groups_differ_p(rows[col], rows["category"])
    ci = bootstrap_ci(same)
    return {
        "ticker": ticker, "category": category, "window": window,
        "events": int(len(same)),
        "avg": round(float(same.mean()), 2) if len(same) else None,
        "ci": None if ci is None else [round(ci[0], 2), round(ci[1], 2)],
        "beat_pct": round(float((same > 0).mean() * 100), 1) if len(same) else None,
        "all_events": int(len(every)),
        "all_beat_pct": round(float((every > 0).mean() * 100), 1),
        "type_test_p": round(float(type_test_p), 3),
        "type_matters": bool(type_test_p < MATTERS_BELOW),
    }


def pct(value):
    return f"{value:+.1f}%"


def summary_text(rates):
    """The base rate as two or three plain sentences."""
    t, kind, n = rates["ticker"], rates["category"].replace("_", " "), rates["events"]
    days = DAYS_TEXT[rates["window"]]
    if n == 0:
        first = f"There are no past {kind} events to compare with."
    else:
        rng = f", 90% range {pct(rates['ci'][0])} to {pct(rates['ci'][1])}" if rates["ci"] else ""
        first = (f"After the {n} past {kind} events, {t} beat its market {days} {rates['beat_pct']:.0f}% of the "
                 f"time (average {pct(rates['avg'])}{rng}).")
    second = f"After any event it beat the market {rates['all_beat_pct']:.0f}% of the time."
    if rates["type_matters"]:
        third = f"Event type has been a real guide for {t} {days} (permutation test {rates['type_test_p']:.1%})."
    else:
        third = (f"But event type hasn't been a reliable guide for {t} {days} (permutation test "
                 f"{rates['type_test_p']:.0%}), so treat this as background, not a forecast.")
    return " ".join([first, second, third])
