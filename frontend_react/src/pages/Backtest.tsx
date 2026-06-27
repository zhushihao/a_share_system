import React, { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Play,
  Save,
  Trash2,
  TrendingUp,
  TrendingDown,
  Activity,
  Target,
  Clock,
  BarChart3,
  ChevronDown,
  ChevronUp,
  Loader2,
  FileText,
  Settings as SettingsIcon,
  Code,
} from 'lucide-react'
import {
  fetchBacktestStrategies,
  runBacktest,
  fetchBacktestResults,
  deleteBacktestResult,
  fetchBacktestDetail,
} from '@/api/client'

interface StrategyTemplate {
  id: string
  name: string
  description: string
  params: Record<string, { type: string; default: any; min: number; max: number; label: string }>
  default_params: Record<string, any>
}

interface BacktestResult {
  id?: string
  strategy_name: string
  symbols: string[]
  start_date: string
  end_date: string
  initial_cash: number
  final_value: number
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe_ratio: number
  win_rate: number
  profit_loss_ratio: number
  total_trades: number
  win_trades: number
  loss_trades: number
  avg_holding_days: number
  equity_curve: Array<{
    date: string
    total_value: number
    equity_return: number
  }>
  trades: Array<{
    date: string
    action: string
    symbol: string
    price: number
    size: number
    reason: string
  }>
  monthly_returns: Record<string, number>
  params: Record<string, any>
  error?: string
}

