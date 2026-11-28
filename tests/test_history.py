# "What history says": base rates for a live event, on small made-up reaction tables.

import pandas as pd
import pytest

from history import base_rates, summary_text


def table(rows):
    """rows: (ticker, category, abnormal_20d)."""
    return pd.DataFrame(rows, columns=["ticker", "category", "abnormal_20d"])


REACTIONS = table([("ITA", "coup", v) for v in (1.0, 2.0, -1.0, 3.0)]
                  + [("ITA", "terrorism", v) for v in (-2.0, -1.0, 1.0, -3.0)]
                  + [("LMT", "coup", 5.0)])


def test_base_rates_for_one_type():
    r = base_rates(REACTIONS, "ITA", "coup", type_test_p=0.5)
    assert r["events"] == 4 and r["avg"] == pytest.approx(1.25)
    assert r["beat_pct"] == pytest.approx(75.0)
    assert r["all_events"] == 8 and r["all_beat_pct"] == pytest.approx(50.0)
    assert r["ci"][0] <= r["avg"] <= r["ci"][1]
    assert not r["type_matters"]


def test_type_test_is_computed_when_not_given():
    r = base_rates(REACTIONS, "ITA", "coup")
    assert 0 < r["type_test_p"] <= 1


def test_unknown_type_and_unknown_stock():
    r = base_rates(REACTIONS, "ITA", "election", type_test_p=0.5)
    assert r["events"] == 0 and r["avg"] is None
    assert "no past election events" in summary_text(r)
    assert base_rates(REACTIONS, "RTX", "coup") is None


def test_summary_says_whether_type_is_a_real_guide():
    weak = summary_text(base_rates(REACTIONS, "ITA", "coup", type_test_p=0.59))
    assert "After the 4 past coup events, ITA beat its market over 20 trading days 75%" in weak
    assert "not a forecast" in weak
    strong = summary_text(base_rates(REACTIONS, "ITA", "coup", type_test_p=0.01))
    assert "has been a real guide" in strong


def test_real_data_has_a_rate_for_every_ticker_and_category(reactions):
    from calculate_reactions import DEFENSE_TICKERS
    for ticker in DEFENSE_TICKERS:
        r = base_rates(reactions, ticker, "military_strike", type_test_p=0.5)
        assert r["events"] >= 20
