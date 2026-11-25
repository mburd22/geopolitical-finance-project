// Every request to the Python back end goes through this file.
// fetch() sends a request to a web address and gives back the response.
// "async" functions can pause with "await" while waiting for the server to answer.

async function request(path, options) {
  let response
  try {
    response = await fetch(path, options)
  } catch {
    throw new Error("Can't reach the back end. Is the Python server running?")
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    // FastAPI sends validation errors as a list of {msg: ...} objects.
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => d.msg).join('; ')
      : body.detail
    throw new Error(detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export const getOptions = () => request('/api/options')

export const getEvents = (ticker) => request(`/api/events?ticker=${ticker}`)

export const getEventDetail = (date, ticker) => request(`/api/events/${date}?ticker=${ticker}`)

export const getCategories = (ticker) => request(`/api/categories?ticker=${ticker}`)

export const getBacktest = (ticker) => request(`/api/backtest?ticker=${ticker}`)

export const getRunup = (ticker, window) => request(`/api/runup?ticker=${ticker}&window=${window}`)

// Live: events the pipeline found in the news by itself.
export const getLiveStatus = () => request('/api/live/status')
export const getLiveEvents = (ticker, includeDismissed) =>
  request(`/api/live/events?ticker=${ticker}&include_dismissed=${includeDismissed}`)
export const getLiveScorecard = (ticker) => request(`/api/live/scorecard?ticker=${ticker}`)
export const runPipeline = () => post('/api/live/run', {})
export const setEventStatus = (id, action) => post(`/api/live/events/${id}/${action}`, {})

// A helper for POST requests, which send JSON data to the server.
const post = (path, data) =>
  request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })

export const findAnalogs = (newEvent) => post('/api/analogs', newEvent)

// The two optional Claude features (need an API key on the Python side).
export const claudeThesis = (newEvent) => post('/api/claude-thesis', newEvent)

export const parseHeadline = (headline) => post('/api/parse-headline', { headline })
