export default function Header() {
  const now = new Date()
  const month = now.toLocaleString('default', { month: 'long', year: 'numeric' })

  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
      <div>
        <h1 className="text-lg font-semibold text-gray-900 tracking-tight">
          AFLALO Brand Revenue Dashboard
        </h1>
        <p className="text-sm text-gray-500 mt-0.5">{month}</p>
      </div>
    </header>
  )
}
