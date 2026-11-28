# Defense Stock Event Tracker

How do defense stocks react to geopolitical events, and can past reactions tell us anything about the next one?

This project measures how defense stocks moved against their own market around 144 geopolitical events from 2015 to November 2026:

- **US:** Lockheed Martin, RTX, Northrop Grumman, General Dynamics and the ITA defense ETF, vs the S&P 500.
- **Europe:** Rheinmetall, BAE Systems, Thales, Saab, Leonardo and an equal-weighted basket of the five (EUDEF), in euros, vs the STOXX Europe 600.

An **analog engine** takes a new event, finds the most similar past events, and writes a thesis from how the stocks reacted then. A **backtest** checks whether the engine is actually any good.

It also runs on its own. A **live pipeline** reads 14 news sources every hour and detects new geopolitical events. For each one it makes a prediction for every stock, locks the prediction in, and scores it once 20 trading days have passed, building a live track record nobody can quietly revise.

It comes with a React dashboard backed by a Python API.

## What it found

From 143 measured events (2015 to November 2026; the newest is still inside its 20-day window), measured over 20 trading days against each stock's own market. Ranges in brackets are 90% bootstrap confidence intervals: with 10 to 25 events per category, the true average could plausibly sit anywhere inside them.

- **Defense-spending decisions are the one reliable positive in the US.** ITA beat the market by +2.2% on average after them (12 events; +0.7% to +3.9%), the only US category whose range stays above zero.
- **Elections looked like the strongest signal, until there were more of them.** With 9 elections, ITA averaged +4.2% (+1.4% to +7.2%). Adding 7 more, from India, the UK, France, Germany, Taiwan and the 2018 US midterms, brought it down to +1.1% (−1.0% to +3.5%). The big moves were a handful of US and European results: Biden in 2020 (+14.1%, the same week as the first vaccine results), Merz in 2025, Labour in 2024 and Trump in 2016.
- **Terrorist attacks don't help defense stocks.** Across 15 attacks, ITA averaged −0.3% (−1.5% to +0.8%) and beat the market 47% of the time.
- **De-escalation leans negative, but not clearly.** After ceasefires, deals and summits, ITA did worse than the market on average: −1.2%, beating it only 36% of the time. The range (−3.1% to +0.5%) still includes zero.
- **War outbreaks are not reliably good for defense stocks.** ITA averaged +1.3% (−1.2% to +3.8%), and beat the market only half the time. When the US and Israel went to war with Iran on 28 Feb 2026, ITA *lagged* the market by 4% and Rheinmetall by 8%. Defense stocks had already rallied hard before it: LMT was up 22–26% vs the market after China's December Taiwan drills and the January Maduro raid.
- **"Sell the news" can be brutal.** After the April 2026 US–Iran ceasefire, LMT fell 28.7% and ITA 13.3% vs the market.
- **European defense stocks react two to five times as strongly.** After spending decisions, the European basket beat its market by +10.8% (+5.2% to +17.5%), vs +2.2% for ITA. After war outbreaks it was +6.4% (vs +1.3%). Five of its nine event types have ranges entirely above zero, against one for ITA. Seven trading days after Russia invaded Ukraine, Rheinmetall was up 69% vs the European market.
- **Individual stocks swing far more than the sector.** After the invasion of Ukraine, NOC and LMT were up about 25% and 21% vs the market within 7 trading days, while the ETF moved about 6%.

### Does event type matter at all?

With nine event types, some average will look large by luck alone. A permutation test checks this: shuffle the event types at random thousands of times, and count how often the shuffled averages spread out as much as the real ones. A small share (under 5%) means event type really goes with how the stock moved.

- **For the first few days, yes.** Event type goes with the day-1 move for 7 of the 11 stocks, and the 5-day move for 6 (share under 5%). That's far more than the 1 in 20 you'd expect by chance. The European basket comes in at 0.4% on day 1.
- **Over 20 days, mostly not.** For every US stock the 20-day share is 26% to 59% (ITA: 59%), so the ranking of event types above could be noise. Only Saab is under 5%, with the European basket borderline at 5%.

The dashboard shows this test for each stock on the By event type tab.

![Defense stocks vs the market around the Russian invasion of Ukraine](docs/event_2022-02-24.png)

## Does the analog engine work?

**No better than a simple guess.** Each event was hidden in turn and predicted from the others:

