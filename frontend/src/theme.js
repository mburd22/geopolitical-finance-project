// Chart colors for light and dark mode, plus small formatting helpers.
// Charts draw with SVG attributes, which can't read CSS variables reliably,
// so the chart colors live here in JavaScript instead.

import { useEffect, useState } from 'react'

const LIGHT = {
  series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
  positive: '#2a78d6',
  negative: '#e34948',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  muted: '#898781',
  text: '#52514e',
  surface: '#fcfcfb',
}

const DARK = {
  series: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
  positive: '#3987e5',
  negative: '#e66767',
  grid: '#2c2c2a',
  axis: '#383835',
  muted: '#898781',
  text: '#c3c2b7',
  surface: '#1a1a19',
}

// A "hook" is a React function whose name starts with "use".
// This one tracks a CSS media query (like "is the screen dark?" or "is it narrow?")
// and re-renders the component whenever the answer changes.
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const media = window.matchMedia(query)
    const onChange = (e) => setMatches(e.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange) // clean up when the component goes away
  }, [query])
  return matches
}

export function useChartTheme() {
  return useMediaQuery('(prefers-color-scheme: dark)') ? DARK : LIGHT
}

// True on phone-sized screens, so charts can use smaller margins and labels.
export const useNarrow = () => useMediaQuery('(max-width: 520px)')

// Each ticker always gets the same color, whichever chart it appears in. Charts only ever
// show one market at a time, so the two markets can reuse the same palette slots.
const TICKER_SLOTS = {
  ITA: 0, LMT: 1, RTX: 2, NOC: 3, GD: 4,
  EUDEF: 0, 'RHM.DE': 1, 'BA.L': 2, 'HO.PA': 3, 'SAAB-B.ST': 4, 'LDO.MI': 6,
}
export const tickerColor = (theme, ticker) => theme.series[TICKER_SLOTS[ticker]] ?? theme.muted

// Short display names: "SAAB-B.ST" -> "SAAB-B", "RHM.DE" -> "RHM"
export const shortTicker = (ticker) => ticker.split('.')[0]

// Same idea for categories. There are 9 categories but only 8 palette colors,
// so the ninth (coup) uses the muted gray rather than an invented color.
const CATEGORY_ORDER = [
  'war_outbreak', 'military_strike', 'escalation', 'weapons_test',
  'defense_spending', 'de_escalation', 'terrorism', 'election',
]
export const categoryColor = (theme, category) =>
  theme.series[CATEGORY_ORDER.indexOf(category)] ?? theme.muted

// "war_outbreak" -> "War outbreak", "de_escalation" -> "De-escalation"
export const label = (text) => {
  const spaced = String(text).replace(/^de_/, 'de-').replaceAll('_', ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

// 1.234 -> "+1.2%", null -> "—"
export const pct = (value, digits = 1) =>
  value === null || value === undefined ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`

// A CSS class name for coloring positive and negative numbers.
export const signClass = (value) => (value > 0 ? 'pos' : value < 0 ? 'neg' : '')
