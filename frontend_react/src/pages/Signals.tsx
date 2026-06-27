import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ScanLine,
  TrendingUp,
  TrendingDown,
  Eye,
  AlertTriangle,
  Trash2,
  Check,
  Zap,
  BarChart3,
  Filter,
  Activity,
  Layers,
} from 'lucide-react'
import {
  fetchSignals,
  scanSignals,
  scanWatchlistSignals,
  fetchSignalStrategies,
  fetchSignalStats,
  fetchSignalPerformance,
  scanResonance,
  expireOldSignals,
  acknowledgeSignal,
  deleteSignal,
  trackSignalPerformance,
  closeSignal,
} from '@/api/client'
import type { SignalItem, SignalStrategy, ResonanceData } from '@/types'

function SignalBadge({ type }: { type: string }) {
  const configs: Record<string, { className: string; icon: React.ReactNode }> = {
    BUY: { className: 'bg-red-50 text-red-600 border-red-200', icon: <TrendingUp size={14} /> },
    SELL: { className: 'bg-emerald-50 text-emerald-600 border-emerald-200', icon: <TrendingDown size={14} /> },
    WATCH: { className: 'bg-amber-50 text-amber-600 border-amber-200', icon: <Eye size={14} /> },
    ALERT: { className: 'bg-slate-50 text-slate-600 border-slate-200', icon: <AlertTriangle size={14} /> },
  }
  const cfg = configs[type] || configs.ALERT
  const label = type === 'BUY' ? '买入' : type === 'SELL' ? '卖出' : type === 'WATCH' ? '关注' : '预警'

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${cfg.className}`}>
      {cfg.icon}
      {label}
    </span>
  )
}

function ConfidenceBar({ value }: { value: number }) {
  const color = value >= 80 ? 'bg-red-500' : value >= 60 ? 'bg-amber-500' : 'bg-sky-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs text-slate-500">{value}</span>
    </div>
  )
}

export default function Signals() {
  const [signals, setSignals] = useState<SignalItem[]>([])
  const [strategies, setStrategies] = useState<SignalStrategy[]>([])
  const [stats, setStats] = useState<any>(null)
  const [performance, setPerformance] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [filterStrategy, setFilterStrategy] = useState('')
  const [filterType, setFilterType] = useState('')
  const [scanSymbols, setScanSymbols] = useState('')
  const [scanResult, setScanResult] = useState<any>(null)
  const [resonanceScanning, setResonanceScanning] = useState(false)
  const [resonanceResult, setResonanceResult] = useState<{ scanned: number; matched: number; results: ResonanceData[] } | null>(null)

  // Load signals, strategies, and stats on mount
  useEffect(() => {
    loadSignals()
    loadStrategies()
    loadStats()
    loadPerformance()
  }, [filterStrategy, filterType])

  async function loadSignals() {
    setLoading(true)
    try {
      const params: any = { limit: 100 }
      if (filterStrategy) params.strategy = filterStrategy
      const resp = await fetchSignals(params)
      setSignals(resp.signals || [])
    } catch (e) {
      console.error('Failed to load signals', e)
    } finally {
      setLoading(false)
    }
  }

  async function loadStrategies() {
    try {
      const resp = await fetchSignalStrategies()
      setStrategies(resp.strategies || [])
    } catch (e) {
      console.error('Failed to load strategies', e)
    }
  }

  async function loadStats() {
    try {
      const resp = await fetchSignalStats(30)
      setStats(resp)
    } catch (e) {
      console.error('Failed to load stats', e)
    }
  }

  async function loadPerformance() {
    try {
      const resp = await fetchSignalPerformance()
      setPerformance(resp)
    } catch (e) {
      console.error('Failed to load performance', e)
    }
  }

  async function handleScan() {
    setScanning(true)
    setScanResult(null)
    try {
      const symbols = scanSymbols
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter((s) => s.length > 0)
      if (symbols.length === 0) {
        // Scan watchlist if no symbols
        const resp = await scanWatchlistSignals()
        setScanResult(resp)
        if (resp.signals && resp.signals.length > 0) {
          loadSignals()
          loadStats()
        }
        return
      }
      const resp = await scanSignals({ symbols })
      setScanResult(resp)
      if (resp.signals && resp.signals.length > 0) {
        loadSignals()
        loadStats()
      }
    } catch (e) {
      console.error('Scan failed', e)
      setScanResult({ error: '扫描失败' })
    } finally {
      setScanning(false)
    }
  }

  async function handleAck(signalId: string) {
    try {
      await acknowledgeSignal(signalId)
      loadSignals()
    } catch (e) {
      console.error('Ack failed', e)
    }
  }

  async function handleTrack(signalId: string) {
    try {
      // 获取当前价格（简化：使用信号价格作为当前价格）
      const signal = signals.find((s) => s.id === signalId)
      const currentPrice = signal?.price || 0
      if (currentPrice > 0) {
        await trackSignalPerformance(signalId, currentPrice)
        loadSignals()
      }
    } catch (e) {
      console.error('Track failed', e)
    }
  }

  async function handleCloseSignal(signalId: string, status: string) {
    try {
      const signal = signals.find((s) => s.id === signalId)
      const exitPrice = signal?.price || 0
      await closeSignal(signalId, status, exitPrice)
      loadSignals()
    } catch (e) {
      console.error('Close failed', e)
    }
  }

  async function handleDelete(signalId: string) {
    try {
      await deleteSignal(signalId)
      loadSignals()
    } catch (e) {
      console.error('Delete failed', e)
    }
  }

  async function handleResonanceScan() {
    setResonanceScanning(true)
    setResonanceResult(null)
    try {
      const symbols = scanSymbols
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter((s) => s.length > 0)
      if (symbols.length === 0) {
        setResonanceResult({ scanned: 0, matched: 0, results: [] })
        return
      }
      const resp = await scanResonance(symbols, 0.7, true)
      setResonanceResult(resp)
    } catch (e) {
      console.error('Resonance scan failed', e)
      setResonanceResult({ scanned: 0, matched: 0, results: [] })
    } finally {
      setResonanceScanning(false)
    }
  }

  async function handleExpireOld() {
    try {
      const resp = await expireOldSignals(7)
      if (resp.expired_count > 0) {
        loadSignals()
        loadStats()
        loadPerformance()
      }
      alert(`已清理 ${resp.expired_count} 个过期信号`)
    } catch (e) {
      console.error('Expire old failed', e)
    }
  }

  const filteredSignals = signals.filter((s) => {
    if (filterType && s.signal_type !== filterType) return false
    return true
  })

  const dailySignals = filteredSignals.filter((s) => s.category === 'daily')
  const intradaySignals = filteredSignals.filter((s) => s.category === 'intraday')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">信号中心</h1>
          <p className="text-sm text-slate-500 mt-1">日线/日内信号检测与历史复盘</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExpireOld}
            className="flex items-center gap-2 px-3 py-2 bg-slate-100 text-slate-600 rounded-lg text-sm font-medium hover:bg-slate-200 transition"
          >
            <Trash2 size={14} />
            清理过期
          </button>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50"
          >
            <ScanLine size={16} />
            {scanning ? '扫描中...' : '扫描信号'}
          </button>
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-2">
              <Zap size={16} className="text-amber-500" />
              <span className="text-sm text-slate-500">30日信号总数</span>
            </div>
            <div className="text-2xl font-bold text-slate-800">{stats.total_signals || 0}</div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp size={16} className="text-red-500" />
              <span className="text-sm text-slate-500">买入信号</span>
            </div>
            <div className="text-2xl font-bold text-red-600">{stats.by_type?.BUY || 0}</div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-2">
              <TrendingDown size={16} className="text-emerald-500" />
              <span className="text-sm text-slate-500">卖出信号</span>
            </div>
            <div className="text-2xl font-bold text-emerald-600">{stats.by_type?.SELL || 0}</div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 size={16} className="text-sky-500" />
              <span className="text-sm text-slate-500">策略数</span>
            </div>
            <div className="text-2xl font-bold text-slate-800">{strategies.length}</div>
          </div>
        </div>
      )}

      {/* Performance stats */}
      {performance && performance.total_signals > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-2">
              <Activity size={16} className="text-purple-500" />
              <span className="text-sm text-slate-500">已平仓信号</span>
            </div>
            <div className="text-2xl font-bold text-slate-800">{performance.closed_signals || 0}</div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp size={16} className="text-red-500" />
              <span className="text-sm text-slate-500">胜率</span>
            </div>
            <div className={`text-2xl font-bold ${(performance.win_rate || 0) >= 50 ? 'text-red-600' : 'text-emerald-600'}`}>
              {performance.win_rate || 0}%
            </div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-2">
              <Zap size={16} className="text-amber-500" />
              <span className="text-sm text-slate-500">平均盈亏</span>
            </div>
            <div className={`text-2xl font-bold ${(performance.avg_pnl_pct || 0) >= 0 ? 'text-red-600' : 'text-emerald-600'}`}>
              {(performance.avg_pnl_pct || 0) >= 0 ? '+' : ''}{performance.avg_pnl_pct || 0}%
            </div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp size={16} className="text-red-400" />
              <span className="text-sm text-slate-500">最大盈利</span>
            </div>
            <div className="text-2xl font-bold text-red-600">+{performance.max_pnl_pct || 0}%</div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-2">
              <TrendingDown size={16} className="text-emerald-400" />
              <span className="text-sm text-slate-500">最大亏损</span>
            </div>
            <div className="text-2xl font-bold text-emerald-600">{performance.min_pnl_pct || 0}%</div>
          </div>
        </div>
      )}

      {/* Scan controls */}
      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-slate-700 mb-1">扫描股票</label>
            <input
              type="text"
              value={scanSymbols}
              onChange={(e) => setScanSymbols(e.target.value)}
              placeholder="输入代码，逗号分隔，留空扫描自选股"
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={handleScan}
              disabled={scanning}
              className="px-4 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50"
            >
              {scanning ? '扫描中...' : '开始扫描'}
            </button>
          </div>
        </div>
        {scanResult && (
          <div className="mt-3 text-sm">
            {scanResult.error ? (
              <span className="text-red-600">{scanResult.error}</span>
            ) : (
              <span className="text-slate-600">
                扫描 {scanResult.scanned} 只，发现 {scanResult.signals_found} 个信号
                {scanResult.signals_found > 0 && '（已保存到数据库）'}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Resonance Scan */}
      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-purple-500" />
            <span className="text-sm font-medium text-slate-700">多周期共振扫描</span>
            <span className="text-xs text-slate-400">日/周/月三周期同向</span>
          </div>
          <button
            onClick={handleResonanceScan}
            disabled={resonanceScanning}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 transition disabled:opacity-50"
          >
            {resonanceScanning ? '扫描中...' : '共振扫描'}
          </button>
        </div>
        {resonanceResult && (
          <div className="text-sm text-slate-600 mb-3">
            扫描 {resonanceResult.scanned} 只，共振 {resonanceResult.matched} 只
          </div>
        )}
        {resonanceResult && resonanceResult.results.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {resonanceResult.results.map((r, idx) => (
              <div key={idx} className="bg-slate-50 rounded-lg p-3 border border-slate-100">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-slate-800">{r.symbol}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    r.direction === 'bull' ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600'
                  }`}>
                    {r.direction === 'bull' ? '看多' : '看空'}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-xs mb-2">
                  <div>
                    <div className="text-slate-400">日线</div>
                    <div className={`font-medium ${r.daily_trend === 'bull' ? 'text-red-500' : r.daily_trend === 'bear' ? 'text-green-500' : 'text-slate-400'}`}>
                      {r.daily_trend === 'bull' ? '涨' : r.daily_trend === 'bear' ? '跌' : '平'}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-400">周线</div>
                    <div className={`font-medium ${r.weekly_trend === 'bull' ? 'text-red-500' : r.weekly_trend === 'bear' ? 'text-green-500' : 'text-slate-400'}`}>
                      {r.weekly_trend === 'bull' ? '涨' : r.weekly_trend === 'bear' ? '跌' : '平'}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-400">月线</div>
                    <div className={`font-medium ${r.monthly_trend === 'bull' ? 'text-red-500' : r.monthly_trend === 'bear' ? 'text-green-500' : 'text-slate-400'}`}>
                      {r.monthly_trend === 'bull' ? '涨' : r.monthly_trend === 'bear' ? '跌' : '平'}
                    </div>
                  </div>
                </div>
                <div className="text-xs text-slate-500">{r.description}</div>
              </div>
            ))}
          </div>
        )}
        {resonanceResult && resonanceResult.results.length === 0 && resonanceResult.scanned > 0 && (
          <div className="text-sm text-slate-400">未发现共振标的</div>
        )}
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
        <div className="flex items-center gap-2 mb-3">
          <Filter size={16} className="text-slate-400" />
          <span className="text-sm font-medium text-slate-700">筛选</span>
        </div>
        <div className="flex flex-wrap gap-3">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm"
          >
            <option value="">全部类型</option>
            <option value="BUY">买入</option>
            <option value="SELL">卖出</option>
            <option value="WATCH">关注</option>
            <option value="HOLD">观望</option>
            <option value="ALERT">预警</option>
          </select>
          <select
            value={filterStrategy}
            onChange={(e) => setFilterStrategy(e.target.value)}
            className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm"
          >
            <option value="">全部策略</option>
            <option value="signal_composer">多因子合成</option>
            {strategies.map((s) => (
              <option key={s.name} value={s.name}>
                {s.display_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Signal Lists */}
      <div className="space-y-4">
        {/* Daily Signals */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
            <Activity size={16} className="text-sky-500" />
            <h3 className="font-semibold text-slate-700">日线信号</h3>
            <span className="ml-auto text-xs text-slate-400">{dailySignals.length} 条</span>
          </div>
          <div className="divide-y divide-slate-50">
            {loading ? (
              <div className="p-8 text-center text-sm text-slate-400">加载中...</div>
            ) : dailySignals.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-400">暂无日线信号</div>
            ) : (
              dailySignals.map((signal) => (
                <SignalRow
                  key={signal.id || `${signal.symbol}-${signal.timestamp}-${signal.strategy}`}
                  signal={signal}
                  onAck={handleAck}
                  onDelete={handleDelete}
                  onTrack={handleTrack}
                  onClose={handleCloseSignal}
                />
              ))
            )}
          </div>
        </div>

        {/* Intraday Signals */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
            <Zap size={16} className="text-amber-500" />
            <h3 className="font-semibold text-slate-700">日内信号</h3>
            <span className="ml-auto text-xs text-slate-400">{intradaySignals.length} 条</span>
          </div>
          <div className="divide-y divide-slate-50">
            {loading ? (
              <div className="p-8 text-center text-sm text-slate-400">加载中...</div>
            ) : intradaySignals.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-400">暂无日内信号</div>
            ) : (
              intradaySignals.map((signal) => (
                <SignalRow
                  key={signal.id || `${signal.symbol}-${signal.timestamp}-${signal.strategy}`}
                  signal={signal}
                  onAck={handleAck}
                  onDelete={handleDelete}
                  onTrack={handleTrack}
                  onClose={handleCloseSignal}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function SignalRow({
  signal,
  onAck,
  onDelete,
  onTrack,
  onClose,
}: {
  signal: SignalItem
  onAck: (id: string) => void
  onDelete: (id: string) => void
  onTrack?: (id: string) => void
  onClose?: (id: string, status: string) => void
}) {
  const [showActions, setShowActions] = useState(false)

  return (
    <div className={`px-4 py-3 hover:bg-slate-50 transition ${signal.acknowledged ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <SignalBadge type={signal.signal_type} />
            <span className="text-sm font-medium text-slate-700">
              <Link to={`/stock/${signal.symbol}`} className="hover:text-sky-600 transition">
                {signal.symbol}
              </Link>
              {' '}
              {signal.name && signal.name !== signal.symbol && (
                <span className="text-slate-400">({signal.name})</span>
              )}
            </span>
            <span className="text-xs text-slate-400">{signal.timestamp}</span>
            {signal.strategy === 'signal_composer' && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-purple-50 text-purple-600 border border-purple-200">
                多因子合成
              </span>
            )}
          </div>
          <p className="text-sm text-slate-600">{signal.description}</p>
          <div className="flex items-center gap-4 mt-2">
            <ConfidenceBar value={signal.confidence} />
            <span className="text-xs text-slate-500">{signal.strategy}</span>
            {signal.price > 0 && (
              <span className="text-xs text-slate-500">价格: {signal.price.toFixed(2)}</span>
            )}
            {signal.target_price && (
              <span className="text-xs text-red-500">目标: {signal.target_price.toFixed(2)}</span>
            )}
            {signal.stop_loss && (
              <span className="text-xs text-red-500">止损: {signal.stop_loss.toFixed(2)}</span>
            )}
            {signal.status && signal.status !== 'open' && (
              <span className={`text-xs px-1.5 py-0.5 rounded ${
                signal.status === 'hit_target' ? 'bg-red-50 text-red-600 border border-red-200' :
                signal.status === 'hit_stop' ? 'bg-emerald-50 text-emerald-600 border border-emerald-200' :
                'bg-slate-50 text-slate-600 border border-slate-200'
              }`}>
                {signal.status === 'hit_target' ? '已止盈' : signal.status === 'hit_stop' ? '已止损' : signal.status}
              </span>
            )}
            {typeof signal.pnl_pct === 'number' && (
              <span className={`text-xs font-medium ${signal.pnl_pct >= 0 ? 'text-red-500' : 'text-emerald-500'}`}>
                {signal.pnl_pct >= 0 ? '+' : ''}{signal.pnl_pct.toFixed(2)}%
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          {signal.id && signal.status === 'open' && onTrack && (
            <button
              onClick={() => onTrack(signal.id!)}
              className="p-1.5 rounded hover:bg-slate-200 text-slate-400 hover:text-amber-600 transition"
              title="追踪绩效"
            >
              <Activity size={14} />
            </button>
          )}
          {signal.id && signal.status === 'open' && onClose && (
            <button
              onClick={() => setShowActions(!showActions)}
              className="p-1.5 rounded hover:bg-slate-200 text-slate-400 hover:text-purple-600 transition"
              title="平仓"
            >
              <Check size={14} />
            </button>
          )}
          {showActions && signal.id && onClose && (
            <div className="absolute right-0 mt-8 bg-white border border-slate-200 rounded-lg shadow-lg p-2 z-10 flex flex-col gap-1">
              <button
                onClick={() => { onClose(signal.id!, 'manual'); setShowActions(false) }}
                className="text-xs px-2 py-1 rounded hover:bg-slate-100 text-slate-600 text-left"
              >
                手动平仓
              </button>
              <button
                onClick={() => { onClose(signal.id!, 'hit_target'); setShowActions(false) }}
                className="text-xs px-2 py-1 rounded hover:bg-red-50 text-red-600 text-left"
              >
                标记止盈
              </button>
              <button
                onClick={() => { onClose(signal.id!, 'hit_stop'); setShowActions(false) }}
                className="text-xs px-2 py-1 rounded hover:bg-emerald-50 text-emerald-600 text-left"
              >
                标记止损
              </button>
            </div>
          )}
          {signal.id && !signal.acknowledged && (
            <button
              onClick={() => onAck(signal.id!)}
              className="p-1.5 rounded hover:bg-slate-200 text-slate-400 hover:text-sky-600 transition"
              title="确认"
            >
              <Check size={14} />
            </button>
          )}
          {signal.id && (
            <button
              onClick={() => onDelete(signal.id!)}
              className="p-1.5 rounded hover:bg-slate-200 text-slate-400 hover:text-red-600 transition"
              title="删除"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
