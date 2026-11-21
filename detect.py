# Turn a stream of headlines into events.
#
#   1. Group recent, relevant, unassigned articles that cover the same story (clustering).
#   2. Keep groups big enough to matter: several articles from at least two outlets.
#   3. Classify each group into the events.csv tags: with Claude if a key is set, else keyword rules.
#   4. Merge a group into an existing recent event when it's more coverage of the same story.
#
# Run on its own:  .\.venv\Scripts\python.exe detect.py

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import ai
import classify

NEW_YORK = ZoneInfo("America/New_York")
LOOKBACK_HOURS = 72      # cluster articles published in this window
MERGE_DAYS = 5           # coverage within this many days of an existing event can join it
MIN_ARTICLES = 3         # a group needs this many articles...
MIN_SOURCES = 3          # ...from at least this many different outlets

STOPWORDS = set("""a an the and or of to in on at for from by with as is are was were be been has have had it its
this that these those over after before into amid says said say new news latest live update updates
report reports could would will may might not no up down out more than about what who how why when""".split())


def ensure_tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS detected_events (
            id INTEGER PRIMARY KEY,
            name TEXT,
            first_seen TEXT,            -- when the pipeline first noticed it (UTC)
            event_time TEXT,            -- earliest article time (UTC)
            event_date TEXT,            -- that time as a New York date
            after_close TEXT,           -- 'yes' if the news broke after the US market close
            category TEXT, region TEXT, us_involved TEXT, severity TEXT, surprise TEXT,
            n_articles INTEGER, n_sources INTEGER,
            classifier TEXT,            -- 'claude' or 'rules'
            reasoning TEXT,
            status TEXT DEFAULT 'active',   -- 'active' or 'dismissed'
            updated_at TEXT
        );
    """)


def tokens(title):
    words = re.findall(r"[a-z][a-z'-]+", title.lower())
    return {w.rstrip("s") for w in words if len(w) > 2 and w not in STOPWORDS}


def places(title):
    lowered = f" {title.lower()} "
    return {term.strip() for terms in classify.REGION_TERMS.values() for term in terms if term in lowered}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def cluster(articles):
    """Greedy clustering on headline words, places and category, then a pass merging near-duplicate groups.

    "Rare" words (ones few headlines use, like a place or a weapon name) are strong evidence
    two headlines cover the same story, so two shared rare words are enough to join.
    """
    all_tokens = [tokens(a["title"]) for a in articles]
    frequency = {}
    for ts in all_tokens:
        for t in ts:
            frequency[t] = frequency.get(t, 0) + 1
    rare_limit = max(3, len(articles) // 50)

    def matches(info, member):
        score = jaccard(info["tokens"], member["tokens"])
        shared_rare = sum(1 for t in info["tokens"] & member["tokens"] if frequency.get(t, 0) <= rare_limit)
        shared_place = bool(info["places"] & member["places"])
        same_category = info["category"] is not None and info["category"] == member["category"]
        if score >= 0.3 or shared_rare >= 2 or (shared_place and same_category and score >= 0.12):
            return score + 0.1 * shared_rare
        return 0.0

    groups = []
    for article, ts in zip(articles, all_tokens):
        info = {"tokens": ts, "places": places(article["title"]), "category": classify.category_of(article["title"])}
        best, best_score = None, 0.0
        for group in groups:
            score = max(matches(info, member) for member in group["info"])
            if score > best_score:
                best, best_score = group, score
        if best is None:
            groups.append({"articles": [article], "info": [info]})
        else:
            best["articles"].append(article)
            best["info"].append(info)

    # Second pass: merge groups that ended up covering the same story.
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                links = sum(1 for a in groups[i]["info"] for b in groups[j]["info"] if matches(a, b))
                if links >= max(2, min(len(groups[i]["info"]), len(groups[j]["info"])) // 2):
                    groups[i]["articles"] += groups[j]["articles"]
                    groups[i]["info"] += groups[j]["info"]
                    del groups[j]
                    merged = True
                    break
            if merged:
                break
    return groups


def market_timing(utc_iso):
    """New York date of the news, and whether it broke after the US close (4pm ET on a weekday)."""
    moment = datetime.fromisoformat(utc_iso).astimezone(NEW_YORK)
    after_close = moment.weekday() < 5 and moment.hour >= 16
    return moment.date().isoformat(), "yes" if after_close else "no"


def classify_groups(groups, recent_events, log):
    """Tag each group. Returns (list of tag dicts or None, classifier name)."""
    if ai.claude_configured():
        try:
            return ai.classify_clusters([[a["title"] for a in g["articles"]] for g in groups], recent_events), "claude"
        except ai.ClaudeUnavailable as error:
            log(f"Claude unavailable ({error}); falling back to keyword rules")
    results = []
    for g in groups:
        tags = classify.classify_titles([a["title"] for a in g["articles"]])
        if tags:
            tags["same_as"] = None
        results.append(tags)
    return results, "rules"


def find_existing(db, tags, titles):
    """An active event from the last few days that this group is more coverage of, if any."""
    since = (datetime.now(timezone.utc) - timedelta(days=MERGE_DAYS)).isoformat()
    group_tokens = set().union(*(tokens(t) for t in titles))
    for row in db.execute(
            "SELECT id, name FROM detected_events WHERE status = 'active' AND event_time > ? "
            "AND category = ? AND region = ?", (since, tags["category"], tags["region"])):
        event_titles = [r[0] for r in db.execute("SELECT title FROM articles WHERE event_id = ?", (row["id"],))]
        event_tokens = set().union(*(tokens(t) for t in event_titles)) if event_titles else tokens(row["name"])
        if jaccard(group_tokens, event_tokens) >= 0.12:
            return row["id"]
    return None


def detect(db, log=print):
    """Find new events among unassigned articles. Returns the ids of events created."""
    ensure_tables(db)
    since = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).isoformat()
    articles = [dict(r) for r in db.execute(
        "SELECT id, title, source, published_at FROM articles "
        "WHERE relevant = 1 AND event_id IS NULL AND published_at > ? ORDER BY published_at", (since,))]
    groups = [g for g in cluster(articles)
              if len(g["articles"]) >= MIN_ARTICLES and len({a["source"] for a in g["articles"]}) >= MIN_SOURCES]
    log(f"{len(articles)} unassigned relevant articles -> {len(groups)} candidate stories")
    if not groups:
        return []

    recent = [dict(r) for r in db.execute(
        "SELECT id, name, category, region FROM detected_events WHERE status = 'active' "
        "AND event_time > ? ORDER BY event_time DESC LIMIT 40",
        ((datetime.now(timezone.utc) - timedelta(days=MERGE_DAYS)).isoformat(),))]
    tags_list, classifier = classify_groups(groups, recent, log)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    created, merged = [], 0
    for group, tags in zip(groups, tags_list):
        if not tags:
            continue  # not a market-relevant event
        titles = [a["title"] for a in group["articles"]]
        ids = [a["id"] for a in group["articles"]]
        existing = tags.get("same_as") or find_existing(db, tags, titles)
        if existing:
            db.executemany("UPDATE articles SET event_id = ? WHERE id = ?", [(existing, i) for i in ids])
            db.execute("UPDATE detected_events SET n_articles = (SELECT count(*) FROM articles WHERE event_id = ?), "
                       "n_sources = (SELECT count(DISTINCT source) FROM articles WHERE event_id = ?), updated_at = ? "
                       "WHERE id = ?", (existing, existing, now, existing))
            merged += 1
            continue
        earliest = min(a["published_at"] for a in group["articles"])
        event_date, after_close = market_timing(earliest)
        cursor = db.execute(
            "INSERT INTO detected_events (name, first_seen, event_time, event_date, after_close, category, region, "
            "us_involved, severity, surprise, n_articles, n_sources, classifier, reasoning, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tags["name"], now, earliest, event_date, after_close, tags["category"], tags["region"],
             tags["us_involved"], tags["severity"], tags["surprise"], len(ids),
             len({a["source"] for a in group["articles"]}), classifier, tags["reasoning"], now))
        db.executemany("UPDATE articles SET event_id = ? WHERE id = ?", [(cursor.lastrowid, i) for i in ids])
        created.append(cursor.lastrowid)
    db.commit()
    log(f"Classifier: {classifier}. {len(created)} new events, {merged} stories merged into existing events")
    return created


if __name__ == "__main__":
    import news

    db = news.connect()
    detect(db)
    for row in db.execute("SELECT * FROM detected_events ORDER BY event_time DESC LIMIT 15"):
        print(f"  #{row['id']:<3} {row['event_date']} {row['category']:16} {row['region']:12} sev {row['severity']} "
              f"{row['n_articles']:>2} articles/{row['n_sources']} outlets  {row['name'][:70]}")
