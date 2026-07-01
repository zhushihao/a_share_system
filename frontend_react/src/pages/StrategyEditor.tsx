import React, { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Code,
  Play,
  Save,
  FileText,
  Zap,
  Loader2,
  BookOpen,
  AlertTriangle,
  CheckCircle,
  ChevronRight,
  Lightbulb,
} from 'lucide-react'
import {
  fetchBacktestCustomTemplate,
  runBacktest,
} from '@/api/client'

interface StrategyExample {
  title: string
  description: string
  code: string
}

const STRATEGY_EXAMPLES: StrategyExample[] = [
  {
    title: '双均线策略',
    description: 'MA5 上穿 MA20 买入，MA5 下穿 MA20 卖出',
    code: JSON.stringify({
      rules: [
        {
          condition: { cross_up: [{ col: 'ma5' }, { col: 'ma20' }] },
          action: 'BUY',
          position_pct: 0.99,
          reason: 'MA5 上穿 MA20',
        },
        {
          condition: { cross_down: [{ col: 'ma5' }, { col: 'ma20' }] },
          action: 'SELL',
          reason: 'MA5 下穿 MA20',
        },
      ],
    }, null, 2),
  },
  {
    title: 'MACD 策略',
    description: 'MACD 金叉买入，死叉卖出',
    code: JSON.stringify({
      rules: [
        {
          condition: { cross_up: [{ col: 'macd_dif' }, { col: 'macd_dea' }] },
          action: 'BUY',
          position_pct: 0.99,
          reason: 'MACD 金叉',
        },
        {
          condition: { cross_down: [{ col: 'macd_dif' }, { col: 'macd_dea' }] },
          action: 'SELL',
          reason: 'MACD 死叉',
        },
      ],
    }, null, 2),
  },
  {
    title: 'KD 超卖策略',
    description: 'KD 在超卖区金叉买入，超买区死叉卖出',
    code: JSON.stringify({
      rules: [
        {
          condition: {
            and: [
              { cross_up: [{ col: 'kdj_k' }, { col: 'kdj_d' }] },
              { lt: [{ col: 'kdj_k' }, { const: 20 }] },
            ],
          },
          action: 'BUY',
          position_pct: 0.99,
          reason: 'KD 超卖金叉',
        },
        {
          condition: {
            and: [
              { cross_down: [{ col: 'kdj_k' }, { col: 'kdj_d' }] },
              { gt: [{ col: 'kdj_k' }, { const: 80 }] },
            ],
          },
          action: 'SELL',
          reason: 'KD 超买死叉',
        },
      ],
    }, null, 2),
  },
  {
    title: '布林带策略',
    description: '跌破下轨买入，突破上轨卖出',
    code: JSON.stringify({
      rules: [
        {
          condition: { lt: [{ col: 'close' }, { col: 'boll_down' }] },
          action: 'BUY',
          position_pct: 0.99,
          reason: '跌破布林下轨',
        },
        {
          condition: { gt: [{ col: 'close' }, { col: 'boll_up' }] },
          action: 'SELL',
          reason: '突破布林上轨',
        },
      ],
    }, null, 2),
  },
]

