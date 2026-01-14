import { Routes, Route, NavLink } from 'react-router-dom'
import {
  Activity,
  Database,
  HardDrive,
  Radio,
  Shield,
  Settings,
  Zap,
  LayoutDashboard,
} from 'lucide-react'
import Overview from './pages/Overview'
import DatabasePage from './pages/Database'
import CachePage from './pages/Cache'
import EventsPage from './pages/Events'
import ConnectorsPage from './pages/Connectors'
import SecurityPage from './pages/Security'
import ObservabilityPage from './pages/Observability'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Overview' },
  { path: '/database', icon: Database, label: 'Database' },
  { path: '/cache', icon: HardDrive, label: 'Cache' },
  { path: '/events', icon: Zap, label: 'Events' },
  { path: '/connectors', icon: Radio, label: 'Connectors' },
  { path: '/security', icon: Shield, label: 'Security' },
  { path: '/observability', icon: Activity, label: 'Observability' },
]

function App() {
  return (
    <div className="flex h-screen bg-slate-900">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-800 border-r border-slate-700">
        <div className="p-4 border-b border-slate-700">
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Settings className="w-6 h-6 text-titan-500" />
            Titan Control
          </h1>
          <p className="text-sm text-slate-400 mt-1">System Dashboard</p>
        </div>

        <nav className="p-2">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg mb-1 transition-colors ${
                  isActive
                    ? 'bg-titan-600 text-white'
                    : 'text-slate-300 hover:bg-slate-700 hover:text-white'
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/database" element={<DatabasePage />} />
          <Route path="/cache" element={<CachePage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/connectors" element={<ConnectorsPage />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route path="/observability" element={<ObservabilityPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
