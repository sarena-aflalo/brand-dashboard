const LAUNCHES = [
  {
    id: 'denim-leather',
    name: 'Denim + Leather',
    window: 'Jan 22 – Feb 11, 2026',
    image: null, // replace with proxied thumbnail URL if desired
    creatives: 17,
    published: 'Jan 23 – Jan 27',
    spend: 17179,
    revenue: 66670,
    roas: 3.88,
    ctr: 2.22,
    aov: 995,
    purchases: 67,
  },
  {
    id: 'pre-spring',
    name: 'Pre Spring',
    window: 'Feb 9 – Mar 1, 2026',
    image: null,
    creatives: 15,
    published: 'Feb 12',
    spend: 15143,
    revenue: 32619,
    roas: 2.15,
    ctr: 1.36,
    aov: 815,
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

function ImageCell({ image, name }) {
  if (image) {
    return (
      <img
        src={`/api/proxy/image?url=${encodeURIComponent(image)}`}
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

          {/* Launch header row */}
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
                    <ImageCell image={launch.image} name={launch.name} />
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
