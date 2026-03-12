import { useEffect, useState } from 'react'

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(n, digits = 0) {
  if (n == null) return '—'
  return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const day = d.toLocaleDateString('en-US', { weekday: 'short' })
  const date = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return `${day}, ${date}`
}

function useApi(url) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(url)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.url}`) ; return r.json() })
      .then((j) => setData(j.data ?? j))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [url])

  return { data, loading, error }
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function Skeleton({ rows = 4, cols = 6 }) {
  return (
    <div className="animate-pulse">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 py-3 border-b border-gray-100">
          {Array.from({ length: cols }).map((_, j) => (
            <div key={j} className="h-3 bg-gray-200 rounded flex-1" />
          ))}
        </div>
      ))}
    </div>
  )
}

function ErrorMsg({ msg }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
      Failed to load: {msg}
    </div>
  )
}

// ── Subscriber Growth Card ────────────────────────────────────────────────────

function SourceBar({ label, value, total }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{label}</span>
        <span>{value.toLocaleString()} ({pct}%)</span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-1.5">
        <div className="bg-gray-400 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function SubscriberCard() {
  const { data, loading, error } = useApi('/api/email/subscribers')

  return (
    <div className="bg-white rounded-lg p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Subscriber Growth</h3>
      {loading && <Skeleton rows={3} cols={2} />}
      {error && <ErrorMsg msg={error} />}
      {data && (
        <>
          <div className="grid grid-cols-4 gap-4 mb-5">
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide">Total Subscribers</p>
              <p className="text-2xl font-semibold text-gray-900 mt-0.5">
                {(data.total_subscribers ?? 0).toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide">Net New</p>
              <p className="text-2xl font-semibold text-gray-900 mt-0.5">
                {data.net_new >= 0 ? '+' : ''}{data.net_new.toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide">Gross Adds</p>
              <p className="text-2xl font-semibold text-gray-900 mt-0.5">
                {data.gross_adds.toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide">Unsubscribes</p>
              <p className="text-2xl font-semibold text-gray-900 mt-0.5">
                {data.unsubscribes.toLocaleString()}
              </p>
            </div>
          </div>

          {/* Monthly goal progress */}
          <div>
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>Monthly goal</span>
              <span>{data.gross_adds.toLocaleString()} / {data.goal.toLocaleString()}</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2">
              <div
                className="bg-green-500 h-2 rounded-full transition-all"
                style={{ width: `${Math.min(100, Math.round((data.gross_adds / data.goal) * 100))}%` }}
              />
            </div>
            <p className="text-xs text-gray-400 mt-1">
              {Math.round((data.gross_adds / data.goal) * 100)}% of {data.goal.toLocaleString()} goal
            </p>
          </div>
        </>
      )}
    </div>
  )
}

// ── Campaign Table ────────────────────────────────────────────────────────────

function Badge({ type }) {
  if (!type) return null
  const map = {
    strong:  { cls: 'bg-green-100 text-green-700',  label: 'Strong' },
    weak:    { cls: 'bg-red-100 text-red-700',      label: 'Weak' },
    average: { cls: 'bg-gray-100 text-gray-500',    label: 'Average' },
  }
  const entry = map[type]
  if (!entry) return null
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${entry.cls}`}>{entry.label}</span>
  )
}

