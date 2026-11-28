// The top-level component: header, ticker picker, tabs, and whichever page is open.

import { Suspense, lazy, useEffect, useState } from 'react'
import { getOptions } from './api'
import LiveFeed from './components/LiveFeed'

// The other tabs load only when first opened. lazy() fetches a tab's code (and the charting
// library, Recharts, which most of them need) on demand, so the first screen appears faster.
// Vite splits each import() into its own file when it builds the site.
const AnalogEngine = lazy(() => import('./components/AnalogEngine'))
const CategoryView = lazy(() => import('./components/CategoryView'))
const EventExplorer = lazy(() => import('./components/EventExplorer'))
const TrackRecord = lazy(() => import('./components/TrackRecord'))

const TABS = [
  { id: 'live', name: 'Live' },
  { id: 'analogs', name: 'Analog engine' },
  { id: 'events', name: 'Event explorer' },
  { id: 'categories', name: 'By event type' },
  { id: 'track', name: 'Track record' },
]

export default function App() {
  const [options, setOptions] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('live')
  const [ticker, setTicker] = useState('ITA')

  // Fetch the dropdown options once, when the page first loads (the empty [] means "only once").
  useEffect(() => {
    getOptions().then(setOptions).catch((err) => setError(err.message))
  }, [])

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>Defense Stock Event Tracker</h1>
          <p className="muted">
            How US and European defense stocks react to geopolitical events, measured against their own market.
            {options && ` Prices through ${options.price_data_ends}.`}
          </p>
        </div>
        {options && (
          <label className="field ticker">
            <span>Stock</span>
            <select value={ticker} onChange={(e) => setTicker(e.target.value)}>
              {Object.entries(options.markets).map(([market, m]) => (
                <optgroup key={market} label={`${market === 'US' ? 'United States' : 'Europe'} (vs ${m.benchmark_name})`}>
                  {m.tickers.map((t) => <option key={t} value={t}>{t} · {options.ticker_names[t]}</option>)}
                </optgroup>
              ))}
            </select>
          </label>
        )}
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} type="button" className={tab === t.id ? 'tab active' : 'tab'}
            onClick={() => setTab(t.id)}>
            {t.name}
          </button>
        ))}
      </nav>

      {error && <p className="error">{error}</p>}
      {!options && !error && <p className="muted">Connecting to the back end…</p>}

      {/* && means "only show the right side if the left side is true".
          Suspense shows the fallback while a lazily loaded tab's code is still downloading. */}
      <Suspense fallback={<p className="muted">Loading…</p>}>
        {options && tab === 'live' && <LiveFeed ticker={ticker} />}
        {options && tab === 'analogs' && <AnalogEngine options={options} ticker={ticker} />}
        {options && tab === 'events' && <EventExplorer options={options} ticker={ticker} />}
        {options && tab === 'categories' && <CategoryView ticker={ticker} options={options} />}
        {options && tab === 'track' && <TrackRecord ticker={ticker} />}
      </Suspense>

      <footer className="muted small">
        Historical base rates from a small set of events, for learning and research. Not investment advice.
      </footer>
    </div>
  )
}
