import React from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAppStore } from '@/stores/useAppStore'
import {
  LayoutDashboard,
  List,
  BarChart3,
  Settings,
  Menu,
  ChevronLeft,
  ChevronRight,
  Zap,
  Beaker,
  Database,
  Code,
  Sparkles,
  RefreshCw,
} from 'lucide-react'

const navItems = [
  { icon: LayoutDashboard, label: '行情看板', path: '/' },
  { icon: List, label: '自选股', path: '/watchlist' },
  { icon: BarChart3, label: '个股分析', path: '/stock/000001' },
  { icon: Zap, label: '信号中心', path: '/signals' },
  { icon: Beaker, label: '回测', path: '/backtest' },
  { icon: Code, label: '策略', path: '/strategy-editor' },
  { icon: Sparkles, label: 'AI 投研', path: '/ai-research' },
  { icon: Database, label: '数据', path: '/data' },
  { icon: Settings, label: '设置', path: '/settings' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { sidebarOpen, toggleSidebar } = useAppStore()
  const location = useLocation()
  const navigate = useNavigate()

  const handleRefresh = () => {
    navigate(0)
  }

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside
        className={`bg-slate-900 text-white transition-all duration-300 flex flex-col ${
          sidebarOpen ? 'w-56' : 'w-16'
        }`}
      >
        <div className="flex items-center justify-between h-14 px-4 border-b border-slate-700">
          {sidebarOpen && (
            <span className="font-bold text-lg tracking-tight">量化工作台</span>
          )}
          <button
            onClick={toggleSidebar}
            className="p-1 rounded hover:bg-slate-700 transition"
          >
            {sidebarOpen ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
          </button>
        </div>

        <nav className="flex-1 py-4 space-y-1">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path || location.pathname.startsWith(item.path + '/')
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-2.5 transition ${
                  isActive
                    ? 'bg-slate-800 text-sky-400 border-r-2 border-sky-400'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
                title={item.label}
              >
                <item.icon size={20} />
                {sidebarOpen && <span className="text-sm">{item.label}</span>}
              </Link>
            )
          })}
        </nav>

        <div className="p-4 border-t border-slate-700 text-xs text-slate-400">
          {sidebarOpen && <span>v1.0.0</span>}
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 bg-white border-b border-slate-200 flex items-center px-6 justify-between">
          <h1 className="text-lg font-semibold text-slate-800">
            {navItems.find((n) => location.pathname === n.path || location.pathname.startsWith(n.path + '/'))?.label || 'Quant Workbench'}
          </h1>
          <div className="flex items-center gap-3">
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 transition"
              title="刷新页面"
            >
              <RefreshCw size={18} />
            </button>
            <div className="text-sm text-slate-500">
              {new Date().toLocaleDateString('zh-CN')}
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  )
}
