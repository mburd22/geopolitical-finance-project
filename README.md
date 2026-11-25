# Defense Stock Event Tracker

How do defense stocks react to geopolitical events, and can past reactions tell us anything about the next one?

This project measures how defense stocks moved against their own market around 113 geopolitical events from 2015 to November 2026:

- **US:** Lockheed Martin, RTX, Northrop Grumman, General Dynamics and the ITA defense ETF, vs the S&P 500.
- **Europe:** Rheinmetall, BAE Systems, Thales, Saab, Leonardo and an equal-weighted basket of the five (EUDEF), in euros, vs the STOXX Europe 600.

An **analog engine** takes a new event, finds the most similar past events, and writes a thesis from how the stocks reacted then. A **backtest** checks whether the engine is actually any good.

It also runs on its own. A **live pipeline** reads 14 news sources every hour and detects new geopolitical events. For each one it makes a prediction for every stock, locks the prediction in, and scores it once 20 trading days have passed, building a live track record nobody can quietly revise.

It comes with a React dashboard backed by a Python API.

## What it found

From 113 events (2015 to November 2026), measured over 20 trading days against each stock's own market:

- **Elections and defense-spending decisions move defense stocks the most.** ITA beat the market by an average of +4.2% after elections (9 events) and +2.3% after spending decisions (8).
- **De-escalation hurts.** Ceasefires, deals and summits were the clearest negative: ITA −1.2% on average, beating the market only 38% of the time.
- **War outbreaks are not reliably good for defense stocks.** ITA averaged +1.3%, but beat the market only half the time. When the US and Israel went to war with Iran on 28 Feb 2026, ITA *lagged* the market by 4% and Rheinmetall by 8%. Defense stocks had already rallied hard before it: LMT was up 22–26% vs the market after China's December Taiwan drills and the January Maduro raid.
- **"Sell the news" can be brutal.** After the April 2026 US–Iran ceasefire, LMT fell 28.7% and ITA 13.3% vs the market.
- **European defense stocks react two to four times as strongly.** After spending decisions, the European basket beat its market by +11.9% (vs +2.3% for ITA). After war outbreaks it was +6.4% (vs +1.3%). Seven trading days after Russia invaded Ukraine, Rheinmetall was up 69% vs the European market.
- **Individual stocks swing far more than the sector.** After the invasion of Ukraine, NOC and LMT were up about 25% and 21% vs the market within 7 trading days, while the ETF moved about 6%.

![Defense stocks vs the market around the Russian invasion of Ukraine](docs/event_2022-02-24.png)

## Does the analog engine work?

**No better than a simple guess.** Each event was hidden in turn and predicted from the others:

| Share of directional calls that were right | ITA | European basket | Average, all 11 stocks |
|---|---|---|---|
| Analog engine (leave one out) | 53% | 49% | 56% |
| Analog engine (only earlier events) | 51% | 50% | 57% |
| Baseline: "defense always beats the market" | 59–64% | 57–60% | 58% |

How we got here, honestly:
- **The first weights were a coin flip.** With 71 events, a severity-heavy set tuned on ITA looked good: 67% vs a 62% baseline.
- **That was overfitting.** After adding 42 events and scoring across all 11 stocks, those weights fell 4.7 points *below* the baseline. No weight combination we tried beats the baseline on average. The most robust choice is the simplest, matching on event type and region only, and that's what the engine uses now. `backtest.py --tune` now always scores across all stocks, to make this kind of luck harder to mistake for skill.
- **Where it fails:** war outbreaks (0 of 5 calls right for ITA), coups and de-escalation. In those categories, what happened last time is a poor guide to what happens next.
- **Confidence labels didn't work either.** A high/medium/low label was tested and removed: "high" calls were right *less* often. The dashboard shows the real backtested hit rate next to the baseline instead.
- **Confounding is everywhere.** 84 of 113 events had earnings, another event, or a 3%+ market day inside their 20-day window. The dashboard flags these on every event.

So treat this as a research tool. Its value is in the measured history, the confound flags and the analogs as context, **not in its calls.** Nothing here is investment advice.

## How it works

