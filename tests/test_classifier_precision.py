# Precision of the keyword classifier (the free fallback when there's no Claude key).
#
# Hand-labelled in Nov 2026 from what the live pipeline actually detected (data/news.db),
# headlines lightly paraphrased. DROP clusters were false positives: company product tests,
# court cases and foiled plots, tributes, pleas for peace, background mentions of a war.
# KEEP clusters are the kind of story data/events.csv is made of, and must still be caught.

import pytest

import classify

KEEP = [
    ("war_outbreak", ["Putin orders full-scale invasion of Ukraine",
                      "Russian troops cross into Ukraine as explosions heard in Kyiv",
                      "Russia invades Ukraine from three directions"]),
    ("war_outbreak", ["Israel declares war after Hamas attack from Gaza",
                      "Israel declares war as Hamas fighters storm border towns",
                      "Netanyahu: we are at war"]),
    ("war_outbreak", ["US and Israel launch war on Iran",
                      "US and Israel launch war on Iran with strikes on Tehran",
                      "Oil jumps as US and Israel launch war on Iran"]),
    ("military_strike", ["Israel launches air strikes on Iranian nuclear sites",
                         "Israeli airstrikes hit Iran's nuclear program",
                         "Explosions in Tehran as Israel strikes nuclear facilities"]),
    ("military_strike", ["US strikes on Houthi targets in Yemen",
                         "US launches airstrikes against Houthis",
                         "Pentagon confirms strikes on Houthi missile sites"]),
    ("terrorism", ["Gunmen kill dozens in coordinated Paris terror attacks",
                   "Paris attacks: terrorists strike concert hall and stadium",
                   "France declares emergency after terror attacks"]),
    ("terrorism", ["Terrorists kill 26 tourists in Pahalgam, Kashmir",
                   "Pahalgam terror attack: gunmen open fire on tourists",
                   "India vows response to Kashmir terror attack"]),
    ("de_escalation", ["Israel and Hamas agree ceasefire deal",
                       "Gaza ceasefire takes effect",
                       "Hostages to be freed as Gaza truce begins"]),
    ("de_escalation", ["India and Pakistan agree to ceasefire",
                       "India-Pakistan ceasefire announced after four days of fighting",
                       "Ceasefire between India and Pakistan holds"]),
    ("coup", ["Military seizes power in Niger coup",
              "Niger soldiers announce coup on national TV",
              "Coup in Niger: president detained by guards"]),
    ("coup", ["Wagner mutiny: mercenaries march on Moscow",
              "Prigozhin's mutiny threatens Putin",
              "Russia accuses Wagner chief of armed mutiny"]),
    ("weapons_test", ["North Korea conducts sixth nuclear test",
                      "North Korea claims hydrogen bomb in nuclear test",
                      "Seoul detects North Korean nuclear test"]),
    ("weapons_test", ["Pakistan test-fires Fatah-3 supersonic cruise missile",
                      "Pakistan claims successful Fatah-3 missile test",
                      "Pakistan tests Fatah-3 cruise missile"]),
    ("escalation", ["NATO calls Russian missiles landing in Poland a grave violation of airspace",
                    "Russian missile hits Poland as allies hold military exercise",
                    "Allies stand with Poland after airspace breach by Russia"]),
    ("military_strike", ["Saudi coalition intercepts Houthi missile and drones over Asir",
                         "Houthis threaten major escalation of strikes against Saudi Arabia",
                         "Saudi Arabia says it intercepts three Houthi missiles targeting Riyadh"]),
    ("military_strike", ["Gaza civil defence says Israeli strikes kill six",
                         "Israeli strikes kill six in Gaza despite ceasefire",
                         "Six killed in Israeli strikes on Gaza"]),
    ("escalation", ["China launches military drills around Taiwan",
                    "Chinese warships encircle Taiwan in military drills",
                    "Taiwan condemns Chinese military drills"]),
    ("defense_spending", ["NATO allies agree to spend 5% of GDP on defence",
                          "NATO summit backs 5% of GDP defence spending target",
                          "Allies commit to higher defence spending"]),
]

