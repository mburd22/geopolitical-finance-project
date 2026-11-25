# The live pipeline, end to end, on a temporary database and fake headlines (no internet).

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import detect
import pipeline
import predict
from calculate_reactions import DEFENSE_TICKERS


def add_articles(db, titles, hours_ago=5, sources=None):
    published = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    for i, title in enumerate(titles):
        source = sources[i] if sources else f"Outlet {i}"
        db.execute("INSERT INTO articles (url, title, source, feed, published_at, fetched_at, relevant) "
                   "VALUES (?, ?, ?, 'test', ?, ?, 1)", (f"https://x.test/{hours_ago}/{i}", title, source, published, published))
    db.commit()


STORY = [
    "Israeli airstrikes hit southern Lebanon overnight",
    "Airstrikes pound southern Lebanon as Israel widens campaign",
    "Lebanon says Israeli airstrikes killed dozens in the south",
    "Israel launches new wave of airstrikes on Lebanon",
]


def test_market_timing():
    # 21:30 UTC on a Wednesday is 4:30pm in New York (standard time): after the close.
    assert detect.market_timing("2026-11-18T21:30:00+00:00") == ("2026-11-18", "yes")
    assert detect.market_timing("2026-11-18T15:00:00+00:00") == ("2026-11-18", "no")
    # Saturday: markets are closed anyway, so the reaction simply rolls to Monday.
    assert detect.market_timing("2026-11-21T22:00:00+00:00") == ("2026-11-21", "no")


def test_cluster_groups_one_story_and_separates_another():
    articles = [{"id": i, "title": t, "source": f"s{i}", "published_at": "x"} for i, t in enumerate(STORY)]
    articles.append({"id": 99, "title": "Pakistan test-fires new cruise missile", "source": "s9", "published_at": "x"})
    groups = detect.cluster(articles)
    sizes = sorted(len(g["articles"]) for g in groups)
    assert sizes == [1, 4]


def test_detect_creates_one_event_and_merges_follow_ups(news_db, no_claude):
    add_articles(news_db, STORY)
    created = detect.detect(news_db, log=lambda m: None)
    assert len(created) == 1
    event = news_db.execute("SELECT * FROM detected_events").fetchone()
    assert event["category"] == "military_strike" and event["region"] == "middle_east"
    assert event["classifier"] == "rules" and event["n_sources"] == 4

    # Next day's coverage of the same story joins the event instead of creating a duplicate.
    add_articles(news_db, ["Israeli airstrikes on southern Lebanon continue for second day",
                           "More airstrikes hit southern Lebanon",
                           "Southern Lebanon airstrikes: Israel says targets were Hezbollah"], hours_ago=2)
    assert detect.detect(news_db, log=lambda m: None) == []
    assert news_db.execute("SELECT count(*) FROM detected_events").fetchone()[0] == 1
    assert news_db.execute("SELECT n_articles FROM detected_events").fetchone()[0] == 7


def test_small_stories_are_ignored(news_db, no_claude):
    add_articles(news_db, STORY[:2])  # only 2 articles: below the 3-article / 3-outlet bar
    assert detect.detect(news_db, log=lambda m: None) == []


def test_predict_and_score_a_known_past_event(news_db, events, reactions, prices):
    """A 'detected' copy of Israel strikes Iran (June 2025) must score exactly like the event study."""
    news_db.execute(
        "INSERT INTO detected_events (name, event_time, event_date, after_close, category, region, us_involved, "
        "severity, surprise, n_articles, n_sources, classifier, status) VALUES ('Test copy', "
        "'2025-06-13T02:00:00+00:00', '2025-06-13', 'no', 'war_outbreak', 'middle_east', 'no', '3', 'yes', "
        "5, 5, 'rules', 'active')")
    assert predict.predict_new(news_db, events, reactions, log=lambda m: None) == 1
    assert predict.predict_new(news_db, events, reactions, log=lambda m: None) == 0  # nothing left to do
    assert predict.score_due(news_db, prices, log=lambda m: None) == len(DEFENSE_TICKERS)
    truth = reactions[reactions["event"] == "Israel strikes Iran"].set_index("ticker")["abnormal_20d"]
    for row in news_db.execute("SELECT ticker, actual_20d, hit, direction FROM predictions"):
        assert row["actual_20d"] == pytest.approx(truth[row["ticker"]], abs=0.01)
        if row["direction"] != "flat":
            assert row["hit"] == int((row["actual_20d"] > 0) == (row["direction"] == "up"))


def test_new_tickers_get_backfilled(news_db, events, reactions):
    news_db.execute(
        "INSERT INTO detected_events (name, event_time, event_date, after_close, category, region, us_involved, "
        "severity, surprise, n_articles, n_sources, classifier, status) VALUES ('Test', "
        "'2026-11-20T12:00:00+00:00', '2026-11-20', 'no', 'escalation', 'europe', 'no', '2', 'yes', 4, 4, 'rules', 'active')")
    news_db.execute("INSERT INTO predictions (event_id, ticker, made_at, direction, n_analogs) VALUES (1, 'ITA', 'x', 'up', 8)")
    predict.predict_new(news_db, events, reactions, log=lambda m: None)
    tickers = {r[0] for r in news_db.execute("SELECT ticker FROM predictions")}
    assert tickers == set(DEFENSE_TICKERS)
    assert news_db.execute("SELECT made_at FROM predictions WHERE ticker = 'ITA'").fetchone()[0] == "x"  # untouched


def test_progress_and_runup_before(prices):
    row = {"event_date": "2025-06-13", "name": "x", "category": "war_outbreak", "region": "middle_east",
           "us_involved": "no", "severity": "3", "surprise": "yes", "after_close": "no"}
    progress = predict.progress(prices, row, "ITA")
    assert progress["days"] == 20 and progress["reaction_day"] == "2025-06-13"
    assert isinstance(predict.runup_before(prices, row, "ITA"), float)
    future = {**row, "event_date": "2030-01-01"}
    assert predict.progress(prices, future, "ITA") is None


def test_pipeline_runs_offline(news_db, no_claude, monkeypatch):
    """A full pipeline pass with the network and market refresh replaced by fakes."""
    import news
    fake = [{"url": f"https://x.test/p{i}", "title": t, "source": f"Outlet {i}", "feed": "fake",
             "published_at": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(timespec="seconds")}
            for i, t in enumerate(STORY)]
    monkeypatch.setattr(news, "fetch_all", lambda log=print: (fake, []))
    monkeypatch.setattr(pipeline, "last_market_refresh", lambda db: datetime.now(timezone.utc))
    summary = pipeline.run_once(log=lambda m: None)
    assert summary["new_articles"] == 4 and summary["new_events"] == 1 and summary["predicted"] == 1
    assert "finished_at" in summary
