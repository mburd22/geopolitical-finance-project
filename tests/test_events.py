# The event database and its checker.

import pandas as pd

from check_events import ALLOWED, find_problems, load_events


def test_real_events_file_has_no_problems():
    assert find_problems(load_events("data/events.csv")) == []


def make_events(rows):
    columns = ["date", "event", "category", "region", "us_involved", "severity", "surprise", "after_close"]
    return pd.DataFrame(rows, columns=columns)


GOOD = ["2024-01-02", "Good event", "escalation", "europe", "no", "2", "yes", "no"]


def test_good_row_passes():
    assert find_problems(make_events([GOOD])) == []


def test_bad_date_is_caught():
    problems = find_problems(make_events([["2024-13-40", *GOOD[1:]]]))
    assert any("bad date" in p for p in problems)


def test_unknown_category_is_caught():
    problems = find_problems(make_events([[GOOD[0], GOOD[1], "militry_strike", *GOOD[3:]]]))
    assert any("category" in p and "militry_strike" in p for p in problems)


def test_duplicates_are_caught():
    problems = find_problems(make_events([GOOD, GOOD]))
    assert sum("duplicate" in p for p in problems) == 2


def test_stray_spaces_are_stripped(tmp_path):
    """The bug from early on: ' military_strike' with a leading space must count as military_strike."""
    path = tmp_path / "events.csv"
    path.write_text("date,event,category,region,us_involved,severity,surprise,after_close\n"
                    "2024-01-02,Spacey, military_strike ,europe,no,2,yes,no\n", encoding="utf-8")
    events = load_events(path)
    assert events.loc[0, "category"] == "military_strike"
    assert find_problems(events) == []


def test_every_region_and_category_is_allowed():
    events = load_events("data/events.csv")
    for column in ("category", "region"):
        assert set(events[column]) <= ALLOWED[column]
