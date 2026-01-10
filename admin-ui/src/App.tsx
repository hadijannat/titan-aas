import { Routes, Route, Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Box,
  Layers,
  Package,
  Settings,
  Activity,
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Shells from './pages/Shells';
import Submodels from './pages/Submodels';
import Packages from './pages/Packages';
import SettingsPage from './pages/Settings';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Shells', href: '/shells', icon: Box },
  { name: 'Submodels', href: '/submodels', icon: Layers },
  { name: 'Packages', href: '/packages', icon: Package },
  { name: 'Settings', href: '/settings', icon: Settings },
];

function Sidebar() {
  const location = useLocation();

  return (
    <aside className="w-64 bg-gray-900 min-h-screen px-4 py-6">
      <div className="flex items-center gap-3 px-2 mb-8">
        <Activity className="h-8 w-8 text-primary-400" />
        <span className="text-xl font-bold text-white">Titan-AAS</span>
      </div>

      <nav className="space-y-1">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          return (
            <Link
              key={item.name}
              to={item.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                isActive
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-300 hover:bg-gray-800 hover:text-white'
              }`}
            >
              <item.icon className="h-5 w-5" />
              {item.name}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/shells" element={<Shells />} />
          <Route path="/submodels" element={<Submodels />} />
          <Route path="/packages" element={<Packages />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
