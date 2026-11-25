# The FastAPI back end the dashboard talks to.

import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture(scope="module")
def client():
    with TestClient(api.app) as c:
        yield c


def test_options(client):
    o = client.get("/api/options").json()
    assert "ITA" in o["tickers"] and "EUDEF" in o["tickers"]
    assert set(o["markets"]) == {"US", "EU"}
    assert o["ticker_market"]["RHM.DE"] == "EU"


def test_events_list_and_bad_ticker(client):
    events = client.get("/api/events?ticker=ITA").json()
    assert len(events) > 100 and {"abnormal_20d", "confounds"} <= set(events[0])
    assert client.get("/api/events?ticker=XYZ").status_code == 422


@pytest.mark.parametrize("ticker, expected", [("ITA", "LMT"), ("EUDEF", "RHM.DE")])
def test_event_detail_shows_its_own_market(client, ticker, expected):
    d = client.get(f"/api/events/2022-02-24?ticker={ticker}").json()
    assert expected in d["series"][0]
    assert len(d["series"]) == 25 and d["benchmark_name"]


def test_event_detail_404(client):
    assert client.get("/api/events/1999-01-01").status_code == 404


def test_analogs_and_validation(client):
    body = {"category": "war_outbreak", "region": "europe", "us_involved": "yes", "severity": "3", "surprise": "yes"}
    r = client.post("/api/analogs", json=body).json()
    assert 1 <= len(r["analogs"]) <= 8
    assert {"hit_rate", "always_up_hit_rate"} <= set(r["track_record"])
    assert "Track record" in r["thesis"]
    assert client.post("/api/analogs", json={**body, "category": "war"}).status_code == 422
    assert client.post("/api/analogs", json={**body, "top": 99}).status_code == 422


def test_backtest_and_runup_endpoints(client):
    b = client.get("/api/backtest?ticker=ITA").json()
    assert b["summary"]["leave_one_out"]["events"] > 100 and b["predictions"]
    r = client.get("/api/runup?ticker=ITA&window=20d").json()
    assert len(r["thirds"]) == 3 and r["points"]
    assert client.get("/api/runup?window=5d").status_code == 422


def test_categories(client):
    cats = client.get("/api/categories?ticker=EUDEF").json()
    assert {c["category"] for c in cats} >= {"war_outbreak", "de_escalation"}
    assert all(len(c["path"]) == 25 for c in cats if c["path"])


def test_claude_features_fail_politely_without_a_key(client, no_claude):
    body = {"category": "war_outbreak", "region": "europe", "us_involved": "yes", "severity": "3", "surprise": "yes"}
    r = client.post("/api/claude-thesis", json=body)
    assert r.status_code == 503 and "API key" in r.json()["detail"]
    r = client.post("/api/parse-headline", json={"headline": "China announces naval blockade of Taiwan"})
    assert r.status_code == 503
    assert client.post("/api/parse-headline", json={"headline": "short"}).status_code == 422


def test_live_endpoints_on_a_temporary_database(client, news_db):
    news_db.execute(
        "INSERT INTO detected_events (name, event_time, event_date, after_close, category, region, us_involved, "
        "severity, surprise, n_articles, n_sources, classifier, status) VALUES ('Test event', "
        "'2026-11-20T12:00:00+00:00', '2026-11-20', 'no', 'escalation', 'europe', 'no', '2', 'yes', 4, 4, 'rules', 'active')")
    news_db.commit()
    status = client.get("/api/live/status").json()
    assert status["events"] == 1 and status["classifier"] == "rules" and status["auto"] is False

    events = client.get("/api/live/events?ticker=ITA").json()
    assert events[0]["name"] == "Test event" and "runup_60d" in events[0]
    event_id = events[0]["id"]
    assert client.post(f"/api/live/events/{event_id}/dismiss").json()["status"] == "dismissed"
    assert client.get("/api/live/events").json() == []
    assert len(client.get("/api/live/events?include_dismissed=true").json()) == 1
    assert client.post(f"/api/live/events/{event_id}/restore").json()["status"] == "active"
    assert client.post(f"/api/live/events/{event_id}/delete").status_code == 422
    assert client.post("/api/live/events/9999/dismiss").status_code == 404
    assert client.get("/api/live/scorecard?ticker=ITA").json()["pending"] == 0
