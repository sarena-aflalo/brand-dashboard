import { useEffect, useState } from 'react'

function Skeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
      {Array.from({ length: 10 }).map((_, i) => (
        <div key={i} className="animate-pulse">
          <div className="bg-gray-200 rounded-lg aspect-square mb-2" />
          <div className="h-3 bg-gray-200 rounded w-3/4" />
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

function AdCard({ ad, rank }) {
  return (
    <div className="flex flex-col">
      <div className="relative rounded-lg overflow-hidden bg-gray-100 aspect-square mb-2">
        <span className="absolute top-1.5 left-1.5 bg-black/50 text-white text-xs font-medium px-1.5 py-0.5 rounded">
          {rank}
        </span>
        {ad.thumbnail_url
          ? <img src={`/api/proxy/image?url=${encodeURIComponent(ad.thumbnail_url)}`} alt={ad.creative_name} className="w-full h-full object-cover" />
          : <div className="w-full h-full bg-gray-200 flex items-center justify-center">
              <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
        }
      </div>
    </div>
  )
}

function AdGrid({ ads }) {
  if (!ads.length) return <p className="text-sm text-gray-400 py-4 text-center">No ads found.</p>
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
      {ads.map((ad, i) => <AdCard key={ad.creative_id} ad={ad} rank={i + 1} />)}
    </div>
  )
}

export default function PaidTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/paid/creatives')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`) ; return r.json() })
      .then((j) => setData(j.data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-lg p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">Top Ads 2026</h3>
        {loading && <Skeleton />}
        {error && <ErrorMsg msg={error} />}
        {data && <AdGrid ads={data.top ?? []} />}
      </div>

      <div className="bg-white rounded-lg p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Bottom Ads 2026</h3>
        <p className="text-xs text-gray-400 mb-4">Ads with spend &gt; $0, zero conversions, and live for 7+ days — sorted by lowest CTR</p>
        {loading && <Skeleton />}
        {error && <ErrorMsg msg={error} />}
        {data && <AdGrid ads={data.bottom ?? []} />}
      </div>
    </div>
  )
}
