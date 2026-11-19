// The analog engine: describe a new event, get similar past events and a thesis.

import { useEffect, useState } from 'react'
import { claudeThesis, findAnalogs, parseHeadline } from '../api'
import { label, pct, signClass } from '../theme'
import { ConfoundMarker } from './Confounds'
import EventChart from './EventChart'

// Type a headline and let Claude fill in the form. Calls onTags with the tags it chose.
function HeadlineBox({ onTags }) {
  const [headline, setHeadline] = useState('')
  const [status, setStatus] = useState(null) // {kind: 'busy' | 'done' | 'error', text}

  const handleSubmit = (e) => {
    e.preventDefault()
    setStatus({ kind: 'busy', text: 'Asking Claude to classify the headline…' })
    parseHeadline(headline)
      .then(({ reasoning, ...tags }) => {
        onTags(tags)
        setStatus({ kind: 'done', text: reasoning })
      })
      .catch((err) => setStatus({ kind: 'error', text: err.message }))
  }

  return (
    <form className="card headline" onSubmit={handleSubmit}>
      <h2>Start from a headline <span className="tag">uses Claude</span></h2>
      <div className="headline-row">
        <input type="text" value={headline} onChange={(e) => setHeadline(e.target.value)}
          placeholder="e.g. China announces naval blockade of Taiwan" minLength={10} />
        <button type="submit" disabled={status?.kind === 'busy' || headline.trim().length < 10}>
          Fill in tags
        </button>
      </div>
      {status && (
        <p className={status.kind === 'error' ? 'error small' : 'muted small'}>
          {status.kind === 'done' ? `Claude's reasoning: ${status.text} Check the tags below, then find analogs.` : status.text}
        </p>
      )}
    </form>
  )
}

const DEFAULT_EVENT = {
  category: 'war_outbreak',
  region: 'europe',
  us_involved: 'yes',
  severity: '3',
  surprise: 'yes',
}

