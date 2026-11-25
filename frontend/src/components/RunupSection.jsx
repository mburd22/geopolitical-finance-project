// Does a big run-up before an event predict the reaction after it? ("buy the rumor, sell the news")

import { useEffect, useState } from 'react'
import {
  CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { getRunup } from '../api'
import { label, pct, signClass, useChartTheme } from '../theme'

// Plain-English reading of the correlation, judged against chance and against ordinary days.
function verdict(r) {
  if (r.event_corr <= -0.15 && r.event_p < 0.05) {
    return r.event_corr < r.ordinary_corr - 0.05
      ? 'Bigger run-ups were followed by weaker moves, more than on ordinary days: a real "sell the news" pattern.'
      : 'Bigger run-ups were followed by weaker moves, but no more than on ordinary days (general mean reversion).'
  }
  if (r.event_corr >= 0.15) {
    return 'Momentum, not "sell the news": stocks that had already run up tended to keep going. Much of this is the 2022 rearmament wave, when events came in clusters.'
  }
  return 'No reliable link: the run-up before an event says little about the move after it.'
}

export default function RunupSection({ ticker }) {
  const theme = useChartTheme()
  const [window, setWindow] = useState('60d')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getRunup(ticker, window).then(setData).catch((err) => setError(err.message))
  }, [ticker, window])

  if (error) return <p className="error">{error}</p>
  if (!data) return <p className="muted">Measuring run-ups…</p>

  const tooltipStyle = {
    background: theme.surface, border: `1px solid ${theme.grid}`, borderRadius: 8, padding: 10,
    color: theme.text, fontSize: 13, maxWidth: 'min(260px, 65vw)',
  }

  return (
    <div className="card">
      <div className="toolbar">
        <h2 style={{ margin: 0, marginRight: 'auto' }}>Does a run-up predict the reaction?</h2>
        <select value={window} onChange={(e) => setWindow(e.target.value)} aria-label="Run-up window">
          <option value="60d">Run-up over 60 days before</option>
          <option value="20d">Run-up over 20 days before</option>
        </select>
      </div>
      <p className="muted small">
        If {ticker} had already beaten its market before an event, did it do worse afterwards ("buy the rumor,
        sell the news")? Each dot is one event. The same measurement on ordinary days is the control.
      </p>
      <p><strong>{verdict(data)}</strong></p>

      <div className="tiles">
        <div className="tile">
          <div className="tile-title">Link around events</div>
          <div className="tile-value">{data.event_corr > 0 ? '+' : ''}{data.event_corr.toFixed(2)}</div>
          <div className="tile-note">rank correlation, {data.events} events (−1 to +1; 0 = no link)</div>
        </div>
        <div className="tile">
          <div className="tile-title">Same, on ordinary days</div>
          <div className="tile-value">{data.ordinary_corr > 0 ? '+' : ''}{data.ordinary_corr.toFixed(2)}</div>
          <div className="tile-note">{data.ordinary_days} non-overlapping 20-day windows</div>
        </div>
        <div className="tile">
          <div className="tile-title">Chance of a link this negative by luck</div>
          <div className="tile-value">{(data.event_p * 100).toFixed(0)}%</div>
          <div className="tile-note">permutation test; under 5% would be notable</div>
        </div>
      </div>

      <div className="chart">
        <ResponsiveContainer width="100%" height={320}>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
            <CartesianGrid stroke={theme.grid} />
            <XAxis type="number" dataKey="runup" unit="%" stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }}
              label={{ value: `Run-up vs market, ${window} before`, position: 'insideBottom', offset: -12, fill: theme.muted, fontSize: 12 }} />
            <YAxis type="number" dataKey="after" unit="%" width={48} stroke={theme.axis} tick={{ fill: theme.muted, fontSize: 12 }} />
            <ZAxis range={[50, 50]} />
            <ReferenceLine x={0} stroke={theme.axis} />
            <ReferenceLine y={0} stroke={theme.axis} />
            <Tooltip content={({ payload }) => {
              const p = payload?.[0]?.payload
              if (!p) return null
              return (
                <div style={tooltipStyle}>
                  <strong>{p.event}</strong> ({p.date})<br />
                  {label(p.category)} · run-up {pct(p.runup)} · next 20 days {pct(p.after)}
                </div>
              )
            }} />
            <Scatter data={data.points} fill={theme.series[0]} fillOpacity={0.7} isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run-up</th><th className="num">Events</th><th className="num">Avg run-up</th>
              <th className="num">Avg next 20 days</th><th className="num">Beat market</th>
            </tr>
          </thead>
          <tbody>
            {data.thirds.map((t) => (
              <tr key={t.third} className="static">
                <td>{label(t.third)}</td>
                <td className="num">{t.events}</td>
                <td className={`num ${signClass(t.avg_runup)}`}>{pct(t.avg_runup)}</td>
                <td className={`num ${signClass(t.avg_after)}`}>{pct(t.avg_after)}</td>
                <td className="num">{t.beat_market.toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Adding run-up to the analog engine didn't improve its calls in the backtest, so it's shown as context only.
      </p>
    </div>
  )
}
