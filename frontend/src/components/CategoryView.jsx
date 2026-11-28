// Which kinds of events help defense stocks? Averages by event category.

import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, ErrorBar, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis, useXAxisScale,
} from 'recharts'
import { getCategories, getCategoryTest } from '../api'
import { categoryColor, label, pct, signClass, useChartTheme, useNarrow } from '../theme'

const MAX_LINES = 4 // more lines than this gets too hard to read

// The value written beside each bar. It always goes to the right of the bar's right end
// (for a negative bar that's the zero line) and of its error bar, so it never collides with
// the category names or the whisker. `high` is the top of the bar's 90% range, if it has one.
function BarValue({ x, y, width, height, value, color, high }) {
  // useXAxisScale turns a value on the x-axis (like +4.2%) into a position in pixels.
  const toPixels = useXAxisScale()
  // A negative bar has a negative width, so its right end is x, not x + width.
  const barEnd = Math.max(x, x + width)
  const rightEnd = toPixels ? Math.max(barEnd, toPixels(Math.max(0, value, high ?? value))) : barEnd
  return (
    <text x={rightEnd + 6} y={y + height / 2} dy="0.35em" fill={color} fontSize={12}>
      {pct(value)}
    </text>
  )
}

// Recharts draws an error bar from distances below and above the value: [down, up].
const errorSpan = (value, ci) => (ci == null || value == null ? null : [value - ci[0], ci[1] - value])

// "−1.2% to +5.0%": a 90% range written out for tooltips and tables.
const rangeText = (ci) => (ci == null ? 'n/a' : `${pct(ci[0])} to ${pct(ci[1])}`)

// Category names on the axis carry their event count, so every average shows its sample size.
const withCount = (counts) => (category) => `${label(category)} (${counts[category]})`

const RANGE_NOTE = 'Thin lines show 90% ranges: where the true average plausibly sits, given how few events ' +
  'there are (bootstrap). Where a range crosses zero, the sign of the average could be luck. ' +
  'Numbers in brackets are events.'

// US vs Europe: each sector basket's average 20-day result by event type, side by side.
function MarketComparison({ options }) {
  const theme = useChartTheme()
  const narrow = useNarrow()
  const [data, setData] = useState(null)
  const [us, eu] = options.baskets // ['ITA', 'EUDEF']

  useEffect(() => {
    Promise.all([getCategories(us), getCategories(eu)]).then(([usRows, euRows]) => {
      const euBy = Object.fromEntries(euRows.map((r) => [r.category, r]))
      setData(usRows
        .map((r) => {
          const e = euBy[r.category]
          return {
            category: r.category, events: r.events,
            us: r.avg_abnormal_20d, usCi: r.ci_20d, usErr: errorSpan(r.avg_abnormal_20d, r.ci_20d),
            eu: e?.avg_abnormal_20d, euCi: e?.ci_20d, euErr: errorSpan(e?.avg_abnormal_20d, e?.ci_20d),
          }
        })
        .sort((a, b) => b.eu - a.eu))
    })
  }, [us, eu])

  if (!data) return null
  const counts = Object.fromEntries(data.map((d) => [d.category, d.events]))
  const usLabel = `US (${us} vs ${options.markets.US.benchmark_name})`
  const euLabel = `Europe (${eu} vs ${options.markets.EU.benchmark_name})`
  return (
    <div className="card">
      <h2>US vs Europe</h2>
      <p className="muted small">
        Average 20-day return vs each market's own benchmark, by event type. {eu} is an equal-weighted basket of
        Rheinmetall, BAE, Thales, Saab and Leonardo, in euros.
      </p>
      <div className="chart">
        <ResponsiveContainer width="100%" height={460}>
          <BarChart data={data} layout="vertical" margin={{ top: 8, right: 44, bottom: 8, left: 0 }} barGap={2}>
            <CartesianGrid stroke={theme.grid} horizontal={false} />
            <XAxis type="number" unit="%" stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }}
              domain={[(min) => Math.floor(Math.min(min, 0)), (max) => Math.ceil(max)]} />
            <YAxis type="category" dataKey="category" tickFormatter={withCount(counts)} width={narrow ? 104 : 156}
              stroke={theme.axis} tick={{ fill: theme.text, fontSize: narrow ? 11 : 12 }} />
            <ReferenceLine x={0} stroke={theme.axis} />
            <Tooltip cursor={{ fill: theme.grid, opacity: 0.4 }}
              contentStyle={{ background: theme.surface, border: `1px solid ${theme.grid}`, borderRadius: 8 }}
              itemStyle={{ color: theme.text }} labelFormatter={withCount(counts)}
              formatter={(value, name, item) => [
                `${pct(value)} (90% range ${rangeText(item.dataKey === 'us' ? item.payload.usCi : item.payload.euCi)})`,
                name,
              ]} />
            <Legend wrapperStyle={{ fontSize: 13, paddingTop: 8 }} />
            <Bar dataKey="us" name={usLabel} fill={theme.series[0]} radius={3} isAnimationActive={false} minPointSize={2}
              label={(props) => <BarValue {...props} color={theme.text} high={data[props.index]?.usCi?.[1]} />}>
              <ErrorBar dataKey="usErr" direction="x" isAnimationActive={false} width={4} stroke={theme.text} strokeWidth={1} />
            </Bar>
            <Bar dataKey="eu" name={euLabel} fill={theme.series[1]} radius={3} isAnimationActive={false} minPointSize={2}
              label={(props) => <BarValue {...props} color={theme.text} high={data[props.index]?.euCi?.[1]} />}>
              <ErrorBar dataKey="euErr" direction="x" isAnimationActive={false} width={4} stroke={theme.text} strokeWidth={1} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small">
        European defense stocks have also risen far more than their market since 2022, which lifts every category.
        Compare the gap between categories, not just the levels. {RANGE_NOTE}
      </p>
    </div>
  )
}

