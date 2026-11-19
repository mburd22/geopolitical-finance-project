// Small pieces for showing confound warnings: reasons an event's numbers might not be
// about the event itself (earnings, overlapping events, market turmoil).

// A compact marker for table rows: a warning symbol plus a count, with the details on hover.
// The text "1 note" means the meaning never depends on color alone.
export function ConfoundMarker({ confounds }) {
  if (!confounds || confounds.length === 0) return null
  return (
    <span className="confound-marker" title={confounds.join('\n')}>
      ⚠ {confounds.length} {confounds.length === 1 ? 'note' : 'notes'}
    </span>
  )
}

// The full list, for under a chart.
export function ConfoundList({ confounds }) {
  if (!confounds || confounds.length === 0) {
    return <p className="small muted">✓ No confounds found in this event's 20-day window.</p>
  }
  return (
    <div className="confound-box">
      <strong>⚠ Possible confounds</strong>
      <span className="small muted"> — other things that happened during the measurement window</span>
      <ul>
        {confounds.map((c) => <li key={c}>{c}</li>)}
      </ul>
    </div>
  )
}
