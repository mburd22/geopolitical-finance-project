// How good is the analog engine? Backtest results against simple baselines.

import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { getBacktest } from '../api'
import RunupSection from './RunupSection'
import { label, pct, signClass, useChartTheme, useNarrow } from '../theme'

function Tile({ title, value, note, emphasis }) {
  return (
    <div className="tile">
      <div className="tile-title">{title}</div>
      <div className={`tile-value ${emphasis ? 'accent' : ''}`}>{value}</div>
      {note && <div className="tile-note">{note}</div>}
    </div>
  )
}

export default function TrackRecord({ ticker }) {
  const theme = useChartTheme()
  const narrow = useNarrow()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all') // all | hits | misses | none

  useEffect(() => {
    getBacktest(ticker).then(setData).catch((err) => setError(err.message))
  }, [ticker])

  if (error) return <p className="error">{error}</p>
  if (!data || data.predictions[0] === undefined) return <p className="muted">Running the backtest…</p>

  const loo = data.summary.leave_one_out
  const past = data.summary.past_only
  const edge = loo.hit_rate - loo.always_up_hit_rate
  const verdict = edge >= 5 ? 'beats' : edge > -2 ? 'roughly matches' : 'trails'

  const bars = [
    { name: 'Analog engine', value: loo.hit_rate, engine: true },
    { name: 'Engine, past only', value: past.hit_rate, engine: true },
    { name: 'Always beats market', value: loo.always_up_hit_rate },
    { name: 'Same-category average', value: loo.category_hit_rate },
  ]

  const hits = data.predictions.filter((p) => p.hit === true)
  const misses = data.predictions.filter((p) => p.hit === false)
  const tooltipStyle = {
    background: theme.surface, border: `1px solid ${theme.grid}`, borderRadius: 8, maxWidth: 'min(260px, 65vw)',
  }
  const shown = data.predictions.filter((p) =>
    filter === 'all' || (filter === 'hits' && p.hit === true) ||
    (filter === 'misses' && p.hit === false) || (filter === 'none' && p.hit === null))

  return (
    <section>
      <div className="card">
        <h2>Does the analog engine work?</h2>
        <p className="muted">
          Each past event was hidden in turn and predicted from the others. For {ticker}, the engine {verdict} the
          simplest possible guess, that defense stocks beat the market after any event.
          Small sample ({data.predictions.length} events): treat differences of a few points as noise.
        </p>
      </div>

      <div className="tiles">
        <Tile title="Engine hit rate" value={`${loo.hit_rate.toFixed(0)}%`} emphasis
          note={`direction right on ${loo.calls} calls`} />
        <Tile title="Past-only hit rate" value={`${past.hit_rate.toFixed(0)}%`}
          note="only using earlier events (the honest test)" />
        <Tile title="Baseline: always up" value={`${loo.always_up_hit_rate.toFixed(0)}%`}
          note="same events, no engine" />
        <Tile title="Typical miss" value={`${loo.mae.toFixed(1)} pts`}
          note={`vs ${loo.category_mae.toFixed(1)} for the category average`} />
      </div>

      <div className="card">
        <h2>Engine vs simple baselines</h2>
        <p className="muted small">Share of directional calls that were right. 50% is a coin flip.</p>
        <div className="chart">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={bars} layout="vertical" margin={{ top: 22, right: 48, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={theme.grid} horizontal={false} />
              <XAxis type="number" domain={[0, 100]} unit="%" stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }} />
              <YAxis type="category" dataKey="name" width={narrow ? 110 : 160} stroke={theme.axis}
                tick={{ fill: theme.text, fontSize: narrow ? 11 : 12 }} />
              <ReferenceLine x={50} stroke={theme.muted} strokeDasharray="4 4"
                label={{ value: 'coin flip', position: 'top', fill: theme.muted, fontSize: 11 }} />
              <Tooltip cursor={{ fill: theme.grid, opacity: 0.4 }} contentStyle={tooltipStyle}
                itemStyle={{ color: theme.text }} formatter={(v) => [`${v}%`, 'Right']} />
              <Bar dataKey="value" radius={4} isAnimationActive={false}
                label={{ position: 'right', formatter: (v) => `${v}%`, fill: theme.text, fontSize: 12 }}>
                {bars.map((b) => <Cell key={b.name} fill={b.engine ? theme.series[0] : theme.muted} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h2>Predicted vs actual</h2>
        <p className="muted small">
          Each dot is one event: what its analogs predicted for {ticker}'s 20-day move vs the market, and what
          actually happened. Dots in the top-right and bottom-left quarters got the direction right.
        </p>
        <div className="chart">
          <ResponsiveContainer width="100%" height={340}>
            <ScatterChart margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
              <CartesianGrid stroke={theme.grid} />
              <XAxis type="number" dataKey="predicted_median" name="Predicted" unit="%" stroke={theme.axis}
                tick={{ fill: theme.muted, fontSize: 12 }}
                label={{ value: 'Predicted (median of analogs)', position: 'insideBottom', offset: -12, fill: theme.muted, fontSize: 12 }} />
              <YAxis type="number" dataKey="actual_20d" name="Actual" unit="%" width={48} stroke={theme.axis}
                tick={{ fill: theme.muted, fontSize: 12 }} />
              <ZAxis range={[60, 60]} />
              <ReferenceLine x={0} stroke={theme.axis} />
              <ReferenceLine y={0} stroke={theme.axis} />
              <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: theme.text }}
                content={({ payload }) => {
                  const p = payload?.[0]?.payload
                  if (!p) return null
                  return (
                    <div style={{ ...tooltipStyle, padding: 10, color: theme.text, fontSize: 13 }}>
                      <strong>{p.event}</strong> ({p.date})<br />
                      Predicted {pct(p.predicted_median)} · actual {pct(p.actual_20d)}<br />
                      {p.hit === null ? 'No call (analogs split)' : p.hit ? '✓ direction right' : '✗ direction wrong'}
                    </div>
                  )
                }} />
              <Legend wrapperStyle={{ fontSize: 13, paddingTop: 12 }} />
              <Scatter name="✓ Right" data={hits} fill={theme.series[0]} shape="circle" legendType="circle"
                isAnimationActive={false} />
              <Scatter name="✗ Wrong" data={misses} fill={theme.negative} shape="cross" legendType="cross"
                isAnimationActive={false} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0, marginRight: 'auto' }}>Every prediction</h2>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All events</option>
            <option value="hits">Right</option>
            <option value="misses">Wrong</option>
            <option value="none">No call</option>
          </select>
        </div>
        <div className="table-wrap tall">
          <table>
            <thead>
              <tr>
                <th>Date</th><th>Event</th><th>Category</th>
                <th className="num">Predicted</th><th className="num">Actual</th><th>Call</th><th>Result</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => (
                <tr key={p.date + p.event} className="static">
                  <td className="nowrap">{p.date}</td>
                  <td>{p.event}</td>
                  <td>{label(p.category)}</td>
                  <td className={`num ${signClass(p.predicted_median)}`}>{pct(p.predicted_median)}</td>
                  <td className={`num ${signClass(p.actual_20d)}`}>{pct(p.actual_20d)}</td>
                  <td>{p.direction === 'flat' ? 'No call' : p.direction === 'up' ? 'Beat market' : 'Lag market'}</td>
                  <td className="nowrap">{p.hit === null ? '—' : p.hit ? '✓ Right' : '✗ Wrong'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Leave-one-out predictions shown. Similarity weights: {Object.entries(data.weights)
            .map(([k, v]) => `${label(k)} ${v}`).join(', ')}.
        </p>
      </div>

      <RunupSection ticker={ticker} />
    </section>
  )
}
