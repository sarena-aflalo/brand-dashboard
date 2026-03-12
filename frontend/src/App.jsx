import { useState } from 'react'
import Header from './components/Header'
import KPIStrip from './components/KPIStrip'
import EmailTab from './components/EmailTab'
import InfluencerTab from './components/InfluencerTab'
import PaidTab from './components/PaidTab'

const TABS = [
  { id: 'email', label: 'Email' },
  { id: 'influencer', label: 'Influencer' },
  { id: 'paid', label: 'Creative' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('email')

  return (
    <div className="min-h-screen bg-[#F4F5F7]">
      {/* Sticky top section: header + KPI strip + tabs */}
      <div className="sticky top-0 z-10 shadow-sm">
        <Header />
        <KPIStrip />

        {/* Tab bar */}
        <div className="bg-white border-b border-gray-200 px-6">
          <nav className="flex gap-0" aria-label="Tabs">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  px-4 py-3 text-sm font-medium border-b-2 transition-colors
                  ${activeTab === tab.id
                    ? 'border-gray-900 text-gray-900'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }
                `}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Tab content */}
      <main className="px-6 py-5 max-w-7xl mx-auto">
        {activeTab === 'email' && <EmailTab />}
        {activeTab === 'influencer' && <InfluencerTab />}
        {activeTab === 'paid' && <PaidTab />}
      </main>
    </div>
  )
}
