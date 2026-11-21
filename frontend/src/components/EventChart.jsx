// A line chart of how each defense stock moved vs the market around one event.
// "Components" are React's building blocks: functions that return what to show on screen.
// The things passed in (here: date and highlight) are called "props".

import { useEffect, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { getEventDetail } from '../api'
import { label, pct, shortTicker, tickerColor, useChartTheme } from '../theme'
import { ConfoundList } from './Confounds'

export default function EventChart({ date, highlight = 'ITA' }) {
  const theme = useChartTheme()
  // useState holds a value that, when changed, makes React redraw the component.
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)

  // useEffect runs code after drawing, here: fetch the event's data.
  // Parents give this component key={date}, so picking a new event creates a fresh
  // EventChart with empty state rather than reusing this one.
  useEffect(() => {
    let cancelled = false // ignore a slow answer if the component has already gone away
    getEventDetail(date, highlight)
      .then((data) => !cancelled && setDetail(data))
      .catch((err) => !cancelled && setError(err.message))
    return () => { cancelled = true }
  }, [date, highlight])

  if (error) return <p className="error">{error}</p>
  if (!detail) return <p className="muted">Loading chart…</p>

  const { event, series, confounds, benchmark, benchmark_name: benchmarkName } = detail
  const tickers = Object.keys(series[0]).filter((key) => key !== 'day')

  return (
    <div className="card">
      <h3>{event.event}</h3>
      <p className="muted small">
        {event.date} · {label(event.category)} · {label(event.region)} · severity {event.severity}
        {event.us_involved === 'yes' ? ' · US involved' : ''}
      </p>
      <div className="chart">
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={series} margin={{ top: 20, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke={theme.grid} vertical={false} />
            <XAxis dataKey="day" stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }}
              label={{ value: 'Trading days from event', position: 'insideBottom', offset: -4, fill: theme.muted, fontSize: 12 }} />
            <YAxis stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }} unit="%" width={48} />
            <ReferenceLine y={0} stroke={theme.axis} />
            <ReferenceLine x={0} stroke={theme.muted} strokeDasharray="4 4"
              label={{ value: 'Day 0', position: 'top', fill: theme.muted, fontSize: 11 }} />
            <Tooltip
              formatter={(value, name) => [pct(value), name]}
              labelFormatter={(day) => `Day ${day}`}
              contentStyle={{ background: theme.surface, border: `1px solid ${theme.grid}`, borderRadius: 8, maxWidth: 'min(240px, 65vw)' }}
              itemStyle={{ color: theme.text }}
              itemSorter={(item) => -item.value} // highest value at the top
            />
            <Legend wrapperStyle={{ fontSize: 13, paddingTop: 8 }} />
            {tickers.map((ticker) => (
              <Line key={ticker} dataKey={ticker} name={shortTicker(ticker)} type="monotone" dot={false}
                stroke={tickerColor(theme, ticker)}
                strokeWidth={ticker === highlight ? 3 : 1.5}
                strokeOpacity={ticker === highlight ? 1 : 0.75}
                isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small">
        Lines show each stock's return minus the {benchmarkName} ({benchmark}), starting from the close before the news.
      </p>
      <ConfoundList confounds={confounds} />
    </div>
  )
}