function CampaignTable() {
  const [raw, setRaw] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/email/campaigns')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`) ; return r.json() })
      .then(setRaw)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const data = raw
  const campaigns = raw?.campaigns ?? []
  const ytd = raw?.ytd ?? null

  return (
    <div className="bg-white rounded-lg p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Campaign Performance</h3>
      {loading && <Skeleton rows={5} cols={7} />}
      {error && <ErrorMsg msg={error} />}
      {data && campaigns.length === 0 && (
        <p className="text-sm text-gray-400 py-4 text-center">No campaigns sent this month.</p>
      )}
      {data && campaigns.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs font-medium text-gray-400 uppercase tracking-wide border-b border-gray-100">
                <th className="text-left pb-2 pr-4">Date</th>
                <th className="text-left pb-2 pr-4">Subject</th>
                <th className="text-left pb-2 pr-4">Preview text</th>
                <th className="text-right pb-2 pr-4">Klaviyo Revenue</th>
                <th className="text-right pb-2 pr-4">Sends</th>
                <th className="text-right pb-2 pr-4">$ / Send</th>
                <th className="text-left pb-2"></th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => (
                <tr key={c.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                  <td className="py-2.5 pr-4 text-gray-500 whitespace-nowrap">{fmtDate(c.send_date)}</td>
                  <td className="py-2.5 pr-4 font-medium text-gray-800 max-w-[200px] truncate">{c.subject || '—'}</td>
                  <td className="py-2.5 pr-4 text-gray-500 max-w-[220px] truncate">{c.preview_text || '—'}</td>
                  <td className="py-2.5 pr-4 text-right font-medium text-gray-800">{fmt(c.revenue)}</td>
                  <td className="py-2.5 pr-4 text-right text-gray-500">{c.sends.toLocaleString()}</td>
                  <td className="py-2.5 pr-4 text-right text-gray-800">{fmt(c.per_send, 2)}</td>
                  <td className="py-2.5"><Badge type={c.badge} /></td>
                </tr>
              ))}
              {ytd && (
                <tr className="bg-gray-50 border-t-2 border-gray-200">
                  <td className="py-2.5 pr-4 text-xs font-medium text-gray-400 uppercase tracking-wide whitespace-nowrap">2026 Average</td>
                  <td className="py-2.5 pr-4 text-xs text-gray-400">{ytd.campaign_count} campaigns</td>
                  <td className="py-2.5 pr-4"></td>
                  <td className="py-2.5 pr-4 text-right font-medium text-gray-600">{fmt(ytd.avg_revenue)}</td>
                  <td className="py-2.5 pr-4 text-right text-gray-500">{(ytd.avg_sends ?? 0).toLocaleString()}</td>
                  <td className="py-2.5 pr-4 text-right text-gray-600">{fmt(ytd.avg_per_send, 2)}</td>
                  <td className="py-2.5"></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Always-On Flows ───────────────────────────────────────────────────────────

function FlowCard({ flow }) {
  return (
    <div className="bg-white rounded-lg p-5">
      <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">{flow.name}</p>
      <p className="text-2xl font-semibold text-gray-900 mt-2">
        {flow.revenue > 0 ? '$' + Math.round(flow.revenue).toLocaleString('en-US') : '—'}
      </p>
      <p className="text-xs text-gray-400 mt-0.5">Revenue this month</p>
      <div className="mt-3 pt-3 border-t border-gray-100 flex gap-4">
        <div>
          <p className="text-sm font-medium text-gray-700">{flow.per_send > 0 ? '$' + flow.per_send.toFixed(2) : '—'}</p>
          <p className="text-xs text-gray-400">per send</p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-700">{flow.sends > 0 ? flow.sends.toLocaleString() : '—'}</p>
          <p className="text-xs text-gray-400">sends</p>
        </div>
      </div>
    </div>
  )
}

function AlwaysOnFlows() {
  const { data, loading, error } = useApi('/api/email/flows')

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Always-On Flows</h3>
      {loading && (
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-lg p-5 animate-pulse">
              <div className="h-3 bg-gray-200 rounded w-24 mb-3" />
              <div className="h-6 bg-gray-200 rounded w-20" />
            </div>
          ))}
        </div>
      )}
      {error && <ErrorMsg msg={error} />}
      {data && (
        <div className="grid grid-cols-3 gap-4">
          {data.map((flow) => (
            <FlowCard key={flow.id || flow.name} flow={flow} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Email Tab Root ────────────────────────────────────────────────────────────

export default function EmailTab() {
  return (
    <div className="space-y-5">
      <SubscriberCard />
      <CampaignTable />
      <AlwaysOnFlows />
    </div>
  )
}
