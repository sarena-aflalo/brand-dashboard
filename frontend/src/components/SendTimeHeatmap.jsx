import { useEffect, useState } from 'react'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const DAY_INDEX = { 0: 'Sun', 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat' }

const TIME_BUCKETS = [
  { label: '6–9 AM',   start: 6,  end: 9  },
  { label: '9–12 PM',  start: 9,  end: 12 },
  { label: '12–3 PM',  start: 12, end: 15 },
  { label: '3–6 PM',   start: 15, end: 18 },
  { label: '6–9 PM',   start: 18, end: 21 },
  { label: '9 PM+',    start: 21, end: 24 },
]

function getBucket(hour) {
  return TIME_BUCKETS.find((b) => hour >= b.start && hour < b.end)?.label ?? null
}

function buildGrid(campaigns) {
  // grid[day][timeBucket] = [ctr values]
  const grid = {}
  for (const day of DAYS) {
    grid[day] = {}
    for (const b of TIME_BUCKETS) grid[day][b.label] = []
  }

  for (const { send_date, ctr } of campaigns) {
    const d = new Date(send_date)
    const etParts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      weekday: 'short',
      hour: 'numeric',
      hour12: false,
    }).formatToParts(d)
    const dayName = etParts.find((p) => p.type === 'weekday')?.value
    const hourStr = etParts.find((p) => p.type === 'hour')?.value
    const etHour = hourStr === '24' ? 0 : parseInt(hourStr, 10)
    const bucket = getBucket(etHour)
    if (dayName && bucket && grid[dayName]?.[bucket] !== undefined) {
      grid[dayName][bucket].push(ctr)
    }
  }
  return grid
}

function avg(arr) {
  if (!arr.length) return null
  return arr.reduce((a, b) => a + b, 0) / arr.length
}

function cellColor(value, min, max) {
  if (value === null) return { bg: 'bg-gray-50', text: 'text-gray-300' }
  if (max === min) return { bg: 'bg-blue-100', text: 'text-blue-700' }
  const t = (value - min) / (max - min)
  if (t >= 0.75) return { bg: 'bg-green-100', text: 'text-green-800' }
  if (t >= 0.5)  return { bg: 'bg-green-50',  text: 'text-green-700' }
  if (t >= 0.25) return { bg: 'bg-gray-100',  text: 'text-gray-600' }
  return { bg: 'bg-red-50', text: 'text-red-500' }
}

export default function SendTimeHeatmap() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/email/send-time-analysis')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`) ; return r.json() })
      .then((j) => setData(j.data ?? []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const grid = data ? buildGrid(data) : null

  // Compute min/max avg CTR across all cells for color scaling
  let minVal = Infinity, maxVal = -Infinity
  if (grid) {
    for (const day of DAYS) {
      for (const b of TIME_BUCKETS) {
        const v = avg(grid[day][b.label])
        if (v !== null) { minVal = Math.min(minVal, v); maxVal = Math.max(maxVal, v) }
      }
    }
  }

  return (
    <div className="bg-white rounded-lg p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-1">Best Send Times</h3>
      <p className="text-xs text-gray-400 mb-4">Average CTR by day of week and time of day (LTD, ET)</p>

      {loading && (
        <div className="animate-pulse space-y-2">
          {[1,2,3,4,5,6,7].map((i) => (
            <div key={i} className="flex gap-2">
              <div className="h-8 w-10 bg-gray-100 rounded" />
              {[1,2,3,4,5,6].map((j) => <div key={j} className="h-8 flex-1 bg-gray-100 rounded" />)}
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          Failed to load: {error}
        </div>
      )}

      {grid && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="text-left pb-2 pr-3 text-gray-400 font-medium w-10" />
                {TIME_BUCKETS.map((b) => (
                  <th key={b.label} className="pb-2 px-1 text-center text-gray-400 font-medium whitespace-nowrap">
                    {b.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DAYS.map((day) => (
                <tr key={day}>
                  <td className="pr-3 py-1 text-gray-500 font-medium">{day}</td>
                  {TIME_BUCKETS.map((b) => {
                    const vals = grid[day][b.label]
                    const v = avg(vals)
                    const { bg, text } = cellColor(v, minVal, maxVal)
                    return (
                      <td key={b.label} className="px-1 py-1">
                        <div className={`rounded flex flex-col items-center justify-center h-10 ${bg}`}>
                          {v !== null ? (
                            <>
                              <span className={`font-semibold ${text}`}>{(v * 100).toFixed(2)}%</span>
                              <span className="text-gray-300 text-[10px]">{vals.length} send{vals.length !== 1 ? 's' : ''}</span>
                            </>
                          ) : (
                            <span className="text-gray-200">—</span>
                          )}
                        </div>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.length === 0 && (
        <p className="text-sm text-gray-400 py-4 text-center">No campaign data available.</p>
      )}
    </div>
  )
}