| Share of directional calls that were right | ITA | European basket | Average, all 11 stocks |
|---|---|---|---|
| Analog engine (leave one out) | 47% | 58% | 55% |
| Analog engine (only earlier events) | 43% | 52% | 55% |
| Baseline: "defense always beats the market" | 49–56% | 56–60% | 55–56% |

How we got here, honestly:
- **The first weights were a coin flip.** With 71 events, a severity-heavy set tuned on ITA looked good: 67% vs a 62% baseline.
- **That was overfitting.** After adding 42 events and scoring across all 11 stocks, those weights fell 4.7 points *below* the baseline. No weight combination we tried beats the baseline on average. The most robust choice is the simplest, matching on event type and region only, and that's what the engine uses now. Re-tuned after adding 31 more events (144 in all): still no set beats the baseline, and the best one beat the current weights by only 0.1 and 0.6 points, so they were left alone. `backtest.py --tune` now always scores across all stocks, to make this kind of luck harder to mistake for skill.
- **Per stock, the gaps are mostly noise.** The dashboard shows a 90% range for "engine minus baseline", resampled event by event. With only earlier events, it crosses zero for 10 of the 11 stocks. With leave one out it's clearer, but points both ways: the engine beat the baseline for Lockheed (+15 points) and Northrop (+20), and trailed it for General Dynamics, Thales, Saab and Leonardo (−7 to −11). With 22 comparisons, a few clear-looking results are expected by luck alone.
- **Where it fails:** war outbreaks (4 of 9 calls right for ITA), coups and de-escalation. In those categories, what happened last time is a poor guide to what happens next.
- **Confidence labels didn't work either.** A high/medium/low label was tested and removed: "high" calls were right *less* often. The dashboard shows the real backtested hit rate next to the baseline instead.
- **Confounding is everywhere.** 115 of 144 events had earnings, another event, or a 3%+ market day inside their 20-day window. The dashboard flags these on every event.

### Would it do better over a shorter horizon?

Event type matters most in the first days, so `horizons.py` reruns the backtest with the same weights to predict the 1-day and 5-day moves instead. Averaged over all 11 stocks:

| Horizon | Engine (leave one out) | Engine (only earlier events) | Always up |
|---|---|---|---|
| 1 day | 50% | 56% | 58–60% |
| 5 days | 52% | 55% | 54% |
| 20 days | 55% | 55% | 55–56% |

**No.** At day 1 the engine does clearly *worse* than assuming defense goes up (by 4 to 8 points). Event type goes with how *big* the first move is, but taking the majority of eight past analogs can't call its *direction* better than that simple rule.

### Does a run-up predict the reaction?

The 2026 Iran war suggested "buy the rumor, sell the news": ITA had beaten the market by 21% over the 60 trading days before the war started, then lagged by 4%. `runup.py` tests whether that's a general pattern across all events, using ordinary days as a control:

- **US stocks: no reliable link.** Bigger 60-day run-ups went with slightly weaker moves afterwards (rank correlation −0.14 for ITA, p ≈ 0.06). That's no stronger than on ordinary days (−0.15), so it's general mean reversion, not something events cause.
- **Europe: momentum, if anything.** Stocks that had already run up tended to keep going. The European basket's top third by run-up beat its market by +6.4% afterwards. Much of this is the 2022 rearmament wave, when events came in clusters.
- **Adding run-up to the engine didn't help.** Tested on the first 113 events: averaged over all 11 stocks it scored 56% (leave one out) and 55% (only earlier events), against 58% for the always-up baseline.

So the 2026 sell-off was the exception, not the rule. The dashboard shows each event's run-up as context only.

### Does adjusting for beta change anything?

The numbers above are *market-adjusted*: a stock's return minus its market's. That treats every stock as moving one-for-one with the market. The textbook event-study alternative is the *market model*: fit each stock's alpha (its own drift) and beta (how strongly it follows the market) on the 120 trading days ending 10 days before each event, and count only the move beyond alpha + beta × the market's move. Defense stocks are low-beta (Lockheed and Northrop about 0.4, ITA 0.9), so this matters. `compare_models.py` reruns everything both ways:

