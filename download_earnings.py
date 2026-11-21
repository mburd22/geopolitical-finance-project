# Download the dates each defense company reported quarterly earnings, so we can
# flag events whose measurement window overlaps an earnings day (company news that
# can swamp any reaction to world news).

import pandas as pd
import yfinance as yf

from calculate_reactions import BASKETS

COMPANIES = [t for members in BASKETS.values() for t in members]  # baskets have no earnings of their own

rows = []
for ticker in COMPANIES:
    # limit = how many past (and upcoming) reports to fetch; ~4 a year since 2014.
    dates = yf.Ticker(ticker).get_earnings_dates(limit=60)
    for timestamp in dates.index:
        rows.append({"ticker": ticker, "date": timestamp.date()})
    print(f"{ticker}: {len(dates)} earnings dates")

earnings = pd.DataFrame(rows).drop_duplicates().sort_values(["ticker", "date"])
earnings.to_csv("data/earnings.csv", index=False)
print("Saved to data/earnings.csv")