// With nine event types, some average looks big by luck alone. This asks the server how often
// shuffling the event types at random spreads the averages out as much as the real ones do.
const share = (p) => `${(p * 100).toFixed(p < 0.1 ? 1 : 0)}%`

// The three horizons the bar chart can show, and which one has the strongest evidence that
// event type matters (the smallest permutation-test share). The chart opens on that one.
const HORIZONS = { '1d': 'day-1', '5d': '5-day', '20d': '20-day' }
const bestHorizon = (test) =>
  test ? Object.keys(HORIZONS).reduce((best, w) => (test[`p_${w}`] < test[`p_${best}`] ? w : best), '20d') : '20d'

function EventTypeTest({ test }) {
  if (!test) return null
  const verdict = test.p_20d < 0.05
    ? 'Over 20 days, event type does seem to matter for this stock.'
    : test.p_20d < 0.1
      ? 'Over 20 days that is borderline: event type may matter, but luck is a fair explanation.'
      : 'Over 20 days, the differences between event types are within what luck produces. Treat the ranking below with care.'
  return (
    <div className="card">
      <h2>Does event type matter at all?</h2>
      <p className="muted small">
        If the event types were shuffled at random across {test.ticker}'s {test.events} events, how often would their
        averages spread out as much as the real ones? Day 1: <strong>{share(test.p_1d)}</strong> · 5 days:{' '}
        <strong>{share(test.p_5d)}</strong> · 20 days: <strong>{share(test.p_20d)}</strong> (a permutation test).
        Under 5% means the type of event really goes with how the stock moved. {verdict}
      </p>
    </div>
  )
}

