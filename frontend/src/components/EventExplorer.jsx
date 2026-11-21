// Browse every event in the database, filter them, and open any event's chart.

import { useEffect, useState } from 'react'
import { getEvents } from '../api'
import { label, pct, signClass } from '../theme'
import { ConfoundMarker } from './Confounds'
import EventChart from './EventChart'

export default function EventExplorer({ options, ticker }) {
  const [events, setEvents] = useState([])
  const [error, setError] = useState(null)
  const [category, setCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('date') // 'date' or 'abnormal_20d'
  const [cleanOnly, setCleanOnly] = useState(false) // hide events with confounds
  const [selectedDate, setSelectedDate] = useState(null)

  useEffect(() => {
    getEvents(ticker).then(setEvents).catch((err) => setError(err.message))
  }, [ticker])

  // Work out which rows to show. This runs on every redraw, which is fine for 71 rows.
  const shown = events
    .filter((e) => category === 'all' || e.category === category)
    .filter((e) => e.event.toLowerCase().includes(search.toLowerCase()))
    .filter((e) => !cleanOnly || e.confounds.length === 0)
    .toSorted((a, b) =>
      sortBy === 'date'
        ? b.date.localeCompare(a.date)
        : (b.abnormal_20d ?? -Infinity) - (a.abnormal_20d ?? -Infinity))

  if (error) return <p className="error">{error}</p>

  return (
    <section>
      <div className="card">
        <div className="toolbar">
          <input type="search" placeholder="Search events…" value={search}
            onChange={(e) => setSearch(e.target.value)} />
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="all">All categories</option>
            {options.categories.map((c) => <option key={c} value={c}>{label(c)}</option>)}
          </select>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            <option value="date">Newest first</option>
            <option value="abnormal_20d">Biggest 20-day gain first</option>
          </select>
          <label className="check">
            <input type="checkbox" checked={cleanOnly} onChange={(e) => setCleanOnly(e.target.checked)} />
            Clean events only
          </label>
          <span className="muted small">{shown.length} of {events.length} events</span>
        </div>
        <div className="table-wrap tall">
          <table>
            <thead>
              <tr>
                <th>Date</th><th>Event</th><th>Category</th><th>Region</th>
                <th className="num">1 day</th><th className="num">5 days</th><th className="num">20 days</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((e) => (
                <tr key={e.date + e.event} onClick={() => setSelectedDate(e.date)}
                  className={e.date === selectedDate ? 'selected' : ''}>
                  <td className="nowrap">{e.date}</td>
                  <td>{e.event}</td>
                  <td>{label(e.category)}</td>
                  <td>{label(e.region)}</td>
                  <td className={`num ${signClass(e.abnormal_1d)}`}>{pct(e.abnormal_1d)}</td>
                  <td className={`num ${signClass(e.abnormal_5d)}`}>{pct(e.abnormal_5d)}</td>
                  <td className={`num ${signClass(e.abnormal_20d)}`}>{pct(e.abnormal_20d)}</td>
                  <td className="nowrap"><ConfoundMarker confounds={e.confounds} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          {ticker} return minus its market's benchmark. Click a row to see its chart.
          ⚠ marks events where earnings, another event or market turmoil fell in the 20-day window (hover for details).
        </p>
      </div>

      {selectedDate && <EventChart key={selectedDate} date={selectedDate} highlight={ticker} />}
    </section>
  )
}