DROP = [
    ["Adani Defence test-fires four anti-tank missiles at Pokhran",
     "Adani Defence successfully tests Bagheera anti-tank missile",
     "Bagheera anti-tank missile hits targets in Pokhran test"],
    ["Man charged over alleged car bomb plot after Sydney counter-terror raids",
     "ISIS-inspired man charged with planning terrorist attack",
     "Sydney man charged after counter-terror raids"],
    ["Police foil major terror plot in Lakki Marwat",
     "Police foil terror attack in Lakki Marwat, suicide bomber killed",
     "Terror attack foiled in Lakki Marwat"],
    ["Man guilty of terror attack plot at migrant hotel in Hull",
     "Hull man found guilty of planning terror attack",
     "White supremacist convicted of planning bomb attack on asylum seekers"],
    ["General jailed for resisting 1961 coup acquitted 65 years later",
     "Former army general acquitted in coup retrial after 65 years",
     "Acquitted at last: general cleared in coup retrial"],
    ["Shah Rukh Khan pays tribute to victims of 26/11 and Pahalgam attacks",
     "Actor honours victims of 26/11 and Pahalgam terror attacks",
     "Respectful salute to security personnel martyred in terror attacks"],
    ["Hyderabad on high alert after email threatens terror attack",
     "Hyderabad police heighten security after email warns of terror attack",
     "Police receive terror attack warning in Hyderabad"],
    ["Delhi Police ban drones near airport for 60 days citing terror threat",
     "India and France condemn Pahalgam terror attack at counter-terror meeting",
     "China yet to share details on camera linked to Pahalgam terror attack"],
    ["Melania Trump calls for a ceasefire in Ukraine before Christmas",
     "Melania Trump's Christmas wish concerns the war in Ukraine",
     "Trump says US is working on a broader Ukraine ceasefire"],
    ["Trump sets January deadline for Ukraine ceasefire deal",
     "Trump hints at a large-scale ceasefire agreement between Russia and Ukraine",
     "Melania Trump has suggested a ceasefire in Ukraine before Christmas"],
    ["Hyderabad on alert after letter threatens 26/11-style attack",
     "Hyderabad police step up security after email threatens attack",
     "Lashkar threatens attack in Telangana capital, police say"],
    ["Israel attacks southern Lebanon despite ceasefire agreement",
     "Palestinians killed in Israeli ceasefire violations across Gaza",
     "Iran says it will return to ceasefire if US does"],
    ["ASEAN keeps Myanmar's military junta excluded from summit",
     "Myanmar's army-backed government calls ASEAN decision unfair",
     "Myanmar accuses ASEAN of discrimination as rift deepens over post-coup crisis"],
    ["US Air Force turns to SNC, Anduril and Castelion in push for cheaper missiles",
     "Israel reportedly turns to cheaper missile defences as Iran tensions escalate",
     "Iran's underground missile city reveals new launch strategy as regional tensions persist"],
    ["Pakistan minister ducks action-on-terror question during India visit",
     "Pakistan minister evades questions on Pahalgam attack",
     "Pakistan minister calls for evidence-based talks on terrorism"],
]


@pytest.mark.parametrize("category, titles", KEEP, ids=[t[0] for _, t in KEEP])
def test_big_stories_are_still_caught(category, titles):
    tags = classify.classify_titles(titles)
    assert tags is not None, "missed a real event"
    assert tags["category"] == category


@pytest.mark.parametrize("titles", DROP, ids=[t[0][:40] for t in DROP])
def test_false_positives_are_dropped(titles):
    assert classify.classify_titles(titles) is None


def test_quoted_invasion_is_not_a_war():
    """A diplomatic row where one side calls the other's actions an 'open invasion'."""
    tags = classify.classify_titles([
        "Somalia orders UAE ambassador to leave, accuses Emirates of 'open invasion'",
        "Somalia orders UAE ambassador out, accuses Emirates of 'open invasion'",
        "Somalia expels UAE envoy"])
    assert tags is None or tags["category"] != "war_outbreak"


def test_background_clause_does_not_decide_the_category():
    assert classify.main_clause("israel turns to cheaper missile defences as iran tensions escalate") == \
        "israel turns to cheaper missile defences"
    assert classify.main_clause("as tensions soar, china masses troops") == " china masses troops"
    assert classify.main_clause("missiles such as the fatah-3") == "missiles such as the fatah-3"
    assert classify.category_of("Russia masses troops on border as tensions soar") == "escalation"


@pytest.mark.parametrize("title", [
    "Hull man found guilty of planning terror attack",
    "General acquitted 65 years later",
    "Actor pays tribute to victims of terror attack",
])
def test_court_cases_and_tributes_are_not_stored_as_relevant(title):
    assert not classify.is_relevant(title)


def test_event_is_named_after_a_headline_that_says_what_happened():
    tags = classify.classify_titles(["Oil prices jump in Asian trading", "Israel launches air strikes on Iran",
                                     "Israeli airstrikes hit Tehran"])
    assert tags["name"] == "Israel launches air strikes on Iran"


def test_one_stray_headline_does_not_make_an_event():
    """A cluster where only one of five headlines mentions a category isn't that kind of event."""
    titles = ["Leaders meet in Brussels", "Summit agenda published", "Ministers arrive for talks",
              "Analysts expect little from meeting", "Drone strikes reported near border"]
    assert classify.classify_titles(titles) is None