1. **Prices:** daily closes since 2015 from Yahoo Finance (`yfinance`). Each market is kept on its own trading calendar, with its own benchmark: SPY for the US, the iShares STOXX Europe 600 fund (EXSA.DE) for Europe. BAE and Saab are converted to euros with daily exchange rates.
2. **Events:** a hand-built database (`data/events.csv`) tagged by category, region, US involvement, severity, surprise, and whether the news broke after the US market close.
3. **Event study:** for each event, find the first trading day markets could react. Measure each stock's return minus SPY's (the *abnormal return*) over 1, 5 and 20 trading days.
4. **Confound checks:** flag events whose window contains company earnings, another event, or market turmoil.
5. **Analog engine:** score every past event's similarity to a new one, take the closest 8, and summarize how the stocks reacted.
6. **Backtest:** leave-one-out and past-only predictions, scored against simple baselines.
7. **Optional Claude features:** turn a news headline into tags, and write a fuller thesis from the numbers. These need an Anthropic API key.

### The live pipeline

```
news feeds ─► store new articles ─► group by story ─► classify ─► new event? ─► predict (locked) ─► score after 20 days
(news.py)        (data/news.db)      (detect.py)    (classify.py      merge with        (predict.py)
                                                     or Claude)    recent coverage
```

- **Sources:** BBC World, Al Jazeera, Guardian World, NPR World, Defense News, 8 targeted Google News searches, and GDELT.
- **What counts as an event:** a story covered by at least 3 articles from 3 different outlets. Coverage of the same story over the next 5 days is merged into it rather than counted again.
- **Classification:** with an `ANTHROPIC_API_KEY`, Claude tags each story and decides whether it's genuinely new and market-relevant. Without one, keyword rules do it. They're free, but noisier: expect some false positives, which you can dismiss in the dashboard.
- **Timing:** each event's reaction day comes from the earliest article's time in New York, so news that breaks after the 4pm close counts from the next trading day.
- **Running it:** the API server runs the pipeline every hour in the background (`AUTO_PIPELINE`, `PIPELINE_EVERY_MINUTES` in `.env`). To run it without the dashboard: `python pipeline.py` (once) or `python pipeline.py --loop 60`. Market data refreshes at most every 12 hours. `python refresh.py` refreshes it on demand.

## Running it

Requires Python 3.13+ and Node.js 20+.

```bash
# Python side
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Build all the data (prices, earnings, reactions, charts) in one go
.\.venv\Scripts\python.exe refresh.py

# Start the API, which also starts the hourly news pipeline
# (http://localhost:8000/docs lists every endpoint)
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
| `refresh.py` | One command to re-download and recalculate all market data |
| `download_prices.py`, `download_earnings.py` | Fetch market data |
| `pipeline.py` | The live loop: news → events → predictions → scores |
| `news.py` | Fetch RSS feeds and GDELT into `data/news.db` |
| `detect.py`, `classify.py` | Group headlines into stories and tag them as events |
| `predict.py` | Locked-in live predictions and later scoring |
| `calculate_reactions.py` | The event study: abnormal returns per event and stock |
| `confounds.py` | Earnings, overlapping-event and market-turmoil checks |
| `find_analogs.py` | The analog engine and template thesis (also a command-line tool) |
| `backtest.py` | Scores the engine; `--tune` searches for better weights |
| `make_charts.py` | Static PNG charts |
| `api.py` | FastAPI back end for the dashboard |
| `ai.py` | Optional Claude features |
| `frontend/` | React + Recharts dashboard |

## Limitations

- **Small sample:** 113 events, some categories with only 6. Africa has 9 and the Americas 12, so analogs there are thin.
- **Tags are judgment calls,** especially severity and surprise.
- **Live detection without Claude is noisy.** The keyword rules catch the big stories, but also let through things like company weapons tests or human-interest pieces that mention a war.
- **The live pipeline only runs while the API server is running** on your computer.
- **Event timing is US-based.** The `after_close` flag refers to the 4pm New York close. European markets close at 11:30 New York time, so for news that broke during US hours, Europe may really react a day later than measured.
- **European defense stocks have trended up hard since 2022,** so "beat the market" is partly that trend, not the event.
- **BAE and Thales have no earnings dates** in the Yahoo data, so earnings confounds are missed for those two.
- **Market-adjusted returns only:** stock return minus SPY. A fuller model would adjust for each stock's sensitivity to the market (beta).
