// How good is the analog engine? Backtest results against simple baselines.

import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, ErrorBar, Legend, ReferenceLine, ResponsiveContainer,
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

// "45–62%": a 90% bootstrap range for a hit rate.
const range = (ci) => (ci ? `${ci[0].toFixed(0)}–${ci[1].toFixed(0)}%` : 'n/a')
// Recharts draws an error bar from distances below and above the value: [down, up].
const errorSpan = (value, ci) => (ci && value != null ? [value - ci[0], ci[1] - value] : null)
// "+2" / "−15": a signed number of percentage points.
const points = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(0)}`

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

  // The edge's range is worked out event by event (engine and baseline on the same events),
  // so it's narrower than the two separate ranges would suggest.
  const [edgeLow, edgeHigh] = loo.edge_ci ?? [edge, edge]
  const edgeSure = edgeLow > 0 || edgeHigh < 0

  const bars = [
    { name: 'Analog engine', value: loo.hit_rate, err: errorSpan(loo.hit_rate, loo.hit_rate_ci), engine: true },
    { name: 'Engine, past only', value: past.hit_rate, err: errorSpan(past.hit_rate, past.hit_rate_ci), engine: true },
    { name: 'Always beats market', value: loo.always_up_hit_rate, err: errorSpan(loo.always_up_hit_rate, loo.always_up_ci) },
    { name: 'Same-category average', value: loo.category_hit_rate, err: null },
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
          Small sample ({data.predictions.length} events): the engine minus the baseline is{' '}
          <strong>{points(edge)} points</strong>, with a 90% range of {points(edgeLow)} to {points(edgeHigh)}.{' '}
          {edgeSure
            ? 'That range does not cross zero, so the gap is probably real for this stock.'
            : 'That range crosses zero, so the gap could easily be luck.'}
        </p>
      </div>

      <div className="tiles">
        <Tile title="Engine hit rate" value={`${loo.hit_rate.toFixed(0)}%`} emphasis
          note={`${loo.calls} calls · 90% range ${range(loo.hit_rate_ci)}`} />
        <Tile title="Past-only hit rate" value={`${past.hit_rate.toFixed(0)}%`}
          note={`only earlier events (the honest test) · ${past.calls} calls · ${range(past.hit_rate_ci)}`} />
        <Tile title="Baseline: always up" value={`${loo.always_up_hit_rate.toFixed(0)}%`}
          note={`same ${loo.calls} events, no engine · ${range(loo.always_up_ci)}`} />
        <Tile title="Typical miss" value={`${loo.mae.toFixed(1)} pts`}
          note={`vs ${loo.category_mae.toFixed(1)} for the category average`} />
      </div>

      <div className="card">
        <h2>Engine vs simple baselines</h2>
        <p className="muted small">
          Share of directional calls that were right ({loo.calls} calls). 50% is a coin flip. Thin lines show 90%
          ranges (bootstrap): overlapping ranges mean the difference may be luck.
        </p>
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
                itemStyle={{ color: theme.text }}
                formatter={(v, _name, item) => [
                  item.payload.err ? `${v}% (90% range ${(v - item.payload.err[0]).toFixed(0)}–${(v + item.payload.err[1]).toFixed(0)}%)` : `${v}%`,
                  'Right',
                ]} />
              <Bar dataKey="value" radius={4} isAnimationActive={false}
                label={{ position: 'insideLeft', formatter: (v) => `${v}%`, fill: '#fff', fontSize: 12 }}>
                {bars.map((b) => <Cell key={b.name} fill={b.engine ? theme.series[0] : theme.muted} />)}
                <ErrorBar dataKey="err" direction="x" isAnimationActive={false} width={6} stroke={theme.text} strokeWidth={1.2} />
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
