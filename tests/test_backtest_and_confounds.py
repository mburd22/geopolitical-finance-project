# The backtest (the engine's honesty check) and the confound checks.

import numpy as np
import pandas as pd
import pytest

from backtest import MODES, Backtester, score
from backtest import test_matches_find_analogs as check_fast_matches  # renamed so pytest does not collect it twice
from confounds import TURMOIL_MOVE, find_confounds
from runup import analyze, permutation_p, rank_corr


def test_fast_backtester_matches_the_real_engine(events, reactions):
    check_fast_matches(events, reactions)  # raises if any analog list differs


def test_past_only_never_peeks_at_the_future(events, reactions):
    bt = Backtester(events, reactions, "ITA")
    for i in range(bt.n):
        pool = bt.pool(i, "past_only")
        assert not pool[i]
        assert (bt.dates[pool] < bt.dates[i]).all()


def test_leave_one_out_excludes_only_the_event_itself(events, reactions):
    bt = Backtester(events, reactions, "ITA")
    pool = bt.pool(5, "leave_one_out")
    assert not pool[5]
    assert pool.sum() == (~np.isnan(bt.actual)).sum() - (0 if np.isnan(bt.actual[5]) else 1)


def test_score_counts_hits_and_baselines():
    results = pd.DataFrame({
        "date": [1, 2, 3, 4], "event": list("abcd"), "category": ["x"] * 4,
        "actual_20d": [2.0, -1.0, 3.0, 1.0],
        "direction": ["up", "up", "down", "flat"],
        "predicted_median": [1.0, 1.0, -1.0, 0.0],
        "beat_share": [0.7, 0.7, 0.2, 0.5], "analogs": [8] * 4, "strong": [0] * 4,
        "confidence": ["low"] * 4, "category_median": [1.0, -1.0, 1.0, 1.0],
    })
    s = score(results)
    assert s["calls"] == 3  # "flat" is not a call
    assert s["hit_rate"] == pytest.approx(100 / 3, abs=0.1)  # only the first call was right
    assert s["always_up_hit_rate"] == pytest.approx(200 / 3, abs=0.1)  # 2 of the 3 called events went up
    assert s["category_hit_rate"] == pytest.approx(100.0)


@pytest.mark.parametrize("ticker", ["ITA", "EUDEF"])
def test_backtest_runs_for_both_markets(events, reactions, ticker):
    for mode in MODES:
        s = score(Backtester(events, reactions, ticker).run(mode))
        assert s["events"] > 50 and 0 <= s["hit_rate"] <= 100


def test_backtest_at_a_shorter_horizon_scores_that_horizon(events, reactions):
    """horizon="5d" must judge calls against the 5-day move, not the 20-day one."""
    bt = Backtester(events, reactions, "ITA", horizon="5d")
    results = bt.run("leave_one_out")
    assert "actual_5d" in results and "actual_20d" not in results
    truth = reactions[reactions["ticker"] == "ITA"].set_index(["date", "event"])["abnormal_5d"]
    first = results.iloc[0]
    assert first["actual_5d"] == pytest.approx(truth[(pd.Timestamp(first["date"]), first["event"])])
    s = score(results, horizon="5d")
    assert s["calls"] > 50 and 0 <= s["hit_rate"] <= 100


def test_known_earnings_confound(prices, events, earnings):
    """LMT and NOC reported on 22 Jul 2025, inside the Israel-Iran ceasefire window."""
    ceasefire = events[events["event"] == "Israel-Iran ceasefire takes hold"].iloc[0]
    flags = find_confounds(prices, events, earnings, ceasefire, ticker="LMT")
    assert any("Earnings" in f and "LMT" in f for f in flags)


def test_basket_counts_every_members_earnings(prices, events, earnings):
    ceasefire = events[events["event"] == "Israel-Iran ceasefire takes hold"].iloc[0]
    flags = find_confounds(prices, events, earnings, ceasefire, ticker="ITA")
    earnings_flag = next(f for f in flags if f.startswith("Earnings"))
    assert "LMT" in earnings_flag and "NOC" in earnings_flag


def test_market_turmoil_uses_the_right_benchmark(prices, events, earnings):
    """April 2025's tariff shock: SPY moved 9-10% in a day inside the US strikes on Houthis window."""
    houthis = events[events["event"] == "US launches strikes on Houthis"].iloc[0]
    us_flags = find_confounds(prices, events, earnings, houthis, ticker="ITA")
    eu_flags = find_confounds(prices, events, earnings, houthis, ticker="EUDEF")
    assert any("SPY moved" in f for f in us_flags)
    assert not any("SPY" in f for f in eu_flags)
    assert TURMOIL_MOVE == 3.0


def test_rank_correlation_and_permutation():
    x = np.arange(40, dtype=float)
    assert rank_corr(x, -x) == pytest.approx(-1.0)
    assert permutation_p(x, -x, shuffles=500) < 0.01     # a perfect negative link is never luck
    assert permutation_p(x, x, shuffles=500) > 0.99      # a positive link isn't evidence of reversal


def test_runup_analysis_shape(reactions, prices):
    a = analyze(reactions, prices, "ITA", "60d")
    assert a["events"] > 100 and len(a["thirds"]) == 3
    assert -1 <= a["event_corr"] <= 1 and 0 < a["event_p"] <= 1
