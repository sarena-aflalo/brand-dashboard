import { useEffect, useState } from 'react'

// Each launch defines its published window — creatives created within
// that range are considered part of that launch.
const LAUNCHES = [
  {
    id: 'denim-leather',
    name: 'Denim + Leather',
    window: 'Jan 22 – Feb 11, 2026',
    publishedStart: '2026-01-23',
    publishedEnd:   '2026-01-27',
    published: 'Jan 23 – Jan 27',
    creatives: 17,
    spend:     17179,
    revenue:   66670,
    roas:      3.88,
    ctr:       2.22,
    aov:       995,
    purchases: 67,
  },
  {
    id: 'pre-spring',
    name: 'Pre Spring',
    window: 'Feb 9 – Mar 1, 2026',
    publishedStart: '2026-02-10',
    publishedEnd:   '2026-02-14',
    published: 'Feb 12',
    creatives: 15,
    spend:     15143,
    revenue:   32619,
    roas:      2.15,
    ctr:       1.36,
    aov:       815,
    purchases: 40,
  },
]

const METRICS = [
  { key: 'creatives', label: 'Creatives', format: (v) => v },
  { key: 'published', label: 'Published', format: (v) => v },
  { key: 'spend',     label: 'Spend',     format: (v) => `$${v.toLocaleString()}` },
  { key: 'revenue',   label: 'Revenue',   format: (v) => `$${v.toLocaleString()}` },
  { key: 'roas',      label: 'ROAS',      format: (v) => `${v}x` },
  { key: 'ctr',       label: 'CTR',       format: (v) => `${v}%` },
  { key: 'aov',       label: 'AOV',       format: (v) => `$${v.toLocaleString()}` },
  { key: 'purchases', label: 'Purchases', format: (v) => v },
]

function pickThumbnail(allCreatives, publishedStart, publishedEnd) {
  const start = new Date(publishedStart)
  const end   = new Date(publishedEnd + 'T23:59:59Z')
  // Find any creative published within the window that has a thumbnail
  const match = allCreatives.find((c) => {
    if (!c.thumbnail_url || !c.created_time) return false
    const d = new Date(c.created_time)
    return d >= start && d <= end
  })
  return match?.thumbnail_url ?? null
}

function ImageCell({ url, name }) {
  if (url) {
    return (
      <img
        src={`/api/proxy/image?url=${encodeURIComponent(url)}`}
        alt={name}
        className="w-full aspect-square object-cover rounded"
      />
    )
  }
  return (
    <div className="w-full aspect-square bg-gray-100 rounded flex items-center justify-center">
      <svg className="w-8 h-8 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    </div>
  )
}

export default function LaunchTab() {
  const [thumbnails, setThumbnails] = useState({}) // launch id → url

  useEffect(() => {
    fetch('/api/paid/all-creatives')
      .then((r) => r.ok ? r.json() : null)
      .then((j) => {
        if (!j?.data) return
        const result = {}
        for (const launch of LAUNCHES) {
          result[launch.id] = pickThumbnail(j.data, launch.publishedStart, launch.publishedEnd)
        }
        setThumbnails(result)
      })
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-1">
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-gray-800">3-Week Post-Launch Performance</h2>
        <p className="text-xs text-gray-400 mt-0.5">Each launch measured over the 21 days following first creative publish.</p>
      </div>

      <div className="bg-white rounded-lg overflow-hidden">
        <table className="w-full border-collapse">
          <colgroup>
            <col className="w-32" />
            {LAUNCHES.map((l) => <col key={l.id} />)}
          </colgroup>

          <thead>
            <tr className="border-b border-gray-100">
              <th className="py-4 px-5" />
              {LAUNCHES.map((launch) => (
                <th key={launch.id} className="py-4 px-5 text-right align-bottom">
                  <div className="text-sm font-semibold text-gray-800">{launch.name}</div>
                  <div className="text-xs text-gray-400 mt-0.5">{launch.window}</div>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {/* Image row */}
            <tr className="border-b border-gray-100">
              <td className="py-4 px-5" />
              {LAUNCHES.map((launch) => (
                <td key={launch.id} className="py-4 px-5">
                  <div className="max-w-[120px] ml-auto">
                    <ImageCell url={thumbnails[launch.id] ?? null} name={launch.name} />
                  </div>
                </td>
              ))}
            </tr>

            {/* Metric rows */}
            {METRICS.map((metric, idx) => (
              <tr
                key={metric.key}
                className={idx < METRICS.length - 1 ? 'border-b border-gray-100' : ''}
              >
                <td className="py-3.5 px-5 text-[11px] font-semibold tracking-widest text-gray-400 uppercase">
                  {metric.label}
                </td>
                {LAUNCHES.map((launch) => (
                  <td key={launch.id} className="py-3.5 px-5 text-sm text-gray-800 text-right">
                    {metric.format(launch[metric.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