export default function CategoryView({ ticker, options }) {
  const theme = useChartTheme()
  const narrow = useNarrow()
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)
  const [picked, setPicked] = useState(['election', 'war_outbreak', 'de_escalation'])
  const [test, setTest] = useState(null) // permutation test for this ticker
  const [chosen, setChosen] = useState(null) // horizon the user picked; null = the best-supported one

  useEffect(() => {
    getCategories(ticker).then(setRows).catch((err) => setError(err.message))
    getCategoryTest(ticker).then(setTest).catch(() => setTest(null))
  }, [ticker])

  const toggle = (category) => {
    if (picked.includes(category)) setPicked(picked.filter((c) => c !== category))
    else if (picked.length < MAX_LINES) setPicked([...picked, category])
  }

  if (error) return <p className="error">{error}</p>
  if (rows.length === 0) return <p className="muted">Loading…</p>

  // maxWidth + whiteSpace let long tooltips wrap instead of running off a phone screen.
  const tooltipStyle = {
    background: theme.surface, border: `1px solid ${theme.grid}`, borderRadius: 8,
    maxWidth: 'min(240px, 65vw)', whiteSpace: 'normal',
  }
  const tooltipItem = { color: theme.text }

  // Reshape the paths into one object per day: [{day: -5, election: 0.7, war_outbreak: 0.6}, ...]
  const pickedRows = rows.filter((r) => picked.includes(r.category))
  const counts = Object.fromEntries(rows.map((r) => [r.category, r.events]))
  const currentTest = test?.ticker === ticker ? test : null
  const horizon = chosen ?? bestHorizon(currentTest)
  const valueKey = `avg_abnormal_${horizon}`
  const ciKey = `ci_${horizon}`
  const barData = rows
    .map((r) => ({ ...r, err: errorSpan(r[valueKey], r[ciKey]) }))
    .sort((a, b) => (b[valueKey] ?? 0) - (a[valueKey] ?? 0))
  const pShown = currentTest?.[`p_${horizon}`]
  const days = rows[0].path.map((p) => p.day)
  const lineData = days.map((day, i) => ({
    day,
    ...Object.fromEntries(pickedRows.map((r) => [r.category, r.path[i]?.value])),
  }))

  return (
    <section>
      <MarketComparison options={options} />
      <EventTypeTest test={currentTest} />
      <div className="card">
        <h2>Average {HORIZONS[horizon]} result by event type</h2>
        <div className="chips" role="group" aria-label="Horizon">
          {Object.entries(HORIZONS).map(([w, name]) => {
            const p = currentTest?.[`p_${w}`]
            return (
              <button key={w} type="button" className={`chip ${w === horizon ? 'on' : ''}`}
                onClick={() => setChosen(w)} aria-pressed={w === horizon}>
                {name}
                {p != null && <span className="small muted"> · {p < 0.05 ? 'type matters' : 'could be luck'}</span>}
              </button>
            )
          })}
        </div>
        <p className="muted small">
          {ticker} return minus the market, averaged over every event in each category.{' '}
          {chosen === null && currentTest && 'Showing the horizon where event type matters most for this stock. '}
          {pShown != null && (pShown < 0.05
            ? `Here event type really goes with the move (permutation test ${share(pShown)}).`
            : `Here the gaps between event types are within what luck produces (permutation test ${share(pShown)}), so read the ranking with care.`)}{' '}
          {RANGE_NOTE}
        </p>
        <div className="chart">
          <ResponsiveContainer width="100%" height={360}>
            <BarChart data={barData} layout="vertical"
              margin={{ top: 8, right: 44, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={theme.grid} horizontal={false} />
              <XAxis type="number" stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }} unit="%"
                domain={[(min) => Math.floor(Math.min(min, 0)), (max) => Math.ceil(max)]} />
              <YAxis type="category" dataKey="category" tickFormatter={withCount(counts)} width={narrow ? 104 : 156}
                stroke={theme.axis} tick={{ fill: theme.text, fontSize: narrow ? 11 : 12 }} />
              <ReferenceLine x={0} stroke={theme.axis} />
              <Tooltip
                cursor={{ fill: theme.grid, opacity: 0.4 }}
                contentStyle={tooltipStyle}
                itemStyle={tooltipItem}
                labelFormatter={withCount(counts)}
                formatter={(value, _name, item) => [
                  `${pct(value)}, 90% range ${rangeText(item.payload[ciKey])}.` +
                  (horizon === '20d'
                    ? ` Beat the market in ${item.payload.beat_market_20d_pct.toFixed(0)}% of ${item.payload.events} events.`
                    : ''),
                  `${HORIZONS[horizon]} avg`,
                ]}
              />
              <Bar dataKey={valueKey} radius={4} isAnimationActive={false} minPointSize={2}
                label={(props) => <BarValue {...props} color={theme.text} high={barData[props.index]?.[ciKey]?.[1]} />}>
                {barData.map((r) => (
                  <Cell key={r.category} fill={r[valueKey] >= 0 ? theme.positive : theme.negative} />
                ))}
                <ErrorBar dataKey="err" direction="x" isAnimationActive={false} width={5} stroke={theme.text} strokeWidth={1.2} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h2>How the reaction unfolds</h2>
        <p className="muted small">Pick up to {MAX_LINES} categories to compare their average path, day by day.</p>
        <div className="chips">
          {rows.map((r) => {
            const on = picked.includes(r.category)
            return (
              <button key={r.category} type="button" onClick={() => toggle(r.category)}
                className={`chip ${on ? 'on' : ''}`}
                disabled={!on && picked.length >= MAX_LINES}>
                <span className="swatch" style={{ background: categoryColor(theme, r.category) }} />
                {label(r.category)} ({r.events})
              </button>
            )
          })}
        </div>
        <div className="chart">
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={lineData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={theme.grid} vertical={false} />
              <XAxis dataKey="day" stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }} />
              <YAxis stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }} unit="%" width={48} />
              <ReferenceLine y={0} stroke={theme.axis} />
              <ReferenceLine x={0} stroke={theme.muted} strokeDasharray="4 4" />
              <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItem} labelFormatter={(d) => `Day ${d}`}
                formatter={(value, name) => [pct(value), label(name)]} />
              <Legend formatter={withCount(counts)} wrapperStyle={{ fontSize: 13, paddingTop: 8 }} />
              {pickedRows.map((r) => (
                <Line key={r.category} dataKey={r.category} type="monotone" dot={false}
                  stroke={categoryColor(theme, r.category)} strokeWidth={2} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h2>The numbers</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Category</th><th className="num">Events</th><th className="num">Day 1</th>
                <th className="num">5 days</th><th className="num">20 days</th>
                <th className="num">20 days, 90% range</th><th className="num">Beat market</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.category}>
                  <td>{label(r.category)}</td>
                  <td className="num">{r.events}</td>
                  <td className={`num ${signClass(r.avg_abnormal_1d)}`}>{pct(r.avg_abnormal_1d)}</td>
                  <td className={`num ${signClass(r.avg_abnormal_5d)}`}>{pct(r.avg_abnormal_5d)}</td>
                  <td className={`num ${signClass(r.avg_abnormal_20d)}`}>{pct(r.avg_abnormal_20d)}</td>
                  <td className="num nowrap muted">{rangeText(r.ci_20d)}</td>
                  <td className="num">{r.beat_market_20d_pct.toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
