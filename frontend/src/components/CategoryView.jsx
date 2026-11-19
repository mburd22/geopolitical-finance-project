// Which kinds of events help defense stocks? Averages by event category.

import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { getCategories } from '../api'
import { categoryColor, label, pct, signClass, useChartTheme, useNarrow } from '../theme'

const MAX_LINES = 4 // more lines than this gets too hard to read

// The value written beside each bar. It always goes to the right of the bar's right end
// (for a negative bar that's the zero line), so it never collides with the category names.
function BarValue({ x, y, width, height, value, color }) {
  // A negative bar has a negative width, so its right end is x, not x + width.
  const rightEnd = Math.max(x, x + width)
  return (
    <text x={rightEnd + 6} y={y + height / 2} dy="0.35em" fill={color} fontSize={12}>
      {pct(value)}
    </text>
  )
}

export default function CategoryView({ ticker }) {
  const theme = useChartTheme()
  const narrow = useNarrow()
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)
  const [picked, setPicked] = useState(['election', 'war_outbreak', 'de_escalation'])

  useEffect(() => {
    getCategories(ticker).then(setRows).catch((err) => setError(err.message))
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
  const days = rows[0].path.map((p) => p.day)
  const lineData = days.map((day, i) => ({
    day,
    ...Object.fromEntries(pickedRows.map((r) => [r.category, r.path[i]?.value])),
  }))

  return (
    <section>
      <div className="card">
        <h2>Average 20-day result by event type</h2>
        <p className="muted small">{ticker} return minus the market, averaged over every event in each category.</p>
        <div className="chart">
          <ResponsiveContainer width="100%" height={360}>
            <BarChart data={rows} layout="vertical"
              margin={{ top: 8, right: 44, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={theme.grid} horizontal={false} />
              <XAxis type="number" stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }} unit="%"
                domain={[(min) => Math.floor(Math.min(min, 0)), (max) => Math.ceil(max)]} />
              <YAxis type="category" dataKey="category" tickFormatter={label} width={narrow ? 92 : 120}
                stroke={theme.axis} tick={{ fill: theme.text, fontSize: narrow ? 11 : 12 }} />
              <ReferenceLine x={0} stroke={theme.axis} />
              <Tooltip
                cursor={{ fill: theme.grid, opacity: 0.4 }}
                contentStyle={tooltipStyle}
                itemStyle={tooltipItem}
                labelFormatter={label}
                formatter={(value, _name, item) => [
                  `${pct(value)} (beat market in ${item.payload.beat_market_20d_pct.toFixed(0)}% of ${item.payload.events})`,
                  '20-day avg',
                ]}
              />
              <Bar dataKey="avg_abnormal_20d" radius={4} isAnimationActive={false}
                label={(props) => <BarValue {...props} color={theme.text} />}>
                {rows.map((r) => (
                  <Cell key={r.category} fill={r.avg_abnormal_20d >= 0 ? theme.positive : theme.negative} />
                ))}
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
                {label(r.category)}
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
              <Legend formatter={label} wrapperStyle={{ fontSize: 13, paddingTop: 8 }} />
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
                <th className="num">5 days</th><th className="num">20 days</th><th className="num">Beat market</th>
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