// A small reusable dropdown. `choices` is a list of [value, text] pairs.
function Select({ name, value, choices, onChange }) {
  return (
    <label className="field">
      <span>{name}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {choices.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
      </select>
    </label>
  )
}

function StatTile({ title, value, note }) {
  return (
    <div className="tile">
      <div className="tile-title">{title}</div>
      <div className={`tile-value ${signClass(value)}`}>{typeof value === 'number' ? pct(value) : value}</div>
      {note && <div className="tile-note">{note}</div>}
    </div>
  )
}

export default function AnalogEngine({ options, ticker }) {
  const [form, setForm] = useState(DEFAULT_EVENT)
  const [submitted, setSubmitted] = useState(null) // the event we last searched for
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [selectedDate, setSelectedDate] = useState(null)
  const [aiThesis, setAiThesis] = useState(null) // {kind: 'busy' | 'done' | 'error', text}

  // Update one field of the form, keeping the others. "...form" copies the old values.
  const update = (field) => (value) => setForm({ ...form, [field]: value })

  const askClaude = () => {
    setAiThesis({ kind: 'busy', text: 'Claude is writing a thesis… (this can take up to a minute)' })
    claudeThesis({ ...submitted, ticker })
      .then((data) => setAiThesis({ kind: 'done', text: data.thesis }))
      .catch((err) => setAiThesis({ kind: 'error', text: err.message }))
  }

  // Run the search whenever a new event is submitted or the ticker changes.
  useEffect(() => {
    if (!submitted) return
    setLoading(true)
    setError(null)
    findAnalogs({ ...submitted, ticker })
      .then((data) => {
        setResult(data)
        setSelectedDate(data.analogs[0]?.date ?? null) // show the closest analog's chart first
        setAiThesis(null) // an old Claude thesis no longer matches the new results
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [submitted, ticker])

  const handleSubmit = (e) => {
    e.preventDefault() // stop the browser from reloading the page, its default for forms
    setSubmitted({ ...form })
  }

  const stats = result?.stats

  return (
    <section>
      <HeadlineBox onTags={(tags) => setForm(tags)} />

      <form className="card form" onSubmit={handleSubmit}>
        <h2>Describe a new event</h2>
        <div className="fields">
          <Select name="Category" value={form.category} onChange={update('category')}
            choices={options.categories.map((c) => [c, label(c)])} />
          <Select name="Region" value={form.region} onChange={update('region')}
            choices={options.regions.map((r) => [r, label(r)])} />
          <Select name="US involved" value={form.us_involved} onChange={update('us_involved')}
            choices={[['yes', 'Yes'], ['no', 'No']]} />
          <Select name="Severity" value={form.severity} onChange={update('severity')}
            choices={[['1', '1 – minor'], ['2', '2 – significant'], ['3', '3 – major']]} />
          <Select name="Surprise" value={form.surprise} onChange={update('surprise')}
            choices={[['yes', 'Yes'], ['no', 'No (expected)']]} />
        </div>
        <button type="submit" disabled={loading}>{loading ? 'Searching…' : 'Find analogs'}</button>
      </form>

      {error && <p className="error">{error}</p>}

      {result && result.analogs.length === 0 && (
        <p className="card muted">No comparable past events. Add more events of this type to the database.</p>
      )}

      {result && result.analogs.length > 0 && (
        <>
          <div className="card thesis">
            <div className="thesis-head">
              <h2>Thesis for {ticker}</h2>
              <span className={`badge badge-${result.confidence.level}`}>
                {label(result.confidence.level)} confidence
              </span>
            </div>
            <p className="thesis-text">{result.thesis}</p>
            <div className="thesis-actions">
              <button type="button" className="secondary" onClick={askClaude}
                disabled={aiThesis?.kind === 'busy'}>
                Write it up with Claude
              </button>
              <span className="small muted">Turns these numbers into a fuller written argument.</span>
            </div>
            {aiThesis && (
              <div className={`ai-thesis ${aiThesis.kind}`}>
                {aiThesis.kind === 'done' && <div className="tag">Written by Claude from the numbers above</div>}
                <p className={aiThesis.kind === 'error' ? 'error' : 'thesis-text'}>{aiThesis.text}</p>
              </div>
            )}
          </div>

          <div className="tiles">
            <StatTile title="Median day 1" value={stats['1d'].median} note="vs the market" />
            <StatTile title="Median 5 days" value={stats['5d'].median} note="vs the market" />
            <StatTile title="Median 20 days" value={stats['20d'].median}
              note={`range ${pct(stats['20d'].low)} to ${pct(stats['20d'].high)}`} />
            <StatTile title="Beat the market" value={`${stats['20d'].beat_market} of ${result.analogs.length}`}
              note="over 20 days" />
          </div>

          <div className="card">
            <h2>Closest past events</h2>
            <p className="muted small">Click a row to see its chart.</p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Similarity</th><th>Date</th><th>Event</th><th>Category</th>
                    <th className="num">1 day</th><th className="num">5 days</th><th className="num">20 days</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {result.analogs.map((a) => (
                    <tr key={a.date} onClick={() => setSelectedDate(a.date)}
                      className={a.date === selectedDate ? 'selected' : ''}>
                      <td>
                        <div className="sim">
                          <div className="sim-bar" style={{ width: `${a.similarity}%` }} />
                          <span>{a.similarity}%</span>
                        </div>
                      </td>
                      <td className="nowrap">{a.date}</td>
                      <td>{a.event}</td>
                      <td>{label(a.category)}</td>
                      <td className={`num ${signClass(a.abnormal_1d)}`}>{pct(a.abnormal_1d)}</td>
                      <td className={`num ${signClass(a.abnormal_5d)}`}>{pct(a.abnormal_5d)}</td>
                      <td className={`num ${signClass(a.abnormal_20d)}`}>{pct(a.abnormal_20d)}</td>
                      <td className="nowrap"><ConfoundMarker confounds={a.confounds} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {selectedDate && <EventChart key={selectedDate} date={selectedDate} highlight={ticker} />}
        </>
      )}
    </section>
  )
}
