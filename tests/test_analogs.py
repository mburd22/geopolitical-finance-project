# The analog engine: similarity scores, which past events count as analogs, and the thesis.

import pandas as pd

from find_analogs import (
    MIN_SIMILARITY, WEIGHTS, find_analogs, same_family, similarity, summarize, write_thesis,
)

WAR = {"category": "war_outbreak", "region": "europe", "us_involved": "yes", "severity": "3", "surprise": "yes"}


def test_identical_events_score_100():
    assert similarity(WAR, WAR) == 100


def test_score_is_between_0_and_100():
    other = {"category": "election", "region": "africa", "us_involved": "no", "severity": "1", "surprise": "no"}
    assert 0 <= similarity(WAR, other) <= 100


def test_category_families():
    assert same_family("war_outbreak", "military_strike")
    assert not same_family("de_escalation", "defense_spending")
    assert same_family("coup", "election")


def test_unrelated_categories_are_never_analogs(events):
    """A spending deal must never be an analog for a ceasefire, however similar the other tags."""
    ceasefire = {**WAR, "category": "de_escalation"}
    found = find_analogs(ceasefire, events, top_n=50)
    assert set(found["category"]) == {"de_escalation"}


def test_analogs_are_sorted_and_above_threshold(events):
    found = find_analogs(WAR, events)
    assert len(found) <= 8
    assert (found["similarity"] >= MIN_SIMILARITY).all()
    assert list(found["similarity"]) == sorted(found["similarity"], reverse=True)


def test_reactions_filter_skips_unmeasured_events(events, reactions):
    """An event whose 20-day window hasn't finished can't take an analog slot."""
    unmeasured = set(zip(events["date"], events["event"])) - set(zip(reactions["date"], reactions["event"]))
    assert unmeasured, "expected at least one recent event without a measured reaction"
    election = {"category": "election", "region": "americas", "us_involved": "yes", "severity": "2", "surprise": "no"}
    found = find_analogs(election, events, top_n=20, reactions=reactions)
    assert not set(zip(found["date"], found["event"])) & unmeasured


def test_thesis_mentions_track_record_and_disclaimer(events, reactions):
    found = find_analogs(WAR, events, reactions=reactions)
    matched, stats = summarize(found, reactions, ticker="ITA")
    record = {"leave_one_out": {"hit_rate": 53.0, "always_up_hit_rate": 59.0}, "past_only": {"hit_rate": 51.0}}
    thesis = write_thesis(WAR, matched, stats, ticker="ITA", track_record=record)
    assert "Track record" in thesis and "59%" in thesis
    assert "not a forecast or investment advice" in thesis


def test_region_warning_when_no_local_analogs(events, reactions):
    africa_terror = {"category": "terrorism", "region": "global", "us_involved": "no", "severity": "2", "surprise": "yes"}
    found = find_analogs(africa_terror, events, reactions=reactions)
    matched, stats = summarize(found, reactions)
    if not (matched["region"] == "global").any():
        assert "Warning: none of these analogs happened in global" in write_thesis(africa_terror, matched, stats)


def test_weights_cover_every_tag():
    assert set(WEIGHTS) == {"category", "region", "us_involved", "severity", "surprise"}
    assert sum(WEIGHTS.values()) > 0
