# Your first Python script.
# Lines starting with # are comments: notes for humans that Python ignores.

# A variable is a name that holds a value.
project_name = "Defense Stock Event Tracker"
print("Welcome to the", project_name)

# A list holds several values in order, inside square brackets.
tickers = ["LMT", "RTX", "NOC", "GD", "ITA"]
print("Stocks we'll track:", tickers)

# A dictionary pairs keys with values, like a lookup table.
company_names = {
    "LMT": "Lockheed Martin",
    "RTX": "RTX (Raytheon)",
    "NOC": "Northrop Grumman",
    "GD": "General Dynamics",
    "ITA": "iShares U.S. Aerospace & Defense ETF",
}

# A for loop repeats the indented lines once for each item in the list.
for ticker in tickers:
    print(ticker, "is", company_names[ticker])

# pandas is a library (code someone else wrote) for working with tables of data.
import pandas as pd

# A DataFrame is pandas' name for a table: rows and columns, like a spreadsheet.
table = pd.DataFrame({
    "ticker": tickers,
    "name": [company_names[t] for t in tickers],
})
print()
print(table)
