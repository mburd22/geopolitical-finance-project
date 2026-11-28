# The beta-adjusted (market-model) abnormal returns, on synthetic prices where alpha and beta
# are known exactly.

import numpy as np
import pandas as pd
import pytest

from calculate_reactions import (
    ESTIMATION_DAYS, ESTIMATION_GAP, MARKETS, expected_prices, fit_market_model, measure_event,
)
from tests.conftest import make_prices

DAYS = 220
EVENT_INDEX = 160  # late enough for a full estimation window before it
RNG = np.random.default_rng(42)


def prices_from_returns(daily_returns, start=100.0):
    """Turn a list of daily returns into prices (the first day has no return)."""
    return list(start * np.cumprod(np.concatenate([[1.0], 1 + np.asarray(daily_returns)])))


def beta_markets(beta, alpha=0.0, market_after=None):
    """SPY wanders randomly; LMT moves exactly alpha + beta x SPY every day. Everything else is flat.

    market_after: if given, SPY's daily return from the event onwards (so the result is easy to check).
    """
    market = RNG.normal(0, 0.01, DAYS - 1)
    if market_after is not None:
        market[EVENT_INDEX - 1:] = market_after
    stock = alpha + beta * market
    tables = {}
    for name, m in MARKETS.items():
        columns = {t: [100.0] * DAYS for t in m["tickers"] + [m["benchmark"]]}
        tables[name] = make_prices(DAYS, columns)
    tables["US"]["SPY"] = prices_from_returns(market)
    tables["US"]["LMT"] = prices_from_returns(stock)
    return tables


def event_at(prices, position):
    return {"date": prices["US"].index[position], "event": "Test", "category": "escalation",
            "region": "europe", "after_close": "no"}


def lmt(results):
    return next(r for r in results if r["ticker"] == "LMT")


def test_fit_recovers_known_alpha_and_beta():
    prices = beta_markets(beta=1.5, alpha=0.0004)
    alpha, beta = fit_market_model(prices["US"], "LMT", "SPY", EVENT_INDEX)
    assert beta == pytest.approx(1.5)
    assert alpha == pytest.approx(0.0004)


def test_fit_needs_enough_history():
    prices = beta_markets(beta=1.0)
    too_early = ESTIMATION_DAYS + ESTIMATION_GAP  # one day short of a full window
    assert fit_market_model(prices["US"], "LMT", "SPY", too_early) is None
    assert fit_market_model(prices["US"], "LMT", "SPY", too_early + 1) is not None
    # With no fit possible, the beta model falls back to the plain benchmark.
    assert expected_prices(prices["US"], "LMT", "SPY", too_early, "beta").equals(prices["US"]["SPY"])


def test_fit_ignores_the_days_just_before_the_event():
    """A run-up in the last ESTIMATION_GAP days before the news must not leak into alpha and beta."""
    prices = beta_markets(beta=1.0)
    table = prices["US"].copy()
    before = fit_market_model(table, "LMT", "SPY", EVENT_INDEX)
    table.iloc[EVENT_INDEX - ESTIMATION_GAP:, table.columns.get_loc("LMT")] *= 1.2  # leak inside the gap
    assert fit_market_model(table, "LMT", "SPY", EVENT_INDEX) == pytest.approx(before)


def test_high_beta_stock_in_a_rising_market():
    """A beta-1.5 stock in a market that rises 0.5% a day: the market-adjusted model sees an
    'abnormal' gain that is really just beta. The market model sees nothing abnormal."""
    prices = beta_markets(beta=1.5, market_after=0.005)
    event = event_at(prices, EVENT_INDEX)
    market_adjusted = lmt(measure_event(prices, event, model="market"))
    market_model = lmt(measure_event(prices, event, model="beta"))
    assert market_adjusted["abnormal_20d"] > 5      # about 1.5x the market's ~10.5%, minus 10.5%
    assert market_model["abnormal_20d"] == pytest.approx(0.0, abs=0.01)
    # market_* columns are the benchmark's own return in both models.
    assert market_model["market_20d"] == market_adjusted["market_20d"]


def test_a_real_jump_is_still_abnormal_under_the_market_model():
    """On top of its beta, the stock jumps 10% on the reaction day while the market is flat."""
    prices = beta_markets(beta=1.5, market_after=0.0)
    table = prices["US"]
    table.iloc[EVENT_INDEX:, table.columns.get_loc("LMT")] *= 1.10
    result = lmt(measure_event(prices, event_at(prices, EVENT_INDEX), model="beta"))
    assert result["abnormal_1d"] == pytest.approx(10.0, abs=0.01)
    assert result["abnormal_20d"] == pytest.approx(10.0, abs=0.01)


def test_alpha_is_expected_not_abnormal():
    """A stock that drifts up 0.1% a day more than its beta explains: under the market model
    that drift is 'expected' (alpha), so 20 more days of it count as roughly nothing."""
    prices = beta_markets(beta=1.0, alpha=0.001, market_after=0.0)
    result = lmt(measure_event(prices, event_at(prices, EVENT_INDEX), model="beta"))
    assert result["abnormal_20d"] == pytest.approx(0.0, abs=0.01)
    market_adjusted = lmt(measure_event(prices, event_at(prices, EVENT_INDEX), model="market"))
    assert market_adjusted["abnormal_20d"] == pytest.approx(100 * (1.001 ** 20 - 1), abs=0.01)


def test_market_model_is_the_benchmark_itself():
    table = beta_markets(beta=2.0)["US"]
    assert expected_prices(table, "LMT", "SPY", EVENT_INDEX, "market").equals(table["SPY"])


def test_unknown_model_is_rejected():
    table = beta_markets(beta=1.0)["US"]
    with pytest.raises(ValueError):
        expected_prices(table, "LMT", "SPY", EVENT_INDEX, "capm")


def test_estimation_settings_fit_the_price_history(events, prices):
    """Prices must start early enough that even the first event gets a fitted beta."""
    from calculate_reactions import first_reaction_day
    for name, table in prices.items():
        day0 = first_reaction_day(table.index, events["date"].min(), "no")
        ticker = MARKETS[name]["tickers"][0]
        assert fit_market_model(table, ticker, MARKETS[name]["benchmark"], day0) is not None, name


def test_real_beta_estimates_are_sensible(prices):
    """Defense stocks are lower-beta than the market on average; nothing should be wild."""
    table = prices["US"]
    day0 = len(table) - 30
    for ticker in MARKETS["US"]["tickers"]:
        _, beta = fit_market_model(table, ticker, "SPY", day0)
        assert -0.5 < beta < 2.5, (ticker, beta)
    assert isinstance(table.index, pd.DatetimeIndex)
