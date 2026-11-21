# Rule-based classification of news headlines into the same tags as data/events.csv.
#
# This is the free fallback. When an Anthropic API key is set, the pipeline asks Claude
# instead (see ai.classify_clusters), which handles nuance far better: "talks collapse"
# vs "talks succeed", ongoing coverage vs a genuinely new event, and so on.

import re

# Category keywords. Order matters: the first category with a match wins, so stronger,
# rarer signals (an invasion) beat weaker, common ones (tensions).
CATEGORY_PATTERNS = [
    ("war_outbreak", r"\binvad(e|es|ed|ing)\b|\binvasion\b|declares? war|ground (offensive|invasion)|launch(es|ed)? (a )?war"),
    ("weapons_test", r"missile test|nuclear test|\bicbm\b|test[- ]fires?|hypersonic (missile )?test|ballistic missile launch"),
    ("coup", r"\bcoup\b|\bjunta\b|\bmutiny\b|overthr(ow|own|ew)|seizes? power|regime (falls|collapse)"),
    ("terrorism", r"\bterror(ist|ism)?\b|suicide bomb|\bgunmen\b|hostages? (taken|seized)|massacre"),
    ("military_strike", r"\bair ?strikes?\b|missile strikes?|drone (strike|attack)s?|\bstrikes? on\b|\bbomb(s|ed|ing)\b|\bshelling\b|\bshot down\b|shoots down"),
    ("de_escalation", r"\bceasefire\b|\btruce\b|peace (deal|agreement|accord|plan)|\barmistice\b|de-?escalat|withdraws? troops|troops withdraw"),
    ("defense_spending", r"defen[cs]e (budget|spending)|military (budget|spending)|\barms deal\b|% of gdp|\brearm|procurement|defen[cs]e contract"),
    ("escalation", r"\btensions?\b|\bmobili[sz]|\bultimatum\b|\bblockade\b|massing troops|military drills|airspace|\bescalat|warns? of war|threatens?"),
    ("election", r"\bwins? (the )?(presidential |general )?election\b|\belection (result|victory|win)\b|\breferendum\b"),
]

# Words that show a headline is about geopolitics/defense at all.
RELEVANCE = re.compile(
    r"military|army|troops|missile|nuclear|war\b|strike|attack|defen[cs]e|navy|air force|pentagon|nato|"
    r"ceasefire|invasion|coup|terror|sanction|drone|weapon|arms|border clash|blockade|hezbollah|hamas|"
    r"houthi|kremlin|warship|fighter jet|artillery|insurgent|militant",
    re.IGNORECASE,
)

# Words that usually mean a headline is NOT a market-moving geopolitical event.
NOISE = re.compile(
    r"\b(football|soccer|cricket|tennis|olympic|film|movie|recipe|celebrity|album|review|podcast|quiz|"
    r"weather|earthquake|hurricane|wildfire|obituary|dies aged|opinion|analysis|explainer|how to|what is|"
    r"watch|latest stories|season|episode|in pictures|photos|anniversary|years after|years ago)\b"
    # Running tallies of an ongoing war are background, not a new event.
    r"|since (the )?(full-scale )?(invasion|beginning|start)|combat losses|losses of",
    re.IGNORECASE,
)

