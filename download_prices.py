# Download daily prices for every market in calculate_reactions.MARKETS and save
# one file per market (each on its own trading calendar).
#
#   data/prices.csv     US defense stocks, ITA, and SPY (the US market)
#   data/prices_eu.csv  European defense stocks in euros, the EUDEF basket, and EXSA.DE (European market)

from pathlib import Path

import pandas as pd
import yfinance as yf

from calculate_reactions import BASKETS, MARKETS

# Prices start half a year before the first event (Jan 2015), so even the earliest events have
# the 120+ trading days of history that the beta model (ABNORMAL_MODEL = "beta") fits on.
START = "2014-06-01"

# European stocks trade in different currencies. To compare them with a euro-denominated
# benchmark, convert each to euros with the daily exchange rate.
CURRENCY = {"BA.L": "GBPEUR=X", "SAAB-B.ST": "SEKEUR=X"}  # the rest already trade in EUR


def download(symbols):
    # auto_adjust=True corrects old prices for splits and dividends.
    return yf.download(symbols, start=START, auto_adjust=True, progress=False)["Close"]


def us_prices():
    market = MARKETS["US"]
    return download(market["tickers"] + [market["benchmark"]])


def eu_prices():
    market = MARKETS["EU"]
    companies = BASKETS["EUDEF"]
    raw = download(companies + [market["benchmark"]] + list(CURRENCY.values()))

    # Use the benchmark's trading days (the Frankfurt exchange) as the calendar. A stock whose
    # own exchange was closed that day (a UK bank holiday, say) keeps its last price.
    calendar = raw[market["benchmark"]].dropna().index
    raw = raw.reindex(calendar).ffill()

    prices = pd.DataFrame(index=calendar)
    for ticker in companies:
        fx = raw[CURRENCY[ticker]] if ticker in CURRENCY else 1.0
        prices[ticker] = raw[ticker] * fx

    # EUDEF: equal-weighted, rebalanced daily. Each day's return is the average of the five
    # companies' returns, compounded into an index starting at 100.
    daily = prices[companies].pct_change().mean(axis=1).fillna(0)
    prices["EUDEF"] = 100 * (1 + daily).cumprod()
    prices[market["benchmark"]] = raw[market["benchmark"]]
    return prices.dropna(how="all")


if __name__ == "__main__":
    Path("data").mkdir(exist_ok=True)
    for name, build in [("US", us_prices), ("EU", eu_prices)]:
        prices = build()
        prices.round(4).to_csv(MARKETS[name]["file"])
        print(f"{name}: {len(prices)} trading days, {prices.index[0].date()} to {prices.index[-1].date()}, "
              f"saved to {MARKETS[name]['file']}")
