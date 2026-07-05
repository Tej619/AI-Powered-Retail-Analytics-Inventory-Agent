import { NavLink } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, BarChart3, FileText } from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat', icon: MessageSquare, label: 'AI Agent Chat' },
  { to: '/forecast', icon: BarChart3, label: 'Forecasting' },
  { to: '/extract', icon: FileText, label: 'Report Extraction' },
];

export default function Sidebar() {
  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col p-4 gap-2 min-h-screen">
      <div className="flex items-center gap-2 mb-8 px-2">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white text-sm">RA</div>
        <h1 className="text-lg font-bold text-white">AI Powered Retail Analytics</h1>
      </div>
      
      <nav className="flex flex-col gap-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                isActive ? 'bg-blue-600/20 text-blue-400' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
              }`
            }
          >
            <item.icon size={20} />
            <span className="text-sm font-medium">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}