export default function Backtest() {
  const [searchParams] = useSearchParams()
  const defaultSymbol = searchParams.get('symbol') || '000001'

  const [strategies, setStrategies] = useState<StrategyTemplate[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState('dual_ma')
  const [symbol, setSymbol] = useState(defaultSymbol)
  const [startDate, setStartDate] = useState('2024-01-01')
  const [endDate, setEndDate] = useState('2024-12-31')
  const [initialCash, setInitialCash] = useState(100000)
  const [commissionRate, setCommissionRate] = useState(0.0003)
  const [slippage, setSlippage] = useState(0.001)
  const [params, setParams] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [history, setHistory] = useState<any[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'equity' | 'trades' | 'monthly'>('overview')
  const [showHistory, setShowHistory] = useState(true)
  const [customCode, setCustomCode] = useState('')
  const [isCustom, setIsCustom] = useState(false)

  useEffect(() => {
    loadStrategies()
    loadHistory()
  }, [])

  useEffect(() => {
    const strategy = strategies.find((s) => s.id === selectedStrategy)
    if (strategy) {
      setParams(strategy.default_params)
    }
  }, [selectedStrategy, strategies])

  const loadStrategies = async () => {
    try {
      const data = await fetchBacktestStrategies()
      setStrategies(data.strategies || [])
    } catch (e) {
      console.error('Failed to load strategies', e)
    }
  }

  const loadHistory = async () => {
    try {
      const data = await fetchBacktestResults()
      setHistory(data.results || [])
    } catch (e) {
      console.error('Failed to load history', e)
    }
  }

  const handleRun = async () => {
    setLoading(true)
    setResult(null)
    try {
      const data = await runBacktest({
        symbol,
        strategy_name: isCustom ? 'custom' : selectedStrategy,
        start_date: startDate,
        end_date: endDate,
        initial_cash: initialCash,
        commission_rate: commissionRate,
        slippage,
        params,
        custom_code: isCustom ? customCode : undefined,
      })
      if (data.result) {
        setResult(data.result)
        loadHistory()
      }
    } catch (e) {
      console.error('Backtest failed', e)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除此回测记录？')) return
    try {
      await deleteBacktestResult(id)
      loadHistory()
      if (result?.id === id) setResult(null)
    } catch (e) {
      console.error('Delete failed', e)
    }
  }

  const handleLoadResult = async (id: string) => {
    try {
      const data = await fetchBacktestDetail(id)
      if (data.result?.result_json) {
        setResult(data.result.result_json)
      }
    } catch (e) {
      console.error('Load result failed', e)
    }
  }

  const currentStrategy = strategies.find((s) => s.id === selectedStrategy)

  // 权益曲线 SVG
  const equityCurveSvg = useCallback(() => {
    if (!result?.equity_curve?.length) return null
    const data = result.equity_curve
    const width = 800
    const height = 300
    const padding = 40
    const values = data.map((d) => d.total_value)
    const minVal = Math.min(...values) * 0.95
    const maxVal = Math.max(...values) * 1.05
    const xScale = (i: number) => padding + (i / (data.length - 1)) * (width - 2 * padding)
    const yScale = (v: number) => height - padding - ((v - minVal) / (maxVal - minVal)) * (height - 2 * padding)

    const pathD = data
      .map((d, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(d.total_value)}`)
      .join(' ')

    const initialY = yScale(result.initial_cash)

    return (
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-64">
        {/* Grid */}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <line
            key={t}
            x1={padding}
            y1={padding + t * (height - 2 * padding)}
            x2={width - padding}
            y2={padding + t * (height - 2 * padding)}
            stroke="#e2e8f0"
            strokeWidth={1}
          />
        ))}
        {/* Initial cash line */}
        <line
          x1={padding}
          y1={initialY}
          x2={width - padding}
          y2={initialY}
          stroke="#94a3b8"
          strokeWidth={1}
          strokeDasharray="4 4"
        />
        {/* Equity curve */}
        <path d={pathD} fill="none" stroke="#0ea5e9" strokeWidth={2} />
        {/* Start and end points */}
        <circle cx={xScale(0)} cy={yScale(data[0].total_value)} r={4} fill="#0ea5e9" />
        <circle cx={xScale(data.length - 1)} cy={yScale(data[data.length - 1].total_value)} r={4} fill="#0ea5e9" />
      </svg>
    )
  }, [result])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <BarChart3 size={22} />
          回测中心
        </h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Config Panel */}
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
            <h3 className="font-medium text-slate-700 mb-4 flex items-center gap-2">
              <SettingsIcon size={16} />
              回测配置
            </h3>

            {/* Strategy Type */}
            <div className="space-y-3">
              <div className="flex gap-2">
                <button
                  onClick={() => setIsCustom(false)}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition ${
                    !isCustom ? 'bg-sky-600 text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  预设策略
                </button>
                <button
                  onClick={() => setIsCustom(true)}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition ${
                    isCustom ? 'bg-sky-600 text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  <Code size={14} className="inline mr-1" />
                  自定义
                </button>
              </div>

              {!isCustom ? (
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">选择策略</label>
                  <select
                    value={selectedStrategy}
                    onChange={(e) => setSelectedStrategy(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    {strategies.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} — {s.description}
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">策略代码</label>
                  <textarea
                    value={customCode}
                    onChange={(e) => setCustomCode(e.target.value)}
                    placeholder='{ "rules": [{ "condition": { "cross_up": [{"col":"ma5"},{"col":"ma20"}] }, "action": "BUY" }] }'
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-500 h-32 resize-none"
                  />
                  <p className="text-xs text-slate-400 mt-1">请输入 JSON 声明式 DSL，不再执行 Python 代码</p>
                </div>
              )}

              {/* Symbol */}
              <div>
                <label className="block text-sm font-medium text-slate-600 mb-1">股票代码</label>
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              {/* Date Range */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">起始日期</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">结束日期</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </div>

              {/* Initial Cash */}
              <div>
                <label className="block text-sm font-medium text-slate-600 mb-1">初始资金</label>
                <input
                  type="number"
                  value={initialCash}
                  onChange={(e) => setInitialCash(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              {/* Commission & Slippage */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">手续费率</label>
                  <input
                    type="number"
                    step={0.0001}
                    value={commissionRate}
                    onChange={(e) => setCommissionRate(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">滑点率</label>
                  <input
                    type="number"
                    step={0.0001}
                    value={slippage}
                    onChange={(e) => setSlippage(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </div>

              {/* Strategy Params */}
              {!isCustom && currentStrategy?.params && (
                <div className="pt-2 border-t border-slate-100">
                  <label className="block text-sm font-medium text-slate-600 mb-2">策略参数</label>
                  <div className="space-y-2">
                    {Object.entries(currentStrategy.params).map(([key, config]) => (
                      <div key={key}>
                        <label className="block text-xs text-slate-500 mb-1">{config.label}</label>
                        <input
                          type="number"
                          min={config.min}
                          max={config.max}
                          value={params[key] ?? config.default}
                          onChange={(e) =>
                            setParams((prev) => ({ ...prev, [key]: Number(e.target.value) }))
                          }
                          className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Run Button */}
              <button
                onClick={handleRun}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                {loading ? '运行中...' : '运行回测'}
              </button>
            </div>
          </div>

          {/* History */}
          {showHistory && (
            <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-medium text-slate-700 flex items-center gap-2">
                  <FileText size={16} />
                  历史记录
                </h3>
                <button
                  onClick={() => setShowHistory(false)}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <ChevronUp size={16} />
                </button>
              </div>
              <div className="space-y-2 max-h-64 overflow-auto">
                {history.length === 0 && (
                  <p className="text-sm text-slate-400 text-center py-4">暂无回测记录</p>
                )}
                {history.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between p-2 rounded-lg bg-slate-50 hover:bg-slate-100 cursor-pointer transition"
                    onClick={() => handleLoadResult(item.id)}
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-700 truncate">{item.strategy_name}</p>
                      <p className="text-xs text-slate-400">
                        {item.start_date} ~ {item.end_date}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500">{item.symbols}</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDelete(item.id)
                        }}
                        className="p-1 text-slate-400 hover:text-red-500 transition"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {!showHistory && (
            <button
              onClick={() => setShowHistory(true)}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50 transition"
            >
              <ChevronDown size={16} />
              显示历史记录
            </button>
          )}
        </div>

        {/* Right: Results */}
        <div className="lg:col-span-2">
          {result ? (
            <div className="space-y-4">
              {/* Error */}
              {result.error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">
                  {result.error}
                </div>
              )}

              {/* Metrics Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricCard
                  label="总收益率"
                  value={`${(result.total_return * 100).toFixed(2)}%`}
                  positive={result.total_return > 0}
                  icon={<TrendingUp size={16} />}
                />
                <MetricCard
                  label="年化收益率"
                  value={`${(result.annual_return * 100).toFixed(2)}%`}
                  positive={result.annual_return > 0}
                  icon={<Activity size={16} />}
                />
                <MetricCard
                  label="最大回撤"
                  value={`${(result.max_drawdown * 100).toFixed(2)}%`}
                  positive={false}
                  icon={<TrendingDown size={16} />}
                />
                <MetricCard
                  label="夏普比率"
                  value={result.sharpe_ratio.toFixed(2)}
                  positive={result.sharpe_ratio > 1}
                  icon={<Target size={16} />}
                />
                <MetricCard
                  label="胜率"
                  value={`${(result.win_rate * 100).toFixed(1)}%`}
                  positive={result.win_rate > 0.5}
                  icon={<BarChart3 size={16} />}
                />
                <MetricCard
                  label="总交易次数"
                  value={String(result.total_trades)}
                  icon={<FileText size={16} />}
                />
                <MetricCard
                  label="盈利/亏损"
                  value={`${result.win_trades}/${result.loss_trades}`}
                  positive={result.win_trades > result.loss_trades}
                  icon={<TrendingUp size={16} />}
                />
                <MetricCard
                  label="平均持仓天数"
                  value={`${result.avg_holding_days.toFixed(1)}天`}
                  icon={<Clock size={16} />}
                />
              </div>

              {/* Tabs */}
              <div className="bg-white rounded-xl shadow-sm border border-slate-200">
                <div className="flex border-b border-slate-200">
                  {[
                    { key: 'overview', label: '概览' },
                    { key: 'equity', label: '权益曲线' },
                    { key: 'trades', label: '交易记录' },
                    { key: 'monthly', label: '月度矩阵' },
                  ].map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => setActiveTab(tab.key as any)}
                      className={`px-4 py-3 text-sm font-medium transition border-b-2 ${
                        activeTab === tab.key
                          ? 'border-sky-600 text-sky-600'
                          : 'border-transparent text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                <div className="p-4">
                  {activeTab === 'overview' && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="p-3 bg-slate-50 rounded-lg">
                          <p className="text-xs text-slate-500">初始资金</p>
                          <p className="text-lg font-semibold text-slate-800">
                            ¥{result.initial_cash.toLocaleString()}
                          </p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-lg">
                          <p className="text-xs text-slate-500">最终资产</p>
                          <p className={`text-lg font-semibold ${result.final_value >= result.initial_cash ? 'text-emerald-600' : 'text-red-500'}`}>
                            ¥{result.final_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                          </p>
                        </div>
                      </div>
                      <div className="text-sm text-slate-600">
                        <p><span className="text-slate-400">策略：</span>{result.strategy_name}</p>
                        <p><span className="text-slate-400">标的：</span>{result.symbols.join(', ')}</p>
                        <p><span className="text-slate-400">区间：</span>{result.start_date} ~ {result.end_date}</p>
                        <p><span className="text-slate-400">参数：</span>{JSON.stringify(result.params)}</p>
                      </div>
                    </div>
                  )}

                  {activeTab === 'equity' && (
                    <div>
                      {equityCurveSvg()}
                      <p className="text-xs text-slate-400 text-center mt-2">权益曲线（总资产 vs 时间）</p>
                    </div>
                  )}

                  {activeTab === 'trades' && (
                    <div className="overflow-auto max-h-96">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-200">
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">日期</th>
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">操作</th>
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">代码</th>
                            <th className="text-right py-2 px-3 text-xs font-medium text-slate-500">价格</th>
                            <th className="text-right py-2 px-3 text-xs font-medium text-slate-500">数量</th>
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">理由</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.trades.map((trade, i) => (
                            <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                              <td className="py-2 px-3 text-slate-600">{trade.date}</td>
                              <td className="py-2 px-3">
                                <span
                                  className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                                    trade.action === 'BUY'
                                      ? 'bg-emerald-100 text-emerald-700'
                                      : 'bg-red-100 text-red-700'
                                  }`}
                                >
                                  {trade.action === 'BUY' ? '买入' : '卖出'}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-slate-600">{trade.symbol}</td>
                              <td className="py-2 px-3 text-right text-slate-600">{trade.price.toFixed(2)}</td>
                              <td className="py-2 px-3 text-right text-slate-600">{trade.size}</td>
                              <td className="py-2 px-3 text-slate-500 text-xs">{trade.reason}</td>
                            </tr>
                          ))}
                          {result.trades.length === 0 && (
                            <tr>
                              <td colSpan={6} className="py-8 text-center text-slate-400 text-sm">
                                无交易记录
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {activeTab === 'monthly' && (
                    <div>
                      {Object.keys(result.monthly_returns).length === 0 ? (
                        <p className="text-center text-slate-400 py-8">无月度数据</p>
                      ) : (
                        <div className="grid grid-cols-4 md:grid-cols-6 gap-2">
                          {Object.entries(result.monthly_returns)
                            .sort(([a], [b]) => a.localeCompare(b))
                            .map(([month, ret]) => (
                              <div
                                key={month}
                                className={`p-2 rounded-lg text-center ${
                                  ret > 0
                                    ? 'bg-emerald-50 text-emerald-700'
                                    : ret < 0
                                    ? 'bg-red-50 text-red-700'
                                    : 'bg-slate-50 text-slate-500'
                                }`}
                              >
                                <p className="text-xs text-slate-400">{month}</p>
                                <p className="text-sm font-semibold">{(ret * 100).toFixed(2)}%</p>
                              </div>
                            ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl p-12 shadow-sm border border-slate-200 text-center">
              <BarChart3 size={48} className="mx-auto text-slate-300 mb-4" />
              <p className="text-slate-500 text-sm">配置回测参数并点击「运行回测」</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function MetricCard({
  label,
  value,
  positive,
  icon,
}: {
  label: string
  value: string
  positive?: boolean
  icon: React.ReactNode
}) {
  const colorClass =
    positive === undefined
      ? 'text-slate-700'
      : positive
      ? 'text-emerald-600'
      : 'text-red-500'

  return (
    <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-slate-400">{label}</span>
        <span className="text-slate-300">{icon}</span>
      </div>
      <p className={`text-lg font-semibold ${colorClass}`}>{value}</p>
    </div>
  )
}
