import { useEffect, useState } from 'react'

function fmt(n) {
  if (n == null) return '—'
  return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex gap-4 py-2">
          <div className="h-3 bg-gray-200 rounded w-6" />
          <div className="h-3 bg-gray-200 rounded flex-1" />
          <div className="h-3 bg-gray-200 rounded w-28" />
          <div className="h-3 bg-gray-200 rounded w-24" />
          <div className="h-3 bg-gray-200 rounded w-16" />
          <div className="h-3 bg-gray-200 rounded w-16" />
        </div>
      ))}
    </div>
  )
}

export default function InfluencerTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/influencer/creators')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`) ; return r.json() })
      .then((j) => setData(j.data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const totalRevenue    = data ? data.reduce((s, c) => s + c.revenue, 0)    : 0
  const totalOrders     = data ? data.reduce((s, c) => s + c.orders, 0)     : 0
  const totalCommission = data ? data.reduce((s, c) => s + c.commission, 0) : 0

  return (
    <div className="bg-white rounded-lg p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Creator Performance</h3>

      {loading && <Skeleton />}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          Failed to load creator data: {error}
        </div>
      )}

      {data && data.length === 0 && (
        <p className="text-sm text-gray-400 py-4 text-center">No orders this month.</p>
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs font-medium text-gray-400 uppercase tracking-wide border-b border-gray-100">
                <th className="text-left pb-2 pr-4">#</th>
                <th className="text-left pb-2 pr-4">Creator</th>
                <th className="text-left pb-2 pr-4">Handle</th>
                <th className="text-right pb-2 pr-4">Revenue</th>
                <th className="text-right pb-2 pr-4">Commission</th>
                <th className="text-right pb-2 pr-4">Rate</th>
                <th className="text-right pb-2">Orders</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c, i) => (
                <tr key={c.handle || c.name} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                  <td className="py-2.5 pr-4 text-gray-400">{i + 1}</td>
                  <td className="py-2.5 pr-4 font-medium text-gray-800">{c.name}</td>
                  <td className="py-2.5 pr-4 text-gray-500">
                    {c.handle
                      ? <a href={`https://www.instagram.com/${c.handle.replace('@', '')}`} target="_blank" rel="noopener noreferrer" className="hover:text-gray-800 underline underline-offset-2">{c.handle}</a>
                      : '—'}
                  </td>
                  <td className="py-2.5 pr-4 text-right font-medium text-gray-800">{fmt(c.revenue)}</td>
                  <td className="py-2.5 pr-4 text-right text-gray-500">{fmt(c.commission)}</td>
                  <td className="py-2.5 pr-4 text-right text-gray-500">{c.commission_rate != null ? `${c.commission_rate}%` : '—'}</td>
                  <td className="py-2.5 text-right text-gray-500">{c.orders.toLocaleString()}</td>
                </tr>
              ))}
              <tr className="bg-gray-50 border-t-2 border-gray-200">
                <td className="py-2.5 pr-4 text-xs font-medium text-gray-400 uppercase tracking-wide" colSpan={3}>Total</td>
                <td className="py-2.5 pr-4 text-right font-semibold text-gray-900">{fmt(totalRevenue)}</td>
                <td className="py-2.5 pr-4 text-right font-medium text-gray-600">{fmt(totalCommission)}</td>
                <td className="py-2.5 pr-4" />
                <td className="py-2.5 text-right text-gray-500">{totalOrders.toLocaleString()}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