REGION_TERMS = {
    "europe": ["ukraine", "ukrainian", "kyiv", "kharkiv", "odesa", "zelensky", "russia", "russian", "moscow",
               "kremlin", "putin", "poland", "polish",
               "germany", "german", "france", "french", "britain", "british", "uk ", "nato", "baltic", "lithuania",
               "latvia", "estonia", "finland", "sweden", "romania", "moldova", "belarus", "serbia", "kosovo", "georgia",
               "armenia", "azerbaijan", "europe", "european", "eu "],
    "middle_east": ["israel", "israeli", "gaza", "hamas", "hezbollah", "lebanon", "iran", "iranian", "tehran", "syria",
                    "syrian", "iraq", "iraqi", "yemen", "houthi", "saudi", "turkey", "turkish", "jordan", "qatar",
                    "uae", "emirates", "red sea", "west bank", "egypt", "idf", "netanyahu", "khamenei",
                    "strait of hormuz", "hormuz", "persian gulf", "beirut", "damascus", "baghdad"],
    "east_asia": ["china", "chinese", "beijing", "taiwan", "taiwanese", "north korea", "pyongyang", "south korea",
                  "seoul", "japan", "japanese", "tokyo", "philippines", "south china sea", "myanmar", "vietnam",
                  "pla ", "xi jinping", "kim jong"],
    "south_asia": ["india", "indian", "delhi", "mumbai", "pokhran", "modi", "pakistan", "pakistani", "islamabad",
                   "karachi", "lahore", "khyber", "balochistan", "waziristan", "lakki marwat", "kashmir", "pahalgam",
                   "afghanistan", "kabul", "taliban", "bangladesh", "sri lanka", "nepal"],
    "americas": ["venezuela", "mexico", "cuba", "colombia", "brazil", "canada", "panama", "haiti"],
    "africa": ["sudan", "ethiopia", "somalia", "nigeria", "niger", "mali", "libya", "congo", "sahel", "kenya",
               "burkina faso", "chad", "eritrea", "mozambique", "africa"],
}

US_TERMS = re.compile(r"\b(u\.?s\.?|united states|america(n)?|pentagon|white house|washington|biden|trump|"
                      r"vance|hegseth|rubio|us military|us forces)\b", re.IGNORECASE)

MAJOR = re.compile(r"\b(war|nuclear|invasion|full-scale|hundreds killed|dozens killed|mass casualty)\b", re.IGNORECASE)
MINOR = re.compile(r"\b(drills?|warns?|talks|considers?|could|may|plans?|urges?|condemns?|foiled|thwarted|"
                   r"charged|arrested|plot|alleged)\b", re.IGNORECASE)
SCHEDULED = re.compile(r"\b(election|summit|vote|budget|talks|meeting|agreement)\b", re.IGNORECASE)


def is_relevant(title):
    return bool(RELEVANCE.search(title)) and not NOISE.search(title)


def category_of(title):
    lowered = title.lower()
    for category, pattern in CATEGORY_PATTERNS:
        if re.search(pattern, lowered):
            return category
    return None


def region_of(text):
    """Pick the region whose places are mentioned most. Ties go to the first match."""
    lowered = f" {text.lower()} "
    counts = {region: sum(lowered.count(term) for term in terms) for region, terms in REGION_TERMS.items()}
    best = max(counts, key=counts.get)
    if counts[best] > 0:
        return best
    return "americas" if US_TERMS.search(text) else "global"


def classify_titles(titles):
    """Tag a cluster of headlines about the same story. Returns a dict, or None if nothing matched."""
    votes = {}
    for title in titles:
        category = category_of(title)
        if category:
            votes[category] = votes.get(category, 0) + 1
    if not votes:
        return None
    # Majority vote, ties broken by the priority order above.
    order = [c for c, _ in CATEGORY_PATTERNS]
    category = max(votes, key=lambda c: (votes[c], -order.index(c)))
    text = " ".join(titles)

    severity = 2
    if category == "war_outbreak" or MAJOR.search(text):
        severity = 3
    elif sum(bool(MINOR.search(t)) for t in titles) > len(titles) / 2:
        severity = 1

    return {
        "category": category,
        "region": region_of(text),
        "us_involved": "yes" if US_TERMS.search(text) else "no",
        "severity": str(severity),
        "surprise": "no" if category in ("election", "defense_spending") or SCHEDULED.search(titles[0]) else "yes",
        "name": titles[0][:120],
        "reasoning": f"Keyword rules: {votes[category]} of {len(titles)} headlines matched '{category}'.",
    }