- **The ranking of event types holds.** Spending decisions stay on top for ITA (+2.0%) and de-escalation at the bottom, now more clearly: −2.4%, beating the market only 21% of the time (and −2.3% for the European basket too). Most averages shrink, because alpha soaks up some of the sector's drift. The European basket's spending reaction falls from +10.8% to +8.3%.
- **Individual events often flip.** The two models agree closely overall (correlation 0.92), but 247 of 1,573 stock-event results change sign.
- **The engine still has no real edge.** With the beta model, it's right 52% of the time in both modes, averaged over the 11 stocks. That's 1–3 points above the always-up baseline, but only because the baseline drops to a coin flip (49–51%). On the first 113 events, re-tuning the weights for the beta model gained a further 0.4 points, which is noise.
- **Events matter for European stocks, not US ones.** Market-adjusted, the five European stocks and their basket beat their market in 60% of the 20-day windows after events, against 52% of ordinary 20-day spells. With the beta model it's 50% vs 45%. The US stocks show almost no difference (52% vs 51%, and 50% vs 48%). Lockheed and Northrop actually beat the market slightly *less* often after events.
- **Run-ups still don't predict anything.** The weak US mean reversion disappears (ITA −0.03, ordinary days −0.09), and Europe keeps its mild momentum.

So the project keeps the simpler market-adjusted model as its default. Switching is one line: `ABNORMAL_MODEL` in `calculate_reactions.py`.

So treat this as a research tool. Its value is in the measured history, the confound flags and the analogs as context, **not in its calls.** Nothing here is investment advice.

## How it works

1. **Prices:** daily closes since June 2014 from Yahoo Finance (`yfinance`). Each market is kept on its own trading calendar, with its own benchmark: SPY for the US, the iShares STOXX Europe 600 fund (EXSA.DE) for Europe. BAE and Saab are converted to euros with daily exchange rates.
2. **Events:** a hand-built database (`data/events.csv`) tagged by category, region, US involvement, severity, surprise, and whether the news broke after the US market close.
3. **Event study:** for each event, find the first trading day markets could react. Measure each stock's return minus its market's (the *abnormal return*) over 1, 5 and 20 trading days. A beta-adjusted market model is built in too (`ABNORMAL_MODEL`), and `compare_models.py` reruns the main results with both.
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
- **Classification:** with an `ANTHROPIC_API_KEY`, Claude tags each story and decides whether it's genuinely new and market-relevant. Without one, keyword rules do it. They're free, but cruder. They count a headline only when its main clause says what happened ("X *as tensions rise*" is about X), and they rule out known false alarms: foiled plots, court cases, tributes, threats emailed to the police, pleas or deadlines for a ceasefire, and companies testing their own products. A story also needs over a third of its headlines to agree on the category. Expect some false positives still, which you can dismiss in the dashboard.
- **What the dashboard shows first:** for each live event, *what history says*: how the stock did after past events of the same type, how it did after any event, and whether event type has been a reliable guide for that stock (the permutation test). The engine's call comes second, labelled with its backtested hit rate next to the always-up rule, because it hasn't beaten it.
- **Timing:** each event's reaction day comes from the earliest article's time in New York, so news that breaks after the 4pm close counts from the next trading day.
- **Running it:** the API server runs the pipeline every hour in the background (`AUTO_PIPELINE`, `PIPELINE_EVERY_MINUTES` in `.env`). To run it without the dashboard: `python pipeline.py` (once) or `python pipeline.py --loop 60`. Market data refreshes at most every 12 hours. `python refresh.py` refreshes it on demand.
- **When a source is busy:** a "too many requests" (429) or server error (5xx) is retried twice, waiting 5 then 10 seconds, or as long as the server asks (up to a minute). GDELT does this often. Connection errors aren't retried, so a run with no network still finishes quickly.
- **Checking on it:** every run writes a line-by-line account to `data/pipeline.log` (not in git; rolls over at about 1 MB). `python live_report.py --ticker ITA` prints the live record for one stock: each detected event, the locked-in call, how the stock has done since, and the final score. Add `--all` to include dismissed events. It opens the database read-only.

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

## Tests

