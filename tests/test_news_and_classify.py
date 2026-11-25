# Reading news feeds safely, and the keyword classifier.

import pytest

import classify
import news

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Russia launches missile strikes on Kyiv</title>
        <link>https://example.com/a?utm_source=x#top</link>
        <pubDate>Sat, 21 Nov 2026 20:30:00 GMT</pubDate></item>
  <item><title>Evil link</title><link>javascript:alert(1)</link></item>
  <item><title></title><link>https://example.com/empty</link></item>
</channel></rss>"""

GOOGLE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Iran readies blockade run - Benzinga</title>
        <link>https://news.google.com/rss/articles/abc</link>
        <source url="https://benzinga.com">Benzinga</source>
        <pubDate>Sat, 21 Nov 2026 20:46:00 GMT</pubDate></item>
</channel></rss>"""


def test_parse_rss_keeps_only_safe_links_and_titles():
    items = news.parse_rss(RSS, "Test feed")
    assert len(items) == 1
    item = items[0]
    assert item["url"] == "https://example.com/a"  # tracking parameters and fragment dropped
    assert item["published_at"] == "2026-11-21T20:30:00+00:00"
    assert item["source"] == "Test feed"


def test_google_news_titles_lose_outlet_suffix():
    item = news.parse_rss(GOOGLE, "Google News: blockade")[0]
    assert item["title"] == "Iran readies blockade run"
    assert item["source"] == "Benzinga"


def test_malicious_xml_is_rejected():
    """defusedxml refuses entity tricks that could exhaust memory ("billion laughs")."""
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss>&b;</rss>'
    with pytest.raises(Exception):
        news.parse_rss(bomb, "Bad feed")


def test_store_skips_repeats(news_db):
    items = news.parse_rss(RSS, "Test feed")
    assert news.store(news_db, items, classify.is_relevant) == 1
    assert news.store(news_db, items, classify.is_relevant) == 0  # same URL again
    copy = [{**items[0], "url": "https://other.com/same-story"}]
    assert news.store(news_db, copy, classify.is_relevant) == 0  # same headline, different site


@pytest.mark.parametrize("title, category", [
    ("Russia invades neighbouring country", "war_outbreak"),
    ("North Korea test-fires ICBM", "weapons_test"),
    ("Military coup topples government in Niger", "coup"),
    ("Israeli airstrikes hit Gaza", "military_strike"),
    ("Ceasefire agreed between Israel and Hezbollah", "de_escalation"),
    ("Germany boosts defense budget to 3% of GDP", "defense_spending"),
    ("Tensions rise as China stages drills", "escalation"),
    ("Local bakery wins award", None),
])
def test_category_of(title, category):
    assert classify.category_of(title) == category


@pytest.mark.parametrize("title, relevant", [
    ("Russian missiles strike Kyiv overnight", True),
    ("Premier League football results", False),
    ("Russia lost 1.6 million troops since invasion began", False),  # running war tally, not news
    ("Watch: latest stories from the front", False),
])
def test_is_relevant(title, relevant):
    assert classify.is_relevant(title) is relevant


def test_region_of():
    assert classify.region_of("Pakistan test-fires missile at Pokhran-style range") == "south_asia"
    assert classify.region_of("Strikes near the Strait of Hormuz") == "middle_east"
    assert classify.region_of("Pentagon announces review") == "americas"
    assert classify.region_of("Something happened somewhere") == "global"


def test_classify_titles_majority_vote():
    tags = classify.classify_titles([
        "Israeli airstrikes hit southern Lebanon",
        "Airstrikes pound Lebanon overnight",
        "Tensions high after strikes",
    ])
    assert tags["category"] == "military_strike"
    assert tags["region"] == "middle_east"
    assert classify.classify_titles(["Nothing to see here"]) is None
