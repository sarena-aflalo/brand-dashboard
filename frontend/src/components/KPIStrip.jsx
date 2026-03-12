import { useEffect, useState } from 'react'

function fmt(n) {
  if (n == null) return '—'
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function StatusBadge({ status }) {
  const map = {
    ahead:           { label: 'Ahead',           cls: 'bg-green-100 text-green-700' },
    on_track:        { label: 'On track',         cls: 'bg-green-100 text-green-700' },
    needs_attention: { label: 'Needs attention',  cls: 'bg-amber-100 text-amber-700' },
    behind:          { label: 'Behind',           cls: 'bg-red-100 text-red-700' },
    error:           { label: 'Error',            cls: 'bg-gray-100 text-gray-500' },
  }
  const { label, cls } = map[status] || map.error
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${cls}`}>{label}</span>
  )
}

const STATUS_BAR_COLOR = {
  ahead:           'bg-green-500',
  on_track:        'bg-gray-400',
  needs_attention: 'bg-amber-400',
  behind:          'bg-red-400',
}

function ProgressBar({ pct, status }) {
  const clamped = Math.min(Math.max(pct ?? 0, 0), 100)
  const color = status
    ? (STATUS_BAR_COLOR[status] ?? 'bg-gray-400')
    : (clamped >= 90 ? 'bg-green-500' : clamped >= 70 ? 'bg-amber-400' : 'bg-red-400')
  return (
    <div className="w-full bg-gray-100 rounded-full h-1.5 mt-2">
      <div
        className={`${color} h-1.5 rounded-full transition-all duration-500`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}

function KPICard({ label, data, loading, statusBar = false, fmt: fmtOverride }) {
  const fmtVal = fmtOverride ?? fmt
  if (loading) {
    return (
      <div className="bg-white rounded-lg px-5 py-4 flex-1 min-w-0 animate-pulse">
        <div className="h-3 bg-gray-200 rounded w-24 mb-3" />
        <div className="h-6 bg-gray-200 rounded w-32 mb-2" />
        <div className="h-1.5 bg-gray-100 rounded-full" />
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="bg-white rounded-lg px-5 py-4 flex-1 min-w-0">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
        <StatusBadge status={data.status} />
      </div>
      <div className="text-2xl font-semibold text-gray-900 mt-1">
        {data.actual != null ? fmtVal(data.actual) : <span className="text-gray-400 text-base">Unavailable</span>}
      </div>
      <div className="text-xs text-gray-400 mt-0.5">
        Goal: {fmtVal(data.goal)}
        {data.pct != null && <span className="ml-2 text-gray-500">({data.pct}%)</span>}
      </div>
      <ProgressBar pct={data.pct} status={statusBar ? data.status : undefined} />
      {data.error && (
        <p className="text-xs text-red-500 mt-1 truncate" title={data.error}>
          {data.error}
        </p>
      )}
    </div>
  )
}

export default function KPIStrip() {
  const [kpi, setKpi] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/kpi')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setKpi)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="bg-[#F4F5F7] border-b border-gray-200 px-6 py-3">
      {error && (
        <p className="text-xs text-red-500 mb-2">KPI fetch failed: {error}</p>
      )}
      <div className="flex gap-3">
        <KPICard label="Net New Subscribers" data={kpi?.subscribers} loading={loading} fmt={n => n == null ? '—' : (n >= 0 ? '+' : '') + Math.round(n).toLocaleString('en-US')} />
        <KPICard label="Klaviyo Email Revenue" data={kpi?.email} loading={loading} statusBar />
        <KPICard label="Influencer Revenue" data={kpi?.influencer} loading={loading} />
      </div>
    </div>
  )
}