```bash
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

150 tests, about 25 seconds. They never touch the internet or the live news database (`data/news.db`). They cover:

- **The event-study maths**, on synthetic prices with known answers: reaction day, after-close news, weekends, benchmark subtraction and run-ups. Also the beta model: it recovers a known alpha and beta, ignores the days just before the news, and doesn't count a high-beta stock's normal move in a rising market as abnormal.
- **The event database checker.**
- **The analog engine:** related categories only, measured events only, and the thesis.
- **The backtest,** including that the past-only mode never peeks at the future.
- **Bootstrap confidence intervals:** they contain the average, narrow with more events, and the paired engine-vs-baseline gap is tighter than the separate ranges. The permutation test finds real group differences and doesn't invent them from pure noise.
- **The backtest at other horizons** judges each call against the right move.
- **Confound flags,** on known real cases.
- **Feed parsing,** including rejecting `javascript:` links and malicious XML.
- **The keyword classifier,** including 33 hand-labelled stories: real events it must catch and false alarms it must drop.
- **The base-rate summary** for live events.
- **The live pipeline end to end:** clustering, merging follow-up coverage, locked predictions and scoring.
- **Pipeline robustness:** retrying busy servers (with a fake server), the run log and its rollover, and the read-only live report.
- **Every API endpoint,** including the polite failure when there's no Claude key.

GitHub runs the tests and the dashboard build on every push (`.github/workflows/tests.yml`).

## Project layout

| File | What it does |
|---|---|
| `data/events.csv` | The event database, edited by hand. Run `check_events.py` after editing. |
| `refresh.py` | One command to re-download and recalculate all market data |
| `download_prices.py`, `download_earnings.py` | Fetch market data |
| `pipeline.py` | The live loop: news → events → predictions → scores |
| `live_report.py` | Prints the live record (events, calls, results) for one stock |
| `news.py` | Fetch RSS feeds and GDELT into `data/news.db` |
| `detect.py`, `classify.py` | Group headlines into stories and tag them as events |
| `predict.py` | Locked-in live predictions and later scoring |
| `history.py` | The base-rate summary shown first for each live event |
| `calculate_reactions.py` | The event study: abnormal returns per event and stock |
| `confounds.py` | Earnings, overlapping-event and market-turmoil checks |
| `find_analogs.py` | The analog engine and template thesis (also a command-line tool) |
| `backtest.py` | Scores the engine; `--tune` searches for better weights across all stocks |
| `runup.py` | Tests whether pre-event run-ups predict the reaction |
| `horizons.py` | Backtests the engine at 1, 5 and 20 days |
| `uncertainty.py` | Bootstrap confidence intervals, and a permutation test of whether event type matters |
| `compare_models.py` | Reruns the main results with market-adjusted and beta-adjusted returns; `--tune` re-tunes weights for each (slow) |
| `make_charts.py` | Static PNG charts |
| `api.py` | FastAPI back end for the dashboard |
| `ai.py` | Optional Claude features |
| `frontend/` | React + Recharts dashboard. Tabs other than Live load on demand, so the charting library only downloads when a chart is shown |
| `tests/` | The pytest suite |

## Limitations

- **Small sample:** 144 events, 10 to 25 per category. South Asia has 12 events, Africa 14 and the Americas 15, so analogs there are thin, and only one event (Christchurch) is outside the six regions.
- **Tags are judgment calls,** especially severity and surprise.
- **Live detection without Claude is noisy.** In Nov 2026 the first 24 stories the keyword rules flagged were hand-labelled: only 8 were real, market-relevant events. The rest were company weapons tests, court cases, foiled plots, tributes and pleas for peace. The tightened rules keep those 8 and drop the other 16, and the labelled cases are now tests. But that's one week of news, so expect new kinds of false alarm. Events detected before the change stay in the database; dismiss them in the dashboard.
- **The live pipeline only runs while the API server is running** on your computer.
- **Event timing is US-based.** The `after_close` flag refers to the 4pm New York close. European markets close at 11:30 New York time, so for news that broke during US hours, Europe may really react a day later than measured. A check suggests this rarely matters: starting every European window one day later captures *less* of the move, not more (the basket's day-1 reaction to war outbreaks drops from +2.5% to 0.0%), and the 20-day results barely change (correlation 0.94; 13 of 143 signs flip).
- **European defense stocks have trended up hard since 2022,** so "beat the market" is partly that trend, not the event.
- **BAE and Thales have no earnings dates** in the Yahoo data, so earnings confounds are missed for those two.
- **Market-adjusted by default.** Beta adjustment is available but doesn't change the conclusions (see above). Neither model adjusts for other factors, like defense stocks moving with oil or with interest rates.
