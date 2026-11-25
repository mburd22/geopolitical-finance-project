// Live: geopolitical events the pipeline found in the news by itself, each with a
// locked-in prediction, progress so far, and the result once 20 trading days pass.

import { useCallback, useEffect, useState } from 'react'
import { getLiveEvents, getLiveScorecard, getLiveStatus, runPipeline, setEventStatus } from '../api'
import { label, pct, signClass } from '../theme'

// "3 hours ago", "in 40 min"
function relative(iso) {
  if (!iso) return '—'
  const minutes = Math.round((new Date(iso) - Date.now()) / 60000)
  const abs = Math.abs(minutes)
  const text = abs < 60 ? `${abs} min` : abs < 48 * 60 ? `${Math.round(abs / 60)} h` : `${Math.round(abs / 1440)} days`
  return minutes < 0 ? `${text} ago` : `in ${text}`
}

// Only ever link to normal web pages (feeds are untrusted, so never "javascript:" links).
const safeUrl = (url) => (/^https?:\/\//i.test(url) ? url : null)

const CALL_TEXT = { up: 'Beat the market', down: 'Lag the market', flat: 'No clear call' }

function StatusBar({ status, onRun }) {
  const last = status.last_run
  return (
    <div className="card live-status">
      <div className="live-status-main">
        <span className={`dot ${status.running ? 'busy' : 'idle'}`} aria-hidden="true" />
        <div>
          <strong>{status.running ? 'Checking the news now…' : 'Watching 14 news sources'}</strong>
          <div className="small muted">
            {last ? `Last check ${relative(last.finished_at)} · ` : 'No checks yet · '}
            {status.auto ? `checks every ${status.every_minutes} min` : 'automatic checks are off'}
            {status.next_run_at && !status.running ? ` · next ${relative(status.next_run_at)}` : ''}
            {` · ${status.articles} articles read · prices through ${status.price_data_ends}`}
          </div>
        </div>
        <button type="button" className="secondary" onClick={onRun} disabled={status.running}>
          {status.running ? 'Checking…' : 'Check now'}
        </button>
      </div>
      {status.classifier === 'rules' && (
        <p className="small muted classifier-note">
          Events are tagged with <strong>keyword rules</strong>, which miss nuance and let some noise through.
          Add an Anthropic API key to <code>.env</code> to have Claude classify them instead.
        </p>
      )}
      {status.last_error && <p className="error small">Last run failed: {status.last_error}</p>}
      {last?.feed_errors?.length > 0 && (
        <p className="small muted">Some sources failed last time: {last.feed_errors.join(', ')}</p>
      )}
    </div>
  )
}

function Scorecard({ card, ticker }) {
  return (
    <div className="tiles">
      <div className="tile">
        <div className="tile-title">Live hit rate ({ticker})</div>
        <div className="tile-value">{card.hit_rate === null ? '—' : `${card.hit_rate.toFixed(0)}%`}</div>
        <div className="tile-note">
          {card.calls ? `${card.calls} scored calls · always-up ${card.always_up_hit_rate}%` : 'first results after 20 trading days'}
        </div>
      </div>
      <div className="tile">
        <div className="tile-title">Waiting to be scored</div>
        <div className="tile-value">{card.pending}</div>
        <div className="tile-note">predictions in their 20-day window</div>
      </div>
      <div className="tile">
        <div className="tile-title">Scored so far</div>
        <div className="tile-value">{card.scored}</div>
        <div className="tile-note">predictions with a final result</div>
      </div>
    </div>
  )
}

function Progress({ event }) {
  const p = event.progress
  const pred = event.prediction
  if (pred?.scored) {
    return (
      <div className="live-line">
        <span className="live-key">Result</span>
        <span className={signClass(pred.actual_20d)}>{pct(pred.actual_20d)}</span> vs the market after 20 days
        {pred.hit !== null && <strong className="result-tag">{pred.hit ? '✓ Prediction right' : '✗ Prediction wrong'}</strong>}
      </div>
    )
  }
  if (!p) {
    return (
      <div className="live-line">
        <span className="live-key">So far</span>
        <span className="muted">Markets haven't traded since the news{event.after_close === 'yes' ? ' (it broke after the close)' : ''}.</span>
      </div>
    )
  }
  return (
    <div className="live-line">
      <span className="live-key">So far</span>
      <span className={signClass(p.abnormal)}>{pct(p.abnormal)}</span> vs the market after {p.days} of 20 trading days
      <div className="progress-track" aria-hidden="true"><div style={{ width: `${(p.days / 20) * 100}%` }} /></div>
    </div>
  )
}

function EventCard({ event, ticker, onStatus }) {
  const [open, setOpen] = useState(false)
  const pred = event.prediction
  const dismissed = event.status === 'dismissed'
  return (
    <article className={`card live-event ${dismissed ? 'dismissed' : ''}`}>
      <div className="live-event-head">
        <div>
          <h3>{event.name}</h3>
          <div className="chips static">
            <span className="chip">{label(event.category)}</span>
            <span className="chip">{label(event.region)}</span>
            <span className="chip">Severity {event.severity}</span>
            {event.us_involved === 'yes' && <span className="chip">US involved</span>}
          </div>
          <p className="small muted">
            {event.event_date} · {event.n_articles} articles from {event.n_sources} outlets ·
            tagged by {event.classifier === 'claude' ? 'Claude' : 'keyword rules'}
          </p>
        </div>
        <button type="button" className="link-button" onClick={() => onStatus(event.id, dismissed ? 'restore' : 'dismiss')}
          title={dismissed ? 'Bring this event back' : 'Hide this if it is not a real event'}>
          {dismissed ? 'Restore' : 'Not an event'}
        </button>
      </div>

      {pred && (
        <div className="live-line">
          <span className="live-key">Prediction</span>
          <strong>{ticker}: {CALL_TEXT[pred.direction]}</strong>
          {pred.n_analogs > 0
            ? <span className="muted"> · median {pct(pred.predicted_median)} over 20 days in {pred.n_analogs} similar past events
                ({Math.round(pred.beat_share * pred.n_analogs)} beat the market)</span>
            : <span className="muted"> · no comparable past events</span>}
        </div>
      )}
      <Progress event={event} />
      {event.runup_60d !== null && event.runup_60d !== undefined && (
        <div className="live-line">
          <span className="live-key">Run-up</span>
          <span className={signClass(event.runup_60d)}>{pct(event.runup_60d)}</span>
          <span className="muted"> vs the market in the 60 trading days before the news (context only: run-ups
            haven't predicted reactions in the backtest)</span>
        </div>
      )}

      <button type="button" className="link-button" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? 'Hide details' : 'Show headlines, analogs and thesis'}
      </button>
      {open && (
        <div className="live-details">
          <h4>Headlines</h4>
          <ul className="headlines">
            {event.headlines.map((h) => (
              <li key={h.url}>
                {safeUrl(h.url)
                  ? <a href={safeUrl(h.url)} target="_blank" rel="noopener noreferrer">{h.title}</a>
                  : h.title}
                <span className="small muted"> · {h.source}</span>
              </li>
            ))}
          </ul>
          {pred?.analogs?.length > 0 && (
            <>
              <h4>Closest past events</h4>
              <ul className="headlines">
                {pred.analogs.map((a) => (
                  <li key={a.date + a.event}>
                    {a.event} <span className="small muted">({a.date}, {a.similarity}% similar)</span>{' '}
                    <span className={signClass(a.abnormal_20d)}>{pct(a.abnormal_20d)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {pred?.thesis && <><h4>Thesis</h4><p className="thesis-text small">{pred.thesis}</p></>}
          <p className="small muted">Why these tags: {event.reasoning}</p>
        </div>
      )}
    </article>
  )
}

export default function LiveFeed({ ticker }) {
  const [status, setStatus] = useState(null)
  const [events, setEvents] = useState([])
  const [card, setCard] = useState(null)
  const [showDismissed, setShowDismissed] = useState(false)
  const [category, setCategory] = useState('all')
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    Promise.all([getLiveStatus(), getLiveEvents(ticker, showDismissed), getLiveScorecard(ticker)])
      .then(([s, e, c]) => { setStatus(s); setEvents(e); setCard(c); setError(null) })
      .catch((err) => setError(err.message))
  }, [ticker, showDismissed])

  useEffect(() => { load() }, [load])

  // While a run is in progress (or after an error), check back every few seconds; otherwise every 5 minutes.
  useEffect(() => {
    const timer = setInterval(load, status?.running || error ? 3000 : 300000)
    return () => clearInterval(timer)
  }, [load, status?.running, error])

  const handleRun = () => runPipeline().then(load).catch((err) => setError(err.message))
  const handleStatus = (id, action) => setEventStatus(id, action).then(load).catch((err) => setError(err.message))

  if (!status) return error ? <p className="error">{error} Retrying…</p> : <p className="muted">Loading live events…</p>

  const categories = [...new Set(events.map((e) => e.category))].sort()
  const shown = events.filter((e) => category === 'all' || e.category === category)

  return (
    <section>
      {error && <p className="error">{error} Retrying…</p>}
      <StatusBar status={status} onRun={handleRun} />
      {card && <Scorecard card={card} ticker={ticker} />}

      <div className="toolbar">
        <h2 style={{ margin: 0, marginRight: 'auto' }}>Detected events</h2>
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="all">All categories</option>
          {categories.map((c) => <option key={c} value={c}>{label(c)}</option>)}
        </select>
        <label className="check">
          <input type="checkbox" checked={showDismissed} onChange={(e) => setShowDismissed(e.target.checked)} />
          Show dismissed
        </label>
      </div>

      {shown.length === 0 && (
        <p className="card muted">
          No events yet. The pipeline needs a story covered by at least 3 outlets before it counts as an event.
        </p>
      )}
      {shown.map((e) => <EventCard key={e.id} event={e} ticker={ticker} onStatus={handleStatus} />)}
    </section>
  )
}