function StrategyEditor() {
  const [searchParams] = useSearchParams()
  const defaultSymbol = searchParams.get('symbol') || '000001'

  const [code, setCode] = useState('')
  const [symbol, setSymbol] = useState(defaultSymbol)
  const [startDate, setStartDate] = useState('2024-01-01')
  const [endDate, setEndDate] = useState('2024-12-31')
  const [initialCash, setInitialCash] = useState(100000)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [selectedExample, setSelectedExample] = useState<number | null>(null)
  const [savedStrategies, setSavedStrategies] = useState<{ name: string; code: string }[]>([])
  const [strategyName, setStrategyName] = useState('')

  useEffect(() => {
    loadTemplate()
    loadSavedStrategies()
  }, [])

  const loadTemplate = async () => {
    try {
      const data = await fetchBacktestCustomTemplate()
      if (data.template) {
        setCode(data.template)
      }
    } catch (e) {
      console.error('Failed to load template', e)
    }
  }

  const loadSavedStrategies = () => {
    try {
      const saved = localStorage.getItem('quant_workbench_strategies')
      if (saved) {
        setSavedStrategies(JSON.parse(saved))
      }
    } catch (e) {
      console.error('Failed to load saved strategies', e)
    }
  }

  const handleSaveStrategy = () => {
    if (!strategyName.trim() || !code.trim()) return
    const updated = [...savedStrategies, { name: strategyName.trim(), code }]
    setSavedStrategies(updated)
    localStorage.setItem('quant_workbench_strategies', JSON.stringify(updated))
    setStrategyName('')
  }

  const handleLoadExample = (index: number) => {
    setSelectedExample(index)
    setCode(STRATEGY_EXAMPLES[index].code)
  }

  const handleRun = async () => {
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const data = await runBacktest({
        symbol,
        strategy_name: 'custom',
        start_date: startDate,
        end_date: endDate,
        initial_cash: initialCash,
        custom_code: code,
      })
      if (data.result) {
        setResult(data.result)
      } else if (data.error) {
        setError(data.error)
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || '运行失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <Code size={22} />
          策略编辑器
        </h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Examples & Saved */}
        <div className="lg:col-span-1 space-y-4">
          {/* Quick Examples */}
          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
            <h3 className="font-medium text-slate-700 mb-3 flex items-center gap-2">
              <BookOpen size={16} />
              策略示例
            </h3>
            <div className="space-y-2">
              {STRATEGY_EXAMPLES.map((example, i) => (
                <button
                  key={i}
                  onClick={() => handleLoadExample(i)}
                  className={`w-full text-left p-3 rounded-lg transition text-sm ${
                    selectedExample === i
                      ? 'bg-sky-50 border border-sky-200'
                      : 'bg-slate-50 hover:bg-slate-100 border border-transparent'
                  }`}
                >
                  <p className="font-medium text-slate-700">{example.title}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{example.description}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Saved Strategies */}
          {savedStrategies.length > 0 && (
            <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
              <h3 className="font-medium text-slate-700 mb-3 flex items-center gap-2">
                <Save size={16} />
                已保存策略
              </h3>
              <div className="space-y-2">
                {savedStrategies.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => setCode(s.code)}
                    className="w-full text-left p-2 rounded-lg bg-slate-50 hover:bg-slate-100 transition text-sm"
                  >
                    {s.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Backtest Config */}
          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
            <h3 className="font-medium text-slate-700 mb-3 flex items-center gap-2">
              <Zap size={16} />
              回测配置
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">股票代码</label>
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-slate-500 mb-1">起始</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">结束</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">初始资金</label>
                <input
                  type="number"
                  value={initialCash}
                  onChange={(e) => setInitialCash(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>
              <button
                onClick={handleRun}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                {loading ? '运行中...' : '运行回测'}
              </button>
            </div>
          </div>
        </div>

        {/* Right: Code Editor & Results */}
        <div className="lg:col-span-2 space-y-4">
          {/* Code Editor */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
              <div className="flex items-center gap-2">
                <Code size={16} className="text-slate-400" />
                <span className="text-sm font-medium text-slate-700">策略代码</span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={strategyName}
                  onChange={(e) => setStrategyName(e.target.value)}
                  placeholder="策略名称"
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
                <button
                  onClick={handleSaveStrategy}
                  className="flex items-center gap-1 px-3 py-1.5 bg-slate-100 text-slate-600 rounded-lg text-sm hover:bg-slate-200 transition"
                >
                  <Save size={14} />
                  保存
                </button>
              </div>
            </div>
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full p-4 font-mono text-sm bg-slate-900 text-slate-200 rounded-b-xl focus:outline-none resize-none h-80"
              spellCheck={false}
            />
          </div>

          {/* Error */}
          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-center gap-2">
              <AlertTriangle size={16} />
              {error}
            </div>
          )}

          {/* Results */}
          {result && (
            <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200 space-y-4">
              <div className="flex items-center gap-2">
                <CheckCircle size={18} className="text-emerald-500" />
                <h3 className="font-medium text-slate-700">回测结果</h3>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <ResultCard label="总收益率" value={`${(result.total_return * 100).toFixed(2)}%`} positive={result.total_return > 0} />
                <ResultCard label="年化收益率" value={`${(result.annual_return * 100).toFixed(2)}%`} positive={result.annual_return > 0} />
                <ResultCard label="最大回撤" value={`${(result.max_drawdown * 100).toFixed(2)}%`} positive={false} />
                <ResultCard label="夏普比率" value={result.sharpe_ratio.toFixed(2)} positive={result.sharpe_ratio > 1} />
                <ResultCard label="胜率" value={`${(result.win_rate * 100).toFixed(1)}%`} positive={result.win_rate > 0.5} />
                <ResultCard label="交易次数" value={String(result.total_trades)} />
                <ResultCard label="盈亏比" value={result.profit_loss_ratio.toFixed(2)} positive={result.profit_loss_ratio > 1} />
                <ResultCard label="平均持仓" value={`${result.avg_holding_days.toFixed(1)}天`} />
              </div>

              {result.trades && result.trades.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-slate-700 mb-2">交易记录</h4>
                  <div className="overflow-auto max-h-48 border border-slate-200 rounded-lg">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200">
                          <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">日期</th>
                          <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">操作</th>
                          <th className="text-right py-2 px-3 text-xs font-medium text-slate-500">价格</th>
                          <th className="text-right py-2 px-3 text-xs font-medium text-slate-500">数量</th>
                          <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">理由</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.trades.map((trade: any, i: number) => (
                          <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                            <td className="py-2 px-3 text-slate-600">{trade.date}</td>
                            <td className="py-2 px-3">
                              <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                                trade.action === 'BUY' ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'
                              }`}>
                                {trade.action === 'BUY' ? '买入' : '卖出'}
                              </span>
                            </td>
                            <td className="py-2 px-3 text-right text-slate-600">{trade.price.toFixed(2)}</td>
                            <td className="py-2 px-3 text-right text-slate-600">{trade.size}</td>
                            <td className="py-2 px-3 text-slate-500 text-xs">{trade.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Documentation */}
          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
            <h3 className="font-medium text-slate-700 mb-3 flex items-center gap-2">
              <Lightbulb size={16} />
              编写指南
            </h3>
            <div className="text-sm text-slate-600 space-y-2">
              <p>1. 策略代码必须是合法 JSON，顶层为 <code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">{'{ "rules": [...] }'}</code></p>
              <p>2. 每条规则包含 <code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">condition</code>、<code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">action</code>（BUY/SELL/HOLD）和可选 <code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">reason</code></p>
              <p>3. 数值节点：<code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">{'{ col: "ma5", lag: 0 }'}</code> / <code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">{'{ param: "short_ma", default: 5 }'}</code> / <code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">{'{ const: 20 }'}</code></p>
              <p>4. 条件：<code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">cross_up</code>、<code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">cross_down</code>、<code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">gt/gte/lt/lte/eq</code>、<code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">and/or/not</code>、<code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">in_range</code></p>
              <p>5. BUY 可通过 <code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">position_pct</code> 控制仓位，默认 0.99；交易价格默认当前收盘价</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function ResultCard({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  const colorClass = positive === undefined ? 'text-slate-700' : positive ? 'text-red-500' : 'text-emerald-600'
  return (
    <div className="p-3 bg-slate-50 rounded-lg">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`text-lg font-semibold ${colorClass}`}>{value}</p>
    </div>
  )
}

export default React.memo(StrategyEditor)
