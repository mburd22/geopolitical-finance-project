# Optional Claude features: write a thesis in plain English, and turn a news headline
# into the tags our analog matcher needs.
#
# These need an Anthropic API key in a file called .env in the project folder:
#   ANTHROPIC_API_KEY=sk-ant-...
# Without a key everything else still works; only these two features are switched off.

from typing import Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from check_events import ALLOWED

load_dotenv()  # copies the values in .env into environment variables, where the SDK looks for them

MODEL = "claude-opus-5-5"

# Server-side fallback: if Claude declines a request, the API re-runs it on a
# suitable fallback model inside the same call, instead of returning a refusal.
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

_client = None


class ClaudeUnavailable(Exception):
    """Raised when Claude can't be used: no API key, a network problem, or a refusal."""


def client():
    # Create the client the first time it's needed, then reuse it.
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def call(**request):
    """Send a request to Claude, turning the many possible failures into one clear error."""
    try:
        response = request.pop("method")(model=MODEL, **FALLBACK, **request)
    except anthropic.AuthenticationError:
        raise ClaudeUnavailable("Claude features need an API key. Add ANTHROPIC_API_KEY to the .env file.")
    except anthropic.RateLimitError:
        raise ClaudeUnavailable("Claude is rate limited right now. Try again in a minute.")
    except anthropic.APIConnectionError:
        raise ClaudeUnavailable("Couldn't reach Claude. Check your internet connection.")
    except anthropic.APIStatusError as error:
        raise ClaudeUnavailable(f"Claude returned an error ({error.status_code}).")
    except TypeError as error:
        # The SDK raises this when it can't find any credentials at all.
        if "api_key" in str(error) or "auth" in str(error).lower():
            raise ClaudeUnavailable("Claude features need an API key. Add ANTHROPIC_API_KEY to the .env file.")
        raise
    if response.stop_reason == "refusal":
        raise ClaudeUnavailable("Claude declined this request.")
    return response


# ---------- 1. A written thesis ----------

THESIS_SYSTEM = """You are an analyst writing for a student learning how geopolitical events
move defense stocks. You are given a hypothetical new event and statistics from similar
past events (its "analogs"). Write a short thesis of 3 short paragraphs:
1. The call: does the stock likely beat, lag or track the market over the next month, and how sure can we be?
   Judge certainty from the engine's backtested hit rate versus the "always beats the market" baseline:
   if the engine barely beats that baseline, say plainly that its call is not much better than a default guess.
2. The evidence: which analogs matter most and why, citing the numbers given.
3. The caveats: what could make this time different, including any confounds flagged on the analogs.
Use only the numbers provided. Plain English, no jargon without a short explanation,
no headings or bullet points. End with: "Historical base rate, not investment advice." """


def write_thesis(new_event, analogs, stats, track_record, ticker):
    """Ask Claude to write a thesis from the analog results. Returns plain text."""
    lines = [f"New event: {new_event}", f"Stock: {ticker} (returns are vs the S&P 500, in %)",
             f"The engine's backtested track record for this stock: {track_record}",
             f"Summary stats: {stats}", "Analogs:"]
    for a in analogs:
        flags = "; ".join(a["confounds"]) or "none"
        lines.append(
            f"- {a['date']} {a['event']} ({a['category']}, {a['region']}, similarity {a['similarity']}%): "
            f"1d {a['abnormal_1d']}, 5d {a['abnormal_5d']}, 20d {a['abnormal_20d']}. Confounds: {flags}"
        )

    response = call(
        method=client().beta.messages.create,
        max_tokens=16000,
        output_config={"effort": "medium"},
        system=THESIS_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(lines)}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


# ---------- 2. Headline -> tags ----------

# Structured output: Claude must answer in exactly this shape, with only allowed values.
class HeadlineTags(BaseModel):
    category: Literal[tuple(sorted(ALLOWED["category"]))]
    region: Literal[tuple(sorted(ALLOWED["region"]))]
    us_involved: Literal["yes", "no"]
    severity: Literal["1", "2", "3"] = Field(description="1 minor, 2 significant, 3 major")
    surprise: Literal["yes", "no"] = Field(description="yes if markets were unlikely to expect it")
    reasoning: str = Field(description="One or two sentences explaining the choices")


HEADLINE_SYSTEM = """Classify a geopolitical news headline for a defense-stock analog tool.
Categories: war_outbreak (a new war or invasion), military_strike (a specific attack or strike),
escalation (rising tension without a full war), de_escalation (ceasefire, deal, summit, withdrawal),
terrorism, weapons_test (missile or nuclear tests, new weapons), coup (coup, regime collapse, mutiny),
election, defense_spending (budgets, procurement deals, alliance spending targets).
Regions: europe (including Russia, Ukraine, the Caucasus), middle_east (including Turkey and Iran),
east_asia (China, Taiwan, Koreas, Japan, Southeast Asia), south_asia (India, Pakistan, Afghanistan),
americas, africa, global.
us_involved is yes only if the US is a direct party (its forces, government or election)."""


def parse_headline(headline):
    """Turn a headline into analog-matcher tags. Returns a dict."""
    response = call(
        method=client().beta.messages.parse,
        max_tokens=16000,
        output_config={"effort": "low"},  # a quick classification doesn't need deep thought
        system=HEADLINE_SYSTEM,
        messages=[{"role": "user", "content": headline}],
        output_format=HeadlineTags,
    )
    if response.parsed_output is None:
        raise ClaudeUnavailable("Claude's answer couldn't be read. Try rephrasing the headline.")
    return response.parsed_output.model_dump()
