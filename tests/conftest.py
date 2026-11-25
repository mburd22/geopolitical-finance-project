# Shared setup for every test. Run the whole suite with:
#   .\.venv\Scripts\python.exe -m pytest
#
# Rules the tests follow:
#   - never touch the internet (no feeds, no Yahoo, no Claude)
#   - never touch the real live database (data/news.db); each test gets a temporary one
#   - real data files (events, prices, reactions) are read but never written

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # the scripts open data files with relative paths like "data/events.csv"

# Must be set before api.py is imported: don't start the hourly news pipeline in tests,
# and make sure no real API key is picked up.
os.environ["AUTO_PIPELINE"] = "0"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)


@pytest.fixture(scope="session")
def events():
    from calculate_reactions import load_events
    return load_events("data/events.csv")


@pytest.fixture(scope="session")
def reactions():
    from find_analogs import load_reactions
    return load_reactions("data/event_reactions.csv")


@pytest.fixture(scope="session")
def prices():
    from calculate_reactions import load_all_prices
    return load_all_prices()


@pytest.fixture(scope="session")
def earnings():
    from confounds import load_earnings
    return load_earnings("data/earnings.csv")


@pytest.fixture
def news_db(tmp_path, monkeypatch):
    """A fresh, empty live database in a temporary folder, with all tables created."""
    import detect
    import news
    import predict
    monkeypatch.setattr(news, "DB_PATH", tmp_path / "news.db")
    db = news.connect()
    detect.ensure_tables(db)
    predict.ensure_tables(db)
    yield db
    db.close()


@pytest.fixture
def no_claude(monkeypatch):
    """Make sure Claude counts as not configured, whatever .env says."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def make_prices(days, values_by_column):
    """A tiny synthetic price table on weekdays starting 2024-01-01 (a Monday)."""
    index = pd.bdate_range("2024-01-01", periods=days)
    return pd.DataFrame(values_by_column, index=index)
