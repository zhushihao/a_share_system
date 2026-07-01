import React, { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, TrendingUp, TrendingDown, Activity, Shield, Target, RefreshCw, Clock, BookOpen, BarChart3, ChevronLeft, ChevronRight } from 'lucide-react'
import {
  fetchQuote,
  fetchOHLCV,
  fetchIndicators,
  fetchScore,
  fetchPatterns,
  fetchVolumeAnalysis,
  fetchSupportResistance,
  fetchQuotesBatch,
  fetchOrderbook,
  fetchProfile,
  fetchIntraday,
  fetchSettings,
  searchStocks,
  fetchWatchlist,
} from '@/api/client'
import TradingViewChart from '@/components/TradingViewChart'
import IntradayChart from '@/components/IntradayChart'
import IndicatorPanel from '@/components/IndicatorPanel'
import { fetchSignal, fetchResonance } from '@/api/client'
import type { StandardQuote, OHLCVRecord, TechIndicators, PatternData, VolumeNodeData, SupportResistanceData, TradingSignal, ResonanceData } from '@/types'

const F10_LABELS: Record<string, string> = {
  industry: '所属行业',
  total_capital: '总股本',
  circulating_capital: '流通股本',
  pe: '市盈率',
  pb: '市净率',
  eps: '每股收益',
  bvps: '每股净资产',
  roe: '净资产收益率',
  revenue: '营业收入',
  profit: '净利润',
  dividend: '股息率',
  market_cap: '总市值',
  circulating_market_cap: '流通市值',
  turnover_rate: '换手率',
  amplitude: '振幅',
  volume_ratio: '量比',
  fiv_min_rise: '5分钟涨幅',
}

