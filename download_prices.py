# Step 2: download daily stock prices and save them to a file.

# "import" loads a library so we can use it.
# yfinance downloads price history from Yahoo Finance. "as yf" gives it a short nickname.
import yfinance as yf

# pathlib helps us work with folders and file paths.
from pathlib import Path

# The defense stocks we're studying, plus SPY.
# SPY is a fund that tracks the S&P 500 (the 500 biggest US companies).
# It stands in for "the whole market", so later we can ask:
# did defense stocks move MORE than the market did?
tickers = ["LMT", "RTX", "NOC", "GD", "ITA", "SPY"]

# How far back to go. Dates are written year-month-day.
start_date = "2015-01-01"

print("Downloading prices for:", tickers)

# This one line fetches every ticker's history from start_date to today.
# auto_adjust=True corrects old prices for stock splits and dividends,
# so a jump in the chart reflects a real change in value, not paperwork.
data = yf.download(tickers, start=start_date, auto_adjust=True, progress=False)

# The download includes several prices per day (Open, High, Low, Close, Volume).
# We only need the Close: the price when the market shut that day.
prices = data["Close"]

# .head() shows the first 5 rows, .tail() the last 5. Great for a quick look.
print()
print("First few days:")
print(prices.head())
print()
print("Most recent days:")
print(prices.tail())
print()
print("Total trading days downloaded:", len(prices))

# Save to a CSV file inside a "data" folder (created if it doesn't exist yet).
# exist_ok=True means "don't complain if the folder is already there".
Path("data").mkdir(exist_ok=True)
prices.round(2).to_csv("data/prices.csv")
print("Saved to data/prices.csv")
