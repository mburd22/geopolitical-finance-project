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
    ("coup", r"\bcoup\b|\bmutiny\b|overthr(ow|own|ew)|seizes? power|regime (falls|collapse)|"
             r"(military|army|soldiers|junta|rebels|taliban) (takes?|took|seizes?|seized) (power|control|over)"),
    ("terrorism", r"\bterror(ist|ism)?\b|suicide bomb|\bgunmen\b|hostages? (taken|seized)|massacre"),
    ("military_strike", r"\bair ?strikes?\b|missile strikes?|drone (strike|attack)s?|\bstrikes? (on|kills?|killing|hits?)\b|\bintercept(s|ed|ing)?\b|\bbomb(s|ed|ing)\b|\bshelling\b|\bshot down\b|shoots down"),
    ("de_escalation", r"\bceasefire\b|\btruce\b|peace (deal|agreement|accord|plan)|\barmistice\b|de-?escalat|withdraws? troops|troops withdraw"),
    ("defense_spending", r"defen[cs]e (budget|spending)|military (budget|spending)|\barms deal\b|% of gdp|\brearm|procurement|defen[cs]e contract"),
    ("escalation", r"\btensions?\b|\bmobili[sz]|\bultimatum\b|\bblockade\b|mass(es|ing)? troops|troop build-?up|military drills|airspace|\bescalat|warns? of war|threatens?"),
    ("election", r"\bwins? (the )?(presidential |general )?election\b|\belection (result|victory|win)\b|\breferendum\b"),
]

# A category match only counts if the headline doesn't ALSO show it's really something else.
# Found by hand-labelling what the live pipeline detected (tests/test_classifier_precision.py):
# a foiled plot, a court case or a tribute isn't a terror attack; a plea for a ceasefire, or a
# ceasefire being broken, isn't de-escalation; a company testing its product isn't a state
# weapons test; and someone accusing a rival of an "invasion" isn't a war breaking out.
COMPANIES = (r"adani|lockheed|raytheon|northrop|boeing|anduril|rheinmetall|saab|bae systems|thales|leonardo|"
             r"hanwha|elbit|rafael|tata|bharat dynamics|l3harris|general atomics|kongsberg|mbda|castelion|snc|"
             r"defen[cs]e (ltd|limited)")
FALSE_ALARMS = {
    "terrorism": r"\b(foil(s|ed)?|thwart(s|ed)?|plot(s|ted)?|charged|guilty|convicted|sentenced|trial|alert|"
                 r"threat(s|ens?|ened)?|warn(s|ed|ing)?|warnings?|tributes?|honou?rs?|salute|condemn(s|ed)?|"
                 r"victims of|questions?|talks|counter-terror\w*|anti-terror\w*|camera|details)\b",
    "de_escalation": r"\b(violat\w*|despite|wish(es)?|hopes?|wants?|calls? for|urges?|suggest\w*|hints?|"
                     r"deadline|working on|seeks?|propos(es|ed|al)|consider(s|ing)?|if)\b",
    # Escalation is between states: a threatening email to the local police is a security scare.
    "escalation": r"\b(e-?mail|letter|police)\b",
    "weapons_test": rf"\b({COMPANIES})\b|anti-tank",
    "war_outbreak": r"accus\w*.{0,40}invasion|['‘\"]open invasion|since (the )?(full-scale )?invasion",
    "coup": r"post-coup|acquit\w*|retrial|years (later|after|ago)",
}

# What share of a story's headlines must match its category. One stray headline in a cluster
# about something else (a summit, a business story) isn't enough to make it that kind of event.
MIN_VOTE_SHARE = 0.34

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
    r"watch|latest stories|season|episode|in pictures|photos|anniversary|years after|years ago|years later|"
    r"acquit(s|ted)?|retrial|guilty|convicted|sentenced|pays? tribute|tributes? to|honou?rs? victims)\b"
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


def main_clause(lowered):
    """The part of a headline that says what happened.

    "Israel turns to cheaper missile defences as Iran tensions escalate" is about Israel's
    purchase; the "as ...", "amid ...", "despite ..." and "while ..." part is background.
    A leading "As tensions soar, China masses troops" keeps the part after the comma.
    """
    if re.match(r"(as|amid|despite|while)\b", lowered) and "," in lowered:
        lowered = lowered.split(",", 1)[1]
    # (?<!such) keeps "missiles such as the Fatah-3" in one piece.
    return re.split(r"(?<!such)\s(?:amid|as|despite|while)\s", lowered, maxsplit=1)[0]


def category_of(title):
    """The first category whose keywords appear in the headline's main clause and whose
    false-alarm words (FALSE_ALARMS) don't appear anywhere in it. None if nothing fits."""
    lowered = title.lower()
    main = main_clause(lowered)
    for category, pattern in CATEGORY_PATTERNS:
        alarm = FALSE_ALARMS.get(category)
        if re.search(pattern, main) and not (alarm and re.search(alarm, lowered)):
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
    if votes[category] < MIN_VOTE_SHARE * len(titles):
        return None  # only a stray headline or two fits: the story is about something else
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
        # Name the event after the first headline that actually says what happened.
        "name": next(t for t in titles if category_of(t) == category)[:120],
        "reasoning": f"Keyword rules: {votes[category]} of {len(titles)} headlines matched '{category}'.",
    }
