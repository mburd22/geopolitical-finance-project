# Live pipeline robustness: retrying busy servers, the run log file, and the live_report CLI.
# No real network: httpx.MockTransport plays the server.

import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import live_report
import news
import pipeline


def mock_client(responses):
    """An httpx client whose server answers with `responses` in order (status, headers)."""
    calls = []

    def handler(request):
        calls.append(str(request.url))
        status, headers = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(status, headers=headers, text="{}")

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_busy_server_is_retried_with_growing_waits():
    client, calls = mock_client([(429, {}), (503, {}), (200, {})])
    waits = []
    response = news.get_with_retry(client, "https://api.example.test/doc", sleep=waits.append)
    assert response.status_code == 200
    assert len(calls) == 3
    assert waits == [news.RETRY_BASE_SECONDS, news.RETRY_BASE_SECONDS * 2]


def test_retry_after_header_is_respected_but_capped():
    client, _ = mock_client([(429, {"Retry-After": "7"}), (429, {"Retry-After": "3600"}), (200, {})])
    waits = []
    news.get_with_retry(client, "https://api.example.test/doc", sleep=waits.append)
    assert waits == [7.0, news.RETRY_MAX_SECONDS]


def test_gives_up_after_the_last_attempt():
    client, calls = mock_client([(429, {})])
    waits = []
    response = news.get_with_retry(client, "https://api.example.test/doc", sleep=waits.append)
    assert response.status_code == 429
    assert len(calls) == news.RETRY_ATTEMPTS and len(waits) == news.RETRY_ATTEMPTS - 1


def test_ordinary_errors_are_not_retried():
    client, calls = mock_client([(404, {})])
    response = news.get_with_retry(client, "https://feeds.example.test/rss", sleep=lambda s: pytest.fail("slept"))
    assert response.status_code == 404 and len(calls) == 1


def test_gdelt_429_then_success(monkeypatch):
    body = '{"articles": [{"url": "https://x.test/a", "title": "Missile strike", "domain": "x.test", "seendate": "20261121T143000Z"}]}'
    answers = iter([httpx.Response(429), httpx.Response(200, text=body)])
    client = httpx.Client(transport=httpx.MockTransport(lambda request: next(answers)))
    items = news.fetch_gdelt(client, sleep=lambda s: None)
    assert [i["title"] for i in items] == ["Missile strike"]


def test_log_file_rotates(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LOG_PATH", tmp_path / "pipeline.log")
    monkeypatch.setattr(pipeline, "LOG_MAX_BYTES", 100)
    for i in range(10):
        pipeline.write_log_line(f"message number {i}")
    assert (tmp_path / "pipeline.log.1").exists()
    assert (tmp_path / "pipeline.log").stat().st_size <= 100 + 60
    assert "message number 9" in (tmp_path / "pipeline.log").read_text(encoding="utf-8")


def test_each_run_is_logged_to_the_file(news_db, no_claude, monkeypatch):
    monkeypatch.setattr(news, "fetch_all", lambda log=print: ([], ["Some feed: ConnectError"]))
    monkeypatch.setattr(pipeline, "last_market_refresh", lambda db: datetime.now(timezone.utc))
    pipeline.run_once(log=lambda m: None)
    text = pipeline.LOG_PATH.read_text(encoding="utf-8")
    assert "Run started" in text
    assert "Run finished: 0 new articles" in text and "1 sources failed" in text


def test_a_failed_run_is_logged(news_db, monkeypatch):
    def broken(log=print):
        raise RuntimeError("disk full")
    monkeypatch.setattr(news, "fetch_all", broken)
    monkeypatch.setattr(pipeline, "last_market_refresh", lambda db: datetime.now(timezone.utc))
    with pytest.raises(RuntimeError):
        pipeline.run_once(log=lambda m: None)
    assert "Run failed: RuntimeError: disk full" in pipeline.LOG_PATH.read_text(encoding="utf-8")


def add_event(db, name, event_date, status="active"):
    cursor = db.execute(
        "INSERT INTO detected_events (name, event_date, event_time, after_close, category, region, us_involved, "
        "severity, surprise, n_articles, n_sources, classifier, status) "
        "VALUES (?, ?, ?, 'no', 'military_strike', 'middle_east', 'no', '2', 'yes', 5, 4, 'rules', ?)",
        (name, event_date, event_date + "T12:00:00+00:00", status))
    return cursor.lastrowid


def test_live_report_lists_scored_and_pending(news_db, prices):
    old = add_event(news_db, "Old strike", "2025-06-13")
    recent = add_event(news_db, "Recent strike", (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat())
    add_event(news_db, "Not an event", "2025-06-14", status="dismissed")
    news_db.execute("INSERT INTO predictions (event_id, ticker, made_at, predicted_median, direction, n_analogs, "
                    "actual_20d, hit, scored_at) VALUES (?, 'ITA', 'x', 1.5, 'up', 8, 3.2, 1, 'y')", (old,))
    news_db.execute("INSERT INTO predictions (event_id, ticker, made_at, predicted_median, direction, n_analogs) "
                    "VALUES (?, 'ITA', 'x', -0.5, 'down', 8)", (recent,))
    news_db.commit()

    rows = live_report.report_rows(news_db, prices, "ITA")
    assert [r["name"] for r in rows] == ["Recent strike", "Old strike"]  # newest first, dismissed hidden
    assert rows[1]["result"] == "RIGHT" and rows[1]["actual"] == 3.2
    assert rows[0]["result"].startswith("pending")
    assert len(live_report.report_rows(news_db, prices, "ITA", include_dismissed=True)) == 3

    lines = []
    live_report.print_report(news_db, prices, "ITA", out=lines.append)
    assert "Hit rate 100.0% on 1 calls" in lines[1]
    assert any("Old strike" in line and "RIGHT" in line for line in lines)


def test_live_report_opens_the_database_read_only(news_db):
    db = live_report.open_read_only(news.DB_PATH)
    assert live_report.has_table(db, "predictions")
    with pytest.raises(sqlite3.OperationalError):
        db.execute("DELETE FROM predictions")
    db.close()


def test_live_report_with_no_database(tmp_path):
    assert live_report.open_read_only(tmp_path / "missing.db") is None
