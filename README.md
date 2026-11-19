# Defense Stock Event Tracker

How do defense stocks react to geopolitical events, and can past reactions tell us anything about the next one?

This project measures how US defense stocks (Lockheed Martin, RTX, Northrop Grumman, General Dynamics and the ITA defense ETF) moved against the S&P 500 around 71 geopolitical events from 2015 to 2025. An **analog engine** takes a new event, finds the most similar past events, and writes a thesis from how the stocks reacted then. A **backtest** checks whether the engine is actually any good.

It comes with a React dashboard backed by a Python API.

![Average reaction of the ITA defense ETF by event type](docs/category_paths.png)

## What it found

- **Spending announcements and elections move defense stocks the most.** Over 20 trading days, ITA beat the market by an average of +5.3% after elections and +3.9% after defense-spending announcements (4 events each).
- **War outbreaks help, and individual strikes barely register.** Outbreaks averaged +2.6%; one-off military strikes and escalations about +0.6%.
- **De-escalation holds defense stocks back.** Ceasefires and summits were the only category to lag the market (−0.1%, beating it in only 29% of cases).
- **Individual stocks swing far more than the sector.** After Russia invaded Ukraine, NOC and LMT were up about 25% and 21% vs the market within 7 trading days, while the ETF moved about 6%.

![Defense stocks vs the market around the Russian invasion of Ukraine](docs/event_2022-02-24.png)

## Does the analog engine work?

Each event was hidden in turn and predicted from the others:

| | ITA hit rate |
|---|---|
| Analog engine (leave one out) | **67%** |
| Analog engine (only earlier events) | 61% |
| Baseline: "defense always beats the market" | 62% |
| Baseline: same-category average | 64% |

**Bottom line: the engine roughly matches a simple "defense beats the market" guess.** It's modestly better on ITA and NOC, and no better on LMT, RTX or GD. With about 70 events, differences of a few points are noise.

Other things the backtest showed:
- The **first similarity weights were a coin flip** (54% on ITA). Tuning showed severity matters most, and that US involvement and surprise added nothing. The tuned weights also improved NOC, which they weren't tuned on.
- The old **high/medium/low confidence label didn't predict accuracy.** "High confidence" calls were right *less* often than "low" ones. It was removed, and the dashboard now shows the real backtested hit rate instead.
- **Confounding is everywhere.** 48 of 71 events had earnings, another event, or a 3%+ market day inside their 20-day window. The dashboard flags these on every event.

This is a research and learning project. **Nothing here is investment advice.**

## How it works

1. **Prices:** daily closes since 2015 from Yahoo Finance (`yfinance`), with SPY as the market benchmark.
2. **Events:** a hand-built database (`data/events.csv`) tagged by category, region, US involvement, severity, surprise, and whether the news broke after the US market close.
3. **Event study:** for each event, find the first trading day markets could react. Measure each stock's return minus SPY's (the *abnormal return*) over 1, 5 and 20 trading days.
4. **Confound checks:** flag events whose window contains company earnings, another event, or market turmoil.
5. **Analog engine:** score every past event's similarity to a new one, take the closest 8, and summarize how the stocks reacted.
6. **Backtest:** leave-one-out and past-only predictions, scored against simple baselines.
7. **Optional Claude features:** turn a news headline into tags, and write a fuller thesis from the numbers. These need an Anthropic API key.

## Running it

Requires Python 3.13+ and Node.js 20+.

```bash
# Python side
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Build the data (prices, earnings, reactions)
.\.venv\Scripts\python.exe download_prices.py
.\.venv\Scripts\python.exe download_earnings.py
.\.venv\Scripts\python.exe calculate_reactions.py

# Start the API (http://localhost:8000/docs lists every endpoint)
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173.

**Optional Claude features:** copy `.env.example` to `.env` and add your `ANTHROPIC_API_KEY`. Without it, everything else still works.

## Project layout

| File | What it does |
|---|---|
| `data/events.csv` | The event database, edited by hand. Run `check_events.py` after editing. |
| `download_prices.py`, `download_earnings.py` | Fetch market data |
| `calculate_reactions.py` | The event study: abnormal returns per event and stock |
| `confounds.py` | Earnings, overlapping-event and market-turmoil checks |
| `find_analogs.py` | The analog engine and template thesis (also a command-line tool) |
| `backtest.py` | Scores the engine; `--tune` searches for better weights |
| `make_charts.py` | Static PNG charts |
| `api.py` | FastAPI back end for the dashboard |
| `ai.py` | Optional Claude features |
| `frontend/` | React + Recharts dashboard |

## Limitations

- **Small sample:** 71 events, some categories with only 4. No African events yet.
- **Tags are judgment calls,** especially severity and surprise.
- **Only US defense stocks** for now. European defense stocks reacted very differently after 2022.
- **Market-adjusted returns only:** stock return minus SPY. A fuller model would adjust for each stock's sensitivity to the market (beta).
