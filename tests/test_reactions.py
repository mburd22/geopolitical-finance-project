# The event-study maths: reaction day, abnormal returns and run-ups, on synthetic prices
# where the right answer is known exactly.

import pandas as pd
import pytest

from calculate_reactions import MARKETS, first_reaction_day, measure_event, runup
from tests.conftest import make_prices

DAYS = 60
EVENT_INDEX = 30  # the event happens on the 31st business day


def flat_markets(jump_ticker=None, jump_at=None, jump_to=110.0):
    """Every price is 100 forever, except one ticker that jumps to `jump_to` at position `jump_at`."""
    tables = {}
    for name, market in MARKETS.items():
        columns = {t: [100.0] * DAYS for t in market["tickers"] + [market["benchmark"]]}
        if jump_ticker in columns:
            columns[jump_ticker] = [100.0] * jump_at + [jump_to] * (DAYS - jump_at)
        tables[name] = make_prices(DAYS, columns)
    return tables


def event_on(date, after_close="no"):
    return {"date": pd.Timestamp(date), "event": "Test", "category": "escalation",
            "region": "europe", "after_close": after_close}


def rows_for(results, ticker):
    return next(r for r in results if r["ticker"] == ticker)


def test_jump_on_reaction_day_is_fully_abnormal():
    prices = flat_markets("LMT", EVENT_INDEX)
    day = prices["US"].index[EVENT_INDEX]
    lmt = rows_for(measure_event(prices, event_on(day)), "LMT")
    assert lmt["reaction_day"] == day.date()
    assert lmt["abnormal_1d"] == pytest.approx(10.0)
    assert lmt["abnormal_20d"] == pytest.approx(10.0)
    assert lmt["runup_20d"] == pytest.approx(0.0)  # nothing happened before the news


def test_after_close_news_reacts_next_day():
    """If the news broke after the close, the jump that day is BEFORE the reaction: it's run-up, not reaction."""
    prices = flat_markets("LMT", EVENT_INDEX)
    day = prices["US"].index[EVENT_INDEX]
    lmt = rows_for(measure_event(prices, event_on(day, after_close="yes")), "LMT")
    assert lmt["reaction_day"] == prices["US"].index[EVENT_INDEX + 1].date()
    assert lmt["abnormal_20d"] == pytest.approx(0.0)
    assert lmt["runup_20d"] == pytest.approx(10.0)


def test_market_move_is_subtracted():
    """If the stock and its benchmark both rise 10%, nothing is abnormal."""
    prices = flat_markets("LMT", EVENT_INDEX)
    prices["US"]["SPY"] = prices["US"]["LMT"]
    day = prices["US"].index[EVENT_INDEX]
    lmt = rows_for(measure_event(prices, event_on(day)), "LMT")
    assert lmt["return_20d"] == pytest.approx(10.0)
    assert lmt["market_20d"] == pytest.approx(10.0)
    assert lmt["abnormal_20d"] == pytest.approx(0.0)


def test_weekend_event_rolls_to_monday():
    prices = flat_markets()
    index = prices["US"].index
    saturday = pd.Timestamp("2024-02-03")
    assert saturday.weekday() == 5
    day0 = first_reaction_day(index, saturday, "no")
    assert index[day0] == pd.Timestamp("2024-02-05")  # the Monday


def test_each_market_uses_its_own_benchmark():
    prices = flat_markets("RHM.DE", EVENT_INDEX)
    day = prices["EU"].index[EVENT_INDEX]
    results = measure_event(prices, event_on(day))
    assert rows_for(results, "RHM.DE")["abnormal_20d"] == pytest.approx(10.0)
    assert rows_for(results, "LMT")["abnormal_20d"] == pytest.approx(0.0)
    assert {r["ticker"] for r in results} == {t for m in MARKETS.values() for t in m["tickers"]}


def test_too_little_history_after_is_skipped():
    prices = flat_markets()
    late = prices["US"].index[DAYS - 5]  # fewer than 20 trading days left
    assert measure_event(prices, event_on(late)) == []


def test_runup_needs_enough_history():
    table = flat_markets()["US"]
    assert runup(table, "LMT", "SPY", baseline=10, days=20) is None
    assert runup(table, "LMT", "SPY", baseline=30, days=20) == pytest.approx(0.0)


def test_real_reactions_file_is_consistent(reactions, events):
    """Every measured event is in the events file, and every ticker has a row per event."""
    measured = reactions.groupby(["date", "event"])["ticker"].nunique()
    assert (measured == len({t for m in MARKETS.values() for t in m["tickers"]})).all()
    known = set(zip(events["date"], events["event"]))
    assert set(measured.index) <= known


def test_every_event_has_one_cluster(reactions):
    """All of an event's rows share one cluster, and clusters run in time order."""
    per_event = reactions.groupby(["date", "event"])["cluster"].nunique()
    assert (per_event == 1).all()
    first = reactions.drop_duplicates(["date", "event"]).sort_values("date")
    assert first["cluster"].is_monotonic_increasing
    assert 30 < first["cluster"].nunique() < len(first)  # many events overlap, but not all