function formatVolume(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '-'
  const n = Number(value)
  if (n >= 100000000) return `${(n / 100000000).toFixed(2)}亿`
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`
  return n.toLocaleString()
}

function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>()
  const [quote, setQuote] = useState<StandardQuote | null>(null)
  const [ohlcv, setOhlcv] = useState<OHLCVRecord[]>([])
  const [chartData, setChartData] = useState<OHLCVRecord[]>([])
  const [indicators, setIndicators] = useState<TechIndicators>({})
  const [indicatorLabels, setIndicatorLabels] = useState<Record<string, string>>({})
  const [score, setScore] = useState<{ score: number; level: string } | null>(null)
  const [patterns, setPatterns] = useState<PatternData[]>([])
  const [volumeAnalysis, setVolumeAnalysis] = useState<VolumeNodeData[]>([])
  const [supportResistance, setSupportResistance] = useState<SupportResistanceData | undefined>(undefined)
  const [signal, setSignal] = useState<TradingSignal | null>(null)
  const [resonance, setResonance] = useState<ResonanceData | null>(null)
  const [orderbook, setOrderbook] = useState<any>(null)
  const [profile, setProfile] = useState<any>(null)
  const [intraday, setIntraday] = useState<any>(null)
  const [activeIndicator, setActiveIndicator] = useState<'macd' | 'kdj' | 'rsi'>('macd')
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const [isRefreshing, setIsRefreshing] = useState(false)
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [chartIndicators, setChartIndicators] = useState({
    ma5: true,
    ma20: true,
    ma60: false,
    boll: false,
    supportResistance: true,
  })

  const [period, setPeriod] = useState<'minute' | 'daily' | 'weekly' | 'monthly'>('daily')
  const [viewMode, setViewMode] = useState<'kline' | 'intraday'>('kline')
  const [adjustMode, setAdjustMode] = useState<string>('qfq')
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([])
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const signalRef = useRef<HTMLDivElement>(null)
  const [highlightSignal, setHighlightSignal] = useState(false)

  // 从信号列表跳转时高亮并滚动到交易信号区域
  useEffect(() => {
    if (searchParams.get('signal_id') && signalRef.current) {
      setHighlightSignal(true)
      signalRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
      const timer = setTimeout(() => setHighlightSignal(false), 3000)
      return () => clearTimeout(timer)
    }
  }, [searchParams])

  // 加载用户默认复权设置
  useEffect(() => {
    fetchSettings()
      .then((settings) => {
        const adj = settings?.default_adjust
        if (adj && ['qfq', 'hfq', 'none'].includes(adj)) {
          setAdjustMode(adj)
        }
      })
      .catch(() => {})
  }, [])

  // 加载当前自选股列表（用于上一只/下一只导航）
  useEffect(() => {
    async function loadWatchlist() {
      try {
        const data = await fetchWatchlist()
        const symbols = (data?.items || []).map((s: any) => s.symbol).filter(Boolean)
        setWatchlistSymbols(symbols)
      } catch (e) {
        console.error('Failed to load watchlist for navigation', e)
      }
    }
    loadWatchlist()
  }, [symbol])

  const currentIndex = symbol ? watchlistSymbols.indexOf(symbol) : -1
  const prevSymbol = currentIndex > 0 ? watchlistSymbols[currentIndex - 1] : null
  const nextSymbol = currentIndex >= 0 && currentIndex < watchlistSymbols.length - 1 ? watchlistSymbols[currentIndex + 1] : null

  async function fetchStockName(symbol: string): Promise<string | null> {
    try {
      const data = await searchStocks(symbol)
      const matches = data?.stocks || []
      const exact = matches.find((s: any) => s?.code === symbol)
      return exact?.name || matches[0]?.name || null
    } catch (e) {
      return null
    }
  }

  const loadData = useCallback(async () => {
    if (!symbol) return
    setIsRefreshing(true)
    try {
      const [q, o, i, s, p, v, sr, sig, res, ob, pr, id] = await Promise.all([
        fetchQuote(symbol).catch(() => null),
        fetchOHLCV(symbol, { period, limit: 120, adjust: adjustMode }),
        fetchIndicators(symbol, { period, limit: 120, adjust: adjustMode }),
        fetchScore(symbol).catch(() => null),
        fetchPatterns(symbol, { period, limit: 120, adjust: adjustMode }),
        fetchVolumeAnalysis(symbol, { period, limit: 120, adjust: adjustMode }),
        fetchSupportResistance(symbol, { period, limit: 120, adjust: adjustMode }),
        fetchSignal(symbol, { period, adjust: adjustMode }).catch(() => null),
        fetchResonance(symbol).catch(() => null),
        fetchOrderbook(symbol).catch(() => null),
        fetchProfile(symbol).catch(() => null),
        fetchIntraday(symbol).catch(() => null),
      ])
      // 降级：如果 fetchQuote 返回空，从 OHLCV 构造 quote
      let quote = q
      if (!quote && o.data && o.data.length > 0) {
        const name = await fetchStockName(symbol)
        const latest = o.data[o.data.length - 1]
        quote = {
          symbol: symbol,
          name: name,
          timestamp: new Date().toISOString(),
          open: latest.open || 0,
          high: latest.high || 0,
          low: latest.low || 0,
          close: latest.close || 0,
          volume: latest.volume || 0,
          amount: null,
          source: 'ohlcv-fallback',
          freq: period,
        }
      }
      setQuote(quote)
      setOhlcv(o.data || [])
      setChartData(i.data || o.data || [])
      setIndicators(i.indicators || {})
      setIndicatorLabels(i.labels || {})
      setScore(s)
      setPatterns(p.patterns || [])
      setVolumeAnalysis(v.nodes || [])
      setSupportResistance(sr)
      setSignal(sig || null)
      setResonance(res || null)
      setOrderbook(ob)
      setProfile(pr)
      setIntraday(id)
      setLastUpdated(new Date().toLocaleTimeString())
    } catch (e) {
      console.error(e)
    } finally {
      setIsRefreshing(false)
      setLoading(false)
    }
  }, [symbol, period, adjustMode])

  // 初始加载
  useEffect(() => {
    loadData()
  }, [loadData])

  // 定时刷新：每30秒刷新一次，页面不可见时暂停
  useEffect(() => {
    function startTimer() {
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current)
      refreshTimerRef.current = setInterval(() => {
        loadData()
      }, 30000)
    }
    function stopTimer() {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current)
        refreshTimerRef.current = null
      }
    }
    function handleVisibilityChange() {
      if (document.hidden) {
        stopTimer()
      } else {
        startTimer()
        loadData()
      }
    }

    startTimer()
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      stopTimer()
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [loadData])

  if (loading) {
    return <div className="text-center py-12 text-slate-400">加载中...</div>
  }

  if (!quote) {
    return <div className="text-center py-12 text-slate-400">未找到股票数据</div>
  }

  const basePrice = quote.pre_close ?? quote.open
  const change = quote.close - basePrice
  const changePct = basePrice ? (change / basePrice) * 100 : 0
  const isUp = change >= 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/watchlist" className="p-2 hover:bg-slate-100 rounded-lg transition">
            <ArrowLeft size={20} className="text-slate-500" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-slate-800">
              {quote.name || symbol} <span className="text-sm font-normal text-slate-400">{symbol}</span>
            </h1>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Clock size={12} />
              <span>数据更新于 {lastUpdated || '未知'}</span>
              {quote?.date && <span>· 最新交易日 {quote.date}</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {currentIndex >= 0 && (
            <span className="text-xs text-slate-400 hidden sm:inline">
              自选股 {currentIndex + 1}/{watchlistSymbols.length}
            </span>
          )}
          <button
            onClick={() => prevSymbol && navigate(`/stock/${prevSymbol}`)}
            disabled={!prevSymbol}
            className="p-2 hover:bg-slate-100 rounded-lg transition disabled:opacity-30 disabled:cursor-not-allowed"
            title="上一只"
          >
            <ChevronLeft size={20} className="text-slate-500" />
          </button>
          <button
            onClick={() => nextSymbol && navigate(`/stock/${nextSymbol}`)}
            disabled={!nextSymbol}
            className="p-2 hover:bg-slate-100 rounded-lg transition disabled:opacity-30 disabled:cursor-not-allowed"
            title="下一只"
          >
            <ChevronRight size={20} className="text-slate-500" />
          </button>
          <button
            onClick={loadData}
            disabled={isRefreshing}
            className="flex items-center gap-1 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50 transition disabled:opacity-50"
          >
            <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
            {isRefreshing ? '刷新中...' : '刷新'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 价格卡片 */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm text-slate-500">最新价</span>
            {isUp ? <TrendingUp size={20} className="text-up" /> : <TrendingDown size={20} className="text-down" />}
          </div>
          <div className={`text-3xl font-bold font-mono ${isUp ? 'text-up' : 'text-down'}`}>
            {quote.close.toFixed(2)}
          </div>
          <div className={`text-sm mt-2 font-mono ${isUp ? 'text-up' : 'text-down'}`}>
            {change >= 0 ? '+' : ''}
            {change.toFixed(2)} ({changePct >= 0 ? '+' : ''}
            {changePct.toFixed(2)}%)
          </div>
          <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-slate-100">
            <div>
              <div className="text-xs text-slate-400">今开</div>
              <div className="text-sm font-medium font-mono">{quote.open.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">最高</div>
              <div className="text-sm font-medium font-mono">{quote.high.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">最低</div>
              <div className="text-sm font-medium font-mono">{quote.low.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">成交量</div>
              <div className="text-sm font-medium font-mono">{formatVolume(quote.volume)}</div>
            </div>
          </div>

          {/* 五档行情 */}
          {orderbook && orderbook.bids && orderbook.bids.length > 0 ? (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <div className="text-xs text-slate-400 mb-2 flex items-center gap-1">
                <BarChart3 size={12} />
                五档行情
                {orderbook.source === 'simulated' && (
                  <span className="ml-1 px-1 py-0.5 bg-amber-100 text-amber-700 rounded text-[10px]">模拟数据</span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="space-y-1">
                  {orderbook.asks.slice().reverse().map((ask: any) => (
                    <div key={`ask-${ask.level}`} className={`flex justify-between ${ask.level === 1 ? 'text-red-500 font-medium' : 'text-slate-500'}`}>
                      <span>卖{ask.level}</span>
                      <span className="font-mono">{ask.price > 0 ? ask.price.toFixed(2) : '-'} / {ask.volume > 0 ? ask.volume : '-'}</span>
                    </div>
                  ))}
                </div>
                <div className="space-y-1">
                  {orderbook.bids.map((bid: any) => (
                    <div key={`bid-${bid.level}`} className={`flex justify-between ${bid.level === 1 ? 'text-green-500 font-medium' : 'text-slate-500'}`}>
                      <span>买{bid.level}</span>
                      <span className="font-mono">{bid.price > 0 ? bid.price.toFixed(2) : '-'} / {bid.volume > 0 ? bid.volume : '-'}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-4 pt-4 border-t border-slate-100 text-xs text-slate-400 text-center">
              暂无五档数据
            </div>
          )}
        </div>

        {/* F10 基本信息 */}
        {profile && profile.data && (
          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <BookOpen size={18} className="text-blue-600" />
                <h3 className="font-semibold text-slate-700">F10 基本信息</h3>
              </div>
              <Link
                to={`/f10/${symbol}`}
                className="text-xs text-blue-600 hover:text-blue-800 hover:underline"
              >
                查看完整 F10 →
              </Link>
            </div>
            <div className="space-y-2 text-sm">
              {Object.entries(profile.data).slice(0, 10).map(([key, value]) => (
                <div key={key} className="flex justify-between">
                  <span className="text-slate-500">{F10_LABELS[key] || key}</span>
                  <span className="font-medium text-slate-800 max-w-[60%] truncate text-right">{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 交易信号 */}
        <div
          ref={signalRef}
          className={`bg-white rounded-xl p-5 shadow-sm border transition ${
            highlightSignal ? 'border-sky-500 ring-2 ring-sky-200' : 'border-slate-200'
          }`}
        >
          <h3 className="font-semibold text-slate-700 mb-4">交易信号</h3>
          {signal ? (
            <div className="space-y-3">
              {/* 信号类型 + 置信度 */}
              <div className="flex items-center justify-between">
                <span
                  className={`px-3 py-1 rounded-full text-sm font-bold ${
                    signal.type === 'BUY'
                      ? 'bg-red-100 text-red-600'
                      : signal.type === 'SELL'
                      ? 'bg-green-100 text-green-600'
                      : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  {signal.type_label || (signal.type === 'BUY' ? '买入' : signal.type === 'SELL' ? '卖出' : '观望')}
                </span>
                <div className="text-right">
                  <div className="text-xs text-slate-400">置信度</div>
                  <div className={`text-lg font-bold ${
                    signal.confidence >= 0.7 ? 'text-red-500' : signal.confidence >= 0.5 ? 'text-amber-500' : 'text-slate-400'
                  }`}>
                    {(signal.confidence * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              {/* 交易计划 */}
              {signal.type !== 'HOLD' ? (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-slate-50 rounded p-2">
                    <div className="text-slate-400">入场价</div>
                    <div className="font-medium text-slate-800">{signal.entry_price.toFixed(2)}</div>
                  </div>
                  <div className="bg-slate-50 rounded p-2">
                    <div className="text-slate-400">止损价</div>
                    <div className="font-medium text-red-600">{signal.stop_loss.toFixed(2)}</div>
                  </div>
                  <div className="bg-slate-50 rounded p-2">
                    <div className="text-slate-400">TP1 / TP2 / TP3</div>
                    <div className="font-medium text-green-600">
                      {signal.tp1.toFixed(2)} / {signal.tp2.toFixed(2)} / {signal.tp3.toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-slate-50 rounded p-2">
                    <div className="text-slate-400">建议仓位</div>
                    <div className="font-medium text-slate-800">{(signal.position_pct * 100).toFixed(0)}%</div>
                  </div>
                </div>
              ) : (
                <div className="text-xs bg-slate-50 rounded p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">当前价</span>
                    <span className="font-medium text-slate-800">{signal.entry_price.toFixed(2)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">多空力量对比</span>
                    <span className="font-medium text-slate-600">
                      {(() => {
                        const bullish = signal.factors?.filter((f: any) => f.score > 0.2).length || 0
                        const bearish = signal.factors?.filter((f: any) => f.score < -0.2).length || 0
                        return `${bullish} 偏多 / ${bearish} 偏空`
                      })()}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">最强因子</span>
                    <span className="font-medium text-slate-600">
                      {(() => {
                        const strongest = signal.factors?.reduce((a: any, b: any) => Math.abs(b.score) > Math.abs(a.score) ? b : a, signal.factors?.[0])
                        const label = strongest?.name_label || strongest?.name || '-'
                        return strongest ? `${label} (${strongest.score > 0 ? '+' : ''}${strongest.score.toFixed(2)})` : '-'
                      })()}
                    </span>
                  </div>
                </div>
              )}

              {/* 追踪止损（仅在非HOLD且trailing_stop>0时显示） */}
              {signal.type !== 'HOLD' && (signal.trailing_stop ?? 0) > 0 && (
                <div className="text-xs bg-amber-50 rounded p-2 flex items-center gap-2">
                  <span className="text-slate-400">追踪止损</span>
                  <span className="font-bold text-amber-600">{(signal.trailing_stop ?? 0).toFixed(2)}</span>
                  <span className="text-slate-400">（价格移动1R后上移至保本价）</span>
                </div>
              )}

              {/* 风险收益比 */}
              {signal.type !== 'HOLD' && signal.risk_reward_ratio > 0 && (
                <div className="flex items-center gap-2 text-xs bg-slate-50 rounded p-2">
                  <span className="text-slate-400">风险收益比</span>
                  <span className={`font-bold ${
                    signal.risk_reward_ratio >= 2.0 ? 'text-red-600' :
                    signal.risk_reward_ratio >= 1.5 ? 'text-amber-600' :
                    'text-slate-500'
                  }`}>
                    1:{signal.risk_reward_ratio.toFixed(1)}
                  </span>
                  <span className="text-slate-400 ml-1">
                    {signal.risk_reward_ratio >= 2.0 ? '（高赔率）' :
                     signal.risk_reward_ratio >= 1.5 ? '（合理）' :
                     '（赔率偏低）'}
                  </span>
                  {/* 止损合理性警告 */}
                  {signal.type === 'BUY' && signal.stop_loss >= signal.entry_price && (
                    <span className="text-red-500 font-medium ml-auto">⚠️ 止损异常</span>
                  )}
                  {signal.type === 'SELL' && signal.stop_loss <= signal.entry_price && (
                    <span className="text-red-500 font-medium ml-auto">⚠️ 止损异常</span>
                  )}
                </div>
              )}

              {/* 理由 */}
              <div className="text-xs text-slate-500 leading-relaxed bg-slate-50 rounded p-2">
                {signal.rationale}
              </div>

              {/* 因子分解 */}
              {signal.factors && signal.factors.length > 0 && (
                <div className="space-y-1">
                  <div className="text-xs text-slate-400">因子分解（权重 / 得分）</div>
                  {signal.factors.map((f, idx) => (
                    <div key={idx} className="flex items-center gap-2 text-xs">
                      <div className="w-20 text-slate-500 flex items-center justify-between">
                        <span>{f.name_label || f.name}</span>
                        <span className="text-slate-400">{(f.weight * 100).toFixed(0)}%</span>
                      </div>
                      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            f.score > 0.05 ? 'bg-red-400' : f.score < -0.05 ? 'bg-green-400' : 'bg-slate-300'
                          }`}
                          style={{ width: `${Math.abs(f.score) * 100}%` }}
                        />
                      </div>
                      <div className={`w-10 text-right font-medium ${
                        f.score > 0.05 ? 'text-red-500' : f.score < -0.05 ? 'text-green-500' : 'text-slate-400'
                      }`}>
                        {f.score > 0.05 ? '+' : ''}{f.score.toFixed(2)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="text-center text-slate-400">暂无信号</div>
          )}
        </div>

        {/* 多周期共振 */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
          <h3 className="font-semibold text-slate-700 mb-4">多周期共振</h3>
          {resonance ? (
            <div className="space-y-3">
              {/* 共振状态 */}
              <div className="flex items-center justify-between">
                <span
                  className={`px-3 py-1 rounded-full text-sm font-bold ${
                    resonance.resonance
                      ? resonance.direction === 'bull'
                        ? 'bg-red-100 text-red-600'
                        : 'bg-green-100 text-green-600'
                      : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  {resonance.resonance
                    ? resonance.direction === 'bull'
                      ? '共振看涨'
                      : '共振看跌'
                    : '未共振'}
                </span>
                <div className="text-right">
                  <div className="text-xs text-slate-400">置信度</div>
                  <div className={`text-lg font-bold ${
                    resonance.confidence >= 0.7 ? 'text-red-500' : resonance.confidence >= 0.5 ? 'text-amber-500' : 'text-slate-400'
                  }`}>
                    {(resonance.confidence * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              {/* 三周期趋势 */}
              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  { label: '日线', trend: resonance.daily_trend },
                  { label: '周线', trend: resonance.weekly_trend },
                  { label: '月线', trend: resonance.monthly_trend },
                ].map((item) => (
                  <div key={item.label} className="bg-slate-50 rounded p-2">
                    <div className="text-xs text-slate-400">{item.label}</div>
                    <div className={`text-sm font-bold ${
                      item.trend === 'bull' ? 'text-red-500' : item.trend === 'bear' ? 'text-green-500' : 'text-slate-400'
                    }`}>
                      {item.trend === 'bull' ? '上涨' : item.trend === 'bear' ? '下跌' : '中性'}
                    </div>
                  </div>
                ))}
              </div>

              {/* 描述 */}
              <div className="text-xs text-slate-500 leading-relaxed bg-slate-50 rounded p-2">
                {resonance.description}
              </div>
            </div>
          ) : (
            <div className="text-center text-slate-400">暂无数据</div>
          )}
        </div>

        {/* 技术指标 */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
          <h3 className="font-semibold text-slate-700 mb-4">技术指标</h3>
          <div className="space-y-2 text-sm">
            {[
              {
                label: indicatorLabels.ma5 || '5日均线',
                value: indicators.ma5?.toFixed(2) ?? '-',
              },
              {
                label: indicatorLabels.ma20 || '20日均线',
                value: indicators.ma20?.toFixed(2) ?? '-',
              },
              {
                label: `KDJ(${indicatorLabels.kdj_k || 'K线'}/${indicatorLabels.kdj_d || 'D线'}/${indicatorLabels.kdj_j || 'J线'})`,
                value: `${indicators.kdj_k?.toFixed(2) ?? '-'}/${indicators.kdj_d?.toFixed(2) ?? '-'}/${indicators.kdj_j?.toFixed(2) ?? '-'}`,
              },
              {
                label: `MACD(${indicatorLabels.macd_dif?.replace('MACD', '').trim() || '差离值'}/${indicatorLabels.macd_dea?.replace('MACD', '').trim() || '信号线'})`,
                value: `${indicators.macd_dif?.toFixed(3) ?? '-'}/${indicators.macd_dea?.toFixed(3) ?? '-'}`,
              },
              {
                label: indicatorLabels.rsi6 || 'RSI(6)',
                value: indicators.rsi6?.toFixed(2) ?? '-',
              },
              {
                label: `BOLL(${indicatorLabels.boll_up?.replace('布林', '').trim() || '上轨'}/${indicatorLabels.boll_mid?.replace('布林', '').trim() || '中轨'}/${indicatorLabels.boll_down?.replace('布林', '').trim() || '下轨'})`,
                value: `${indicators.boll_up?.toFixed(2) ?? '-'}/${indicators.boll_mid?.toFixed(2) ?? '-'}/${indicators.boll_down?.toFixed(2) ?? '-'}`,
              },
              {
                label: indicatorLabels.obv || 'OBV能量潮',
                value: indicators.obv?.toFixed(0) ?? '-',
              },
              {
                label: `DMI(${indicatorLabels.dmi_pdi?.replace('DMI', '').trim() || '+DI'}/${indicatorLabels.dmi_mdi?.replace('DMI', '').trim() || '-DI'}/${indicatorLabels.dmi_adx?.replace('DMI', '').trim() || 'ADX'})`,
                value: `${indicators.dmi_pdi?.toFixed(2) ?? '-'}/${indicators.dmi_mdi?.toFixed(2) ?? '-'}/${indicators.dmi_adx?.toFixed(2) ?? '-'}`,
              },
            ].map((item) => (
              <div key={item.label} className="flex justify-between">
                <span className="text-slate-500">{item.label}</span>
                <span className="font-medium">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* K线图 / 分时图 */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-slate-700">{viewMode === 'intraday' ? '分时图' : 'K线图'}</h3>
            <span className="px-2 py-0.5 bg-slate-100 text-slate-600 text-[10px] rounded">
              {adjustMode === 'qfq' ? '前复权' : adjustMode === 'hfq' ? '后复权' : '不复权'}
            </span>
          </div>
          <div className="flex gap-1 items-center">
            <select
              value={adjustMode}
              onChange={(e) => setAdjustMode(e.target.value)}
              className="px-2 py-1 text-xs border border-slate-200 rounded-md bg-white text-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
              title="复权方式"
            >
              <option value="qfq">前复权</option>
              <option value="hfq">后复权</option>
              <option value="none">不复权</option>
            </select>
            <button
              onClick={() => setViewMode('intraday')}
              className={`px-3 py-1 text-xs rounded-md transition ${
                viewMode === 'intraday'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              分时
            </button>
            {[
              { key: 'minute' as const, label: '分钟' },
              { key: 'daily' as const, label: '日K' },
              { key: 'weekly' as const, label: '周K' },
              { key: 'monthly' as const, label: '月K' },
            ].map((p) => (
              <button
                key={p.key}
                onClick={() => { setPeriod(p.key); setViewMode('kline'); }}
                className={`px-3 py-1 text-xs rounded-md transition ${
                  period === p.key && viewMode === 'kline'
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        {/* 指标叠加切换（仅K线图） */}
        {viewMode === 'kline' && (
          <div className="flex flex-wrap gap-2 mb-3">
            {[
              { key: 'ma5', label: 'MA5' },
              { key: 'ma20', label: 'MA20' },
              { key: 'ma60', label: 'MA60' },
              { key: 'boll', label: 'BOLL' },
              { key: 'supportResistance', label: '支撑阻力' },
            ].map((item) => (
              <button
                key={item.key}
                onClick={() => setChartIndicators((prev) => ({ ...prev, [item.key]: !prev[item.key as keyof typeof prev] }))}
                className={`px-2 py-1 text-xs rounded-md transition border ${
                  chartIndicators[item.key as keyof typeof chartIndicators]
                    ? 'bg-sky-50 text-sky-600 border-sky-200'
                    : 'bg-slate-50 text-slate-400 border-slate-200'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
        {viewMode === 'intraday' && intraday && intraday.data && intraday.data.length > 0 ? (
          <IntradayChart
            data={intraday.data}
            height={420}
            prevClose={quote?.pre_close ?? quote?.open}
          />
        ) : viewMode === 'intraday' ? (
          <div className="text-center py-12 text-slate-400">暂无分时数据</div>
        ) : chartData.length > 0 ? (
          <TradingViewChart
            data={chartData}
            height={420}
            patterns={patterns}
            volumeAnalysis={volumeAnalysis}
            supportResistance={supportResistance}
            signal={signal}
            indicators={chartIndicators}
          />
        ) : (
          <div className="text-center py-12 text-slate-400">暂无K线数据</div>
        )}
      </div>

      {/* 副图指标面板 */}
      {chartData.length > 0 && (
        <IndicatorPanel
          data={chartData}
          activeTab={activeIndicator}
          onTabChange={setActiveIndicator}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 形态识别面板 */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={18} className="text-blue-600" />
            <h3 className="font-semibold text-slate-700">形态识别</h3>
          </div>
          {patterns.length > 0 ? (
            <div className="space-y-2">
              {patterns.map((p, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-3 rounded-lg bg-slate-50 hover:bg-slate-100 transition"
                >
                  <div>
                    <div className="font-medium text-sm text-slate-800">{p.display_name || p.pattern}</div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {p.start_date} ~ {p.end_date}
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">{p.description}</div>
                  </div>
                  <div className="text-right">
                    <div
                      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                        p.confidence >= 0.8
                          ? 'bg-red-100 text-red-600'
                          : p.confidence >= 0.6
                          ? 'bg-amber-100 text-amber-600'
                          : 'bg-blue-100 text-blue-600'
                      }`}
                    >
                      置信度 {Math.round((p.confidence || 0) * 100)}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-slate-400 text-sm">未检测到形态</div>
          )}
        </div>

        {/* 支撑阻力面板 */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
          <div className="flex items-center gap-2 mb-4">
            <Shield size={18} className="text-green-600" />
            <h3 className="font-semibold text-slate-700">支撑阻力</h3>
          </div>
          {supportResistance && (
            <div className="space-y-4">
              {supportResistance.support && supportResistance.support.length > 0 && (
                <div>
                  <div className="text-xs text-slate-500 mb-2 flex items-center gap-1">
                    <Target size={14} className="text-green-500" />
                    支撑位
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {supportResistance.support.map((price, idx) => (
                      <span
                        key={`s-${idx}`}
                        className="text-xs px-2 py-1 rounded bg-green-50 text-green-700 font-medium"
                      >
                        {price.toFixed(2)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {supportResistance.resistance && supportResistance.resistance.length > 0 && (
                <div>
                  <div className="text-xs text-slate-500 mb-2 flex items-center gap-1">
                    <Target size={14} className="text-red-500" />
                    阻力位
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {supportResistance.resistance.map((price, idx) => (
                      <span
                        key={`r-${idx}`}
                        className="text-xs px-2 py-1 rounded bg-red-50 text-red-700 font-medium"
                      >
                        {price.toFixed(2)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {supportResistance.levels && supportResistance.levels.length > 0 && (
                <div className="pt-2 border-t border-slate-100">
                  <div className="text-xs text-slate-500 mb-2">关键价位</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="text-slate-400">
                        <tr>
                          <th className="text-left py-1">价位</th>
                          <th className="text-left py-1">类型</th>
                          <th className="text-right py-1">强度</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {supportResistance.levels.slice(0, 10).map((level, idx) => (
                          <tr key={idx}>
                            <td className="py-1 font-medium">{level.price.toFixed(2)}</td>
                            <td className="py-1">
                              <span
                                className={`px-1.5 py-0.5 rounded text-white text-[10px] ${
                                  level.type === 'support' ? 'bg-green-500' : 'bg-red-500'
                                }`}
                              >
                                {level.type === 'support' ? '支撑' : '阻力'}
                              </span>
                            </td>
                            <td className="py-1 text-right text-slate-500">{level.strength.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
          {(!supportResistance ||
            (supportResistance.support.length === 0 && supportResistance.resistance.length === 0)) && (
            <div className="text-center py-8 text-slate-400 text-sm">暂无支撑阻力数据</div>
          )}
        </div>
      </div>

      {/* K线数据明细 */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="font-semibold text-slate-700 mb-4">K线明细</h3>
        {ohlcv.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-sm">暂无K线数据</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left">日期</th>
                  <th className="px-3 py-2 text-right">开盘</th>
                  <th className="px-3 py-2 text-right">最高</th>
                  <th className="px-3 py-2 text-right">最低</th>
                  <th className="px-3 py-2 text-right">收盘</th>
                  <th className="px-3 py-2 text-right">成交量</th>
                  <th className="px-3 py-2 text-right">涨跌幅</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {ohlcv.slice(0, 20).map((row) => {
                  const rowChange = ((row.close - row.open) / row.open) * 100
                  return (
                    <tr key={row.date} className="hover:bg-slate-50">
                      <td className="px-3 py-2">{row.date}</td>
                      <td className="px-3 py-2 text-right">{row.open.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right">{row.high.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right">{row.low.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right font-medium">{row.close.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right font-mono">{formatVolume(row.volume)}</td>
                      <td className={`px-3 py-2 text-right ${rowChange >= 0 ? 'text-up' : 'text-down'}`}>
                        {rowChange >= 0 ? '+' : ''}
                        {rowChange.toFixed(2)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default React.memo(StockDetail)
