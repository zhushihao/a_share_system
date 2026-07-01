import { useState, Suspense, lazy, Component, ReactNode } from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Watchlist from './pages/Watchlist'
import StockDetail from './pages/StockDetail'
import F10 from './pages/F10'
import Settings from './pages/Settings'

// 懒加载非首屏页面
const Signals = lazy(() => import('./pages/Signals'))
const Backtest = lazy(() => import('./pages/Backtest'))
const DataManager = lazy(() => import('./pages/DataManager'))
const StrategyEditor = lazy(() => import('./pages/StrategyEditor'))
const AIResearch = lazy(() => import('./pages/AIResearch'))

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('App ErrorBoundary caught:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center py-20 text-slate-600">
          <h1 className="text-3xl font-bold mb-4">页面出错了</h1>
          <p className="mb-6">{this.state.error?.message || '未知错误'}</p>
          <Link
            to="/"
            className="px-4 py-2 bg-sky-600 text-white rounded-lg hover:bg-sky-700 transition"
            onClick={() => this.setState({ hasError: false })}
          >
            返回首页
          </Link>
        </div>
      )
    }
    return this.props.children
  }
}

function App() {
  return (
    <Layout>
      <ErrorBoundary>
        <Suspense fallback={<div className="flex items-center justify-center h-screen text-slate-400">加载中...</div>}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/stock/:symbol" element={<StockDetail />} />
            <Route path="/quote/:symbol" element={<StockDetail />} />
            <Route path="/f10/:symbol" element={<F10 />} />
            <Route path="/signals" element={<Signals />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/strategy-editor" element={<StrategyEditor />} />
            <Route path="/ai-research" element={<AIResearch />} />
            <Route path="/data" element={<DataManager />} />
            <Route path="/settings" element={<Settings />} />
            <Route
              path="*"
              element={
                <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                  <h1 className="text-4xl font-bold mb-4">404</h1>
                  <p className="mb-6">页面未找到</p>
                  <Link to="/" className="px-4 py-2 bg-sky-600 text-white rounded-lg hover:bg-sky-700 transition">
                    返回首页
                  </Link>
                </div>
              }
            />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </Layout>
  )
}

export default App
