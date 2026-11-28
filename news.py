# Fetch geopolitical news from public RSS feeds (and GDELT) and store new articles.
#
# Everything lives in a small SQLite database, data/news.db, so the pipeline can run
# repeatedly and only ever process articles it hasn't seen before.
#
# Run on its own:  .\.venv\Scripts\python.exe news.py

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus, urlsplit, urlunsplit

import httpx
from defusedxml import ElementTree  # safe XML parsing: feeds are untrusted input

DB_PATH = Path(__file__).parent / "data" / "news.db"
HEADERS = {"User-Agent": "defense-event-tracker/0.1 (personal research project)"}

# General world-news feeds: broad coverage, filtered later by keywords.
FEEDS = {
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Guardian World": "https://www.theguardian.com/world/rss",
    "NPR World": "https://feeds.npr.org/1004/rss.xml",
    "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
}

# Targeted Google News searches: pick up stories from many outlets at once.
GOOGLE_QUERIES = [
    "military strike", "invasion troops", "missile test", "ceasefire agreement",
    "defense spending NATO", "coup military", "terror attack", "naval blockade",
]

GDELT_QUERY = "(airstrike OR invasion OR ceasefire OR missile OR coup OR \"defense budget\") sourcelang:english"

# Servers say "too many requests" (429) or "try again later" (5xx) when busy. GDELT in
# particular allows about one request every 5 seconds. Instead of giving up, wait and try
# again, waiting twice as long each time ("exponential backoff").
RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_ATTEMPTS = 3       # tries in total, including the first
RETRY_BASE_SECONDS = 5   # wait 5 s, then 10 s
RETRY_MAX_SECONDS = 60   # never wait longer than this, whatever the server asks


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row  # rows behave like dictionaries
    db.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY,
            url TEXT UNIQUE,
            title TEXT NOT NULL,
            source TEXT,
            feed TEXT,
            published_at TEXT,      -- ISO time, UTC
            fetched_at TEXT,
            relevant INTEGER,       -- 1 if the keyword filter thinks it is geopolitical
            event_id INTEGER        -- set once the detector assigns it to an event
        );
        CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY,
            started_at TEXT, finished_at TEXT, summary TEXT
        );
    """)
    return db


def normalize_url(url):
    """Drop tracking parameters and fragments so the same story isn't stored twice."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, "", ""))


def parse_time(text):
    if not text:
        return None
    try:
        moment = parsedate_to_datetime(text)  # RSS uses RFC 822 dates
    except (TypeError, ValueError):
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def parse_rss(xml_text, feed_name):
    root = ElementTree.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        title = clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not title or not link.startswith(("http://", "https://")):
            continue
        source = clean(item.findtext("source")) or feed_name
        if feed_name.startswith("Google News") and " - " in title:
            title = title.rsplit(" - ", 1)[0]  # Google appends " - Outlet name"
        items.append({
            "url": normalize_url(link) if not feed_name.startswith("Google News") else link,
            "title": title,
            "source": source,
            "feed": feed_name,
            "published_at": parse_time(item.findtext("pubDate")),
        })
    return items


def retry_wait(response, attempt):
    """Seconds to wait before the next try: the server's Retry-After if it gave one, else backoff."""
    asked = response.headers.get("Retry-After", "")
    seconds = float(asked) if asked.replace(".", "", 1).isdigit() else RETRY_BASE_SECONDS * 2 ** attempt
    return min(seconds, RETRY_MAX_SECONDS)


def get_with_retry(client, url, attempts=RETRY_ATTEMPTS, sleep=time.sleep, log=None):
    """client.get(url), retrying busy-server answers (429, 5xx). Returns the last response.

    Connection errors are NOT retried: if the network is down, waiting won't fix it, and
    retrying 14 sources would only make a run take minutes. `sleep` is swappable for tests.
    """
    for attempt in range(attempts):
        response = client.get(url)
        if response.status_code not in RETRY_STATUSES or attempt == attempts - 1:
            return response
        wait = retry_wait(response, attempt)
        if log:
            log(f"{urlsplit(url).netloc} answered {response.status_code}, retrying in {wait:.0f}s")
        sleep(wait)
    return response


def fetch_gdelt(client, sleep=time.sleep, log=None):
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + quote_plus(GDELT_QUERY)
           + "&mode=artlist&format=json&maxrecords=100&timespan=12h&sort=datedesc")
    response = get_with_retry(client, url, sleep=sleep, log=log)
    if response.status_code != 200 or not response.text.startswith("{"):
        raise RuntimeError(f"GDELT returned {response.status_code}")
    items = []
    for a in json.loads(response.text).get("articles", []):
        if not a.get("url", "").startswith(("http://", "https://")):
            continue
        seen = a.get("seendate", "")  # like 20261121T143000Z
        published = (datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
                     if seen else None)
        items.append({"url": normalize_url(a["url"]), "title": clean(a.get("title")),
                      "source": a.get("domain", "GDELT"), "feed": "GDELT", "published_at": published})
    return items


def fetch_all(log=print, sleep=time.sleep):
    """Download every feed. Returns (articles, errors). One failing feed never stops the rest."""
    articles, errors = [], []
    sources = dict(FEEDS)
    for query in GOOGLE_QUERIES:
        sources[f"Google News: {query}"] = (
            f"https://news.google.com/rss/search?q={quote_plus(query + ' when:2d')}&hl=en-US&gl=US&ceid=US:en")

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for name, url in sources.items():
            try:
                response = get_with_retry(client, url, sleep=sleep, log=log)
                response.raise_for_status()
                articles.extend(parse_rss(response.text, name))
            except Exception as error:  # a broken feed shouldn't stop the run
                errors.append(f"{name}: {type(error).__name__}")
        try:
            articles.extend(fetch_gdelt(client, sleep=sleep, log=log))
        except Exception as error:
            errors.append(f"GDELT: {error}")
    log(f"Fetched {len(articles)} items from {len(sources) + 1} sources"
        + (f" ({len(errors)} failed: {', '.join(errors)})" if errors else ""))
    return articles, errors


def store(db, articles, is_relevant):
    """Insert articles not seen before. Returns how many were new."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    known_titles = {row[0] for row in db.execute(
        "SELECT lower(title) FROM articles WHERE fetched_at > datetime('now', '-7 days')")}
    new = 0
    for a in articles:
        if not a["title"] or a["title"].lower() in known_titles:
            continue  # same headline from another feed
        cursor = db.execute(
            "INSERT OR IGNORE INTO articles (url, title, source, feed, published_at, fetched_at, relevant) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (a["url"], a["title"], a["source"], a["feed"], a["published_at"] or now, now,
             int(is_relevant(a["title"]))),
        )
        if cursor.rowcount:
            new += 1
            known_titles.add(a["title"].lower())
    db.commit()
    return new


if __name__ == "__main__":
    from classify import is_relevant

    db = connect()
    articles, _ = fetch_all()
    new = store(db, articles, is_relevant)
    total, relevant = db.execute("SELECT count(*), sum(relevant) FROM articles").fetchone()
    print(f"{new} new articles stored ({total} total, {relevant} look geopolitical)")
    for row in db.execute("SELECT published_at, source, title FROM articles WHERE relevant = 1 "
                          "ORDER BY published_at DESC LIMIT 12"):
        print(f"  {row['published_at'][:16]}  {row['source'][:18]:18}  {row['title'][:90]}")
