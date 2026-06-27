import { useState, Suspense, lazy } from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Watchlist from './pages/Watchlist'
import StockDetail from './pages/StockDetail'
import Settings from './pages/Settings'

// 懒加载非首屏页面
const Signals = lazy(() => import('./pages/Signals'))
const Backtest = lazy(() => import('./pages/Backtest'))
const DataManager = lazy(() => import('./pages/DataManager'))
const StrategyEditor = lazy(() => import('./pages/StrategyEditor'))
const AIResearch = lazy(() => import('./pages/AIResearch'))

function App() {
  return (
    <Layout>
      <Suspense fallback={<div className="flex items-center justify-center h-screen text-slate-400">加载中...</div>}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/stock/:symbol" element={<StockDetail />} />
          <Route path="/quote/:symbol" element={<StockDetail />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/strategy-editor" element={<StrategyEditor />} />
          <Route path="/ai-research" element={<AIResearch />} />
          <Route path="/data" element={<DataManager />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<div className="text-center py-20 text-slate-400">404 页面未找到</div>} />
        </Routes>
      </Suspense>
    </Layout>
  )
}

export default App
