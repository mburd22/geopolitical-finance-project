# Checks data/events.csv for mistakes before we use it in any analysis.
# Run this every time you edit the events file.

import pandas as pd

# The only values each column is allowed to contain.
# Curly brackets { } with plain values make a "set": a collection with no duplicates,
# which is fast to check "is this value in here?"
ALLOWED = {
    "category": {
        "war_outbreak", "military_strike", "escalation", "de_escalation",
        "terrorism", "weapons_test", "coup", "election", "defense_spending",
    },
    "region": {"europe", "middle_east", "east_asia", "south_asia", "americas", "africa", "global"},
    "us_involved": {"yes", "no"},
    "severity": {"1", "2", "3"},
    "surprise": {"yes", "no"},
    "after_close": {"yes", "no"},
}


# "def" defines a function: a named, reusable block of code.
# This one takes the path of a file and gives back ("returns") a cleaned table.
def load_events(path):
    # dtype=str reads everything as text, so we control conversions ourselves.
    events = pd.read_csv(path, dtype=str)
    # Strip stray spaces from the start and end of every value (the safety net
    # for the " military_strike" bug you found).
    events = events.apply(lambda column: column.str.strip())
    return events


def find_problems(events):
    problems = []  # start with an empty list and add to it

    # 1. Dates must be real dates in YYYY-MM-DD format.
    dates = pd.to_datetime(events["date"], format="%Y-%m-%d", errors="coerce")
    for row_number in events.index[dates.isna()]:
        problems.append(f"Row {row_number + 2}: bad date '{events.loc[row_number, 'date']}'")

    # 2. Every tag column must only contain allowed values.
    for column, allowed_values in ALLOWED.items():
        for row_number, value in events[column].items():
            if value not in allowed_values:
                problems.append(f"Row {row_number + 2}: {column} '{value}' is not one of {sorted(allowed_values)}")

    # 3. No event should be listed twice.
    duplicates = events[events.duplicated(subset=["date", "event"], keep=False)]
    for row_number in duplicates.index:
        problems.append(f"Row {row_number + 2}: duplicate of another row")

    return problems


# This is where the script actually starts running (only when run directly,
# so other files can import ALLOWED without running the checks).
if __name__ == "__main__":
    events = load_events("data/events.csv")
    problems = find_problems(events)

    if problems:
        print(f"Found {len(problems)} problem(s):")
        for problem in problems:
            print(" -", problem)
    else:
        print(f"All good: {len(events)} events, no problems found.")
        print()
        print("Events per category:")
        print(events["category"].value_counts().to_string())
        print()
        print("Events per region:")
        print(events["region"].value_counts().to_string())
