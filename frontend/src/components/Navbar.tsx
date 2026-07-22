import { Link, useLocation } from 'react-router-dom';
import { Activity, LogOut, LayoutDashboard, History as HistoryIcon } from 'lucide-react';

interface NavbarProps {
  isAuthenticated: boolean;
  onLogout: () => void;
}

export default function Navbar({ isAuthenticated, onLogout }: NavbarProps) {
  const location = useLocation();

  if (!isAuthenticated) return null;

  return (
    <nav className="glass-panel sticky top-0 z-50 border-b border-white/10">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center space-x-8">
            <Link to="/" className="flex items-center space-x-2 text-white">
              <Activity className="h-6 w-6 text-indigo-400 drop-shadow-[0_0_8px_rgba(99,102,241,0.8)]" />
              <span className="font-bold text-lg hidden sm:block bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">
                AI Cost Detective
              </span>
            </Link>
            
            <div className="flex space-x-4">
              <Link
                to="/dashboard"
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
                  location.pathname === '/dashboard'
                    ? 'bg-white/10 text-white shadow-lg border border-white/10'
                    : 'text-gray-300 hover:bg-white/5 hover:text-white'
                }`}
              >
                <LayoutDashboard className="h-4 w-4" />
                <span>Dashboard</span>
              </Link>
              <Link
                to="/history"
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
                  location.pathname === '/history'
                    ? 'bg-white/10 text-white shadow-lg border border-white/10'
                    : 'text-gray-300 hover:bg-white/5 hover:text-white'
                }`}
              >
                <HistoryIcon className="h-4 w-4" />
                <span>History</span>
              </Link>
            </div>
          </div>

          <div>
            <button
              onClick={onLogout}
              className="flex items-center space-x-2 text-gray-300 hover:text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-white/5 transition-all duration-300"
            >
              <LogOut className="h-4 w-4" />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
