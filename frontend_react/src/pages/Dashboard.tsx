import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { TrendingUp, TrendingDown, Activity, Zap, Database, CheckCircle, AlertTriangle, XCircle } from 'lucide-react'
import { fetchQuotesBatch, fetchMarketSentiment, fetchMarketHotspots, fetchDataHealth, fetchMarketOverview } from '@/api/client'
import type { StandardQuote } from '@/types'

const INDEX_SYMBOLS = [
  { symbol: 'sh000001', name: '上证指数' },
  { symbol: 'sz399001', name: '深证成指' },
  { symbol: 'sz399006', name: '创业板指' },
  { symbol: 'sh000688', name: '科创50' },
]

function IndexCard({ name, close, change, changePct, volume, date }: { 
  name: string; 
  close: number; 
  change: number; 
  changePct: number; 
  volume: number; 
  date: string;
}) {
  const isUp = change >= 0

  return (
    <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-slate-600">{name}</span>
        {isUp ? (
          <TrendingUp size={16} className="text-up" />
        ) : (
          <TrendingDown size={16} className="text-down" />
        )}
      </div>
      <div className={`text-2xl font-bold ${isUp ? 'text-up' : 'text-down'}`}>
        {close.toFixed(2)}
      </div>
      <div className={`text-sm mt-1 ${isUp ? 'text-up' : 'text-down'}`}>
        {isUp ? '▲' : '▼'} {change >= 0 ? '+' : ''}
        {change.toFixed(2)} ({changePct >= 0 ? '+' : ''}
        {changePct.toFixed(2)}%)
      </div>
      <div className="text-xs text-slate-400 mt-2">
        量: {(volume / 10000).toFixed(1)}万 · {date}
      </div>
    </div>
  )
}

function MarketSentiment({ data, loading }: { data: any; loading: boolean }) {
  if (loading) {
    return (
      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200 animate-pulse">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={18} className="text-sky-500" />
          <h3 className="font-semibold text-slate-700">市场情绪</h3>
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-8 bg-slate-100 rounded" />
          ))}
        </div>
      </div>
    )
  }

  const ratio = data?.up_down_ratio
  const limitUp = data?.limit_up
  const limitDown = data?.limit_down
  const hasData = ratio !== undefined && ratio !== null

  return (
    <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
      <div className="flex items-center gap-2 mb-3">
        <Activity size={18} className="text-sky-500" />
        <h3 className="font-semibold text-slate-700">市场情绪</h3>
        {data?.source && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${data.source === 'eastmoney' ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-400'}`}>
            {data.source === 'eastmoney' ? '实时' : data.source === 'unavailable' ? '暂无数据（非交易时间）' : data.source}
          </span>
        )}
      </div>
      <div className="space-y-3">
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span className="text-slate-500">涨跌比</span>
            <span className={`font-medium ${hasData && ratio >= 1 ? 'text-up' : hasData ? 'text-down' : 'text-slate-400'}`}>
              {hasData ? ratio.toFixed(2) : '--'}
            </span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${hasData && ratio >= 1 ? 'bg-up' : 'bg-down'}`}
              style={{ width: hasData ? `${Math.min(ratio / (ratio + 1) * 100, 100)}%` : '0%' }}
            />
          </div>
        </div>
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span className="text-slate-500">涨停家数</span>
            <span className="text-up font-medium">{limitUp !== undefined && limitUp !== null ? limitUp : '--'}</span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-up rounded-full" style={{ width: limitUp ? `${Math.min(limitUp / 100 * 100, 100)}%` : '0%' }} />
          </div>
        </div>
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span className="text-slate-500">跌停家数</span>
            <span className="text-down font-medium">{limitDown !== undefined && limitDown !== null ? limitDown : '--'}</span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-down rounded-full" style={{ width: limitDown ? `${Math.min(limitDown / 50 * 100, 100)}%` : '0%' }} />
          </div>
        </div>
      </div>
      {data?.data_date && (
        <div className="text-xs text-slate-400 mt-2 pt-2 border-t border-slate-100">
          数据日期：{data.data_date}
        </div>
      )}
    </div>
  )
}

function HotBlocks({ data, loading }: { data: any[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200 animate-pulse">
        <div className="flex items-center gap-2 mb-3">
          <Zap size={18} className="text-amber-500" />
          <h3 className="font-semibold text-slate-700">热点板块</h3>
        </div>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 bg-slate-100 rounded" />
          ))}
        </div>
      </div>
    )
  }

  const blocks = data || []

  if (blocks.length === 0) {
    return (
      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
        <div className="flex items-center gap-2 mb-3">
          <Zap size={18} className="text-amber-500" />
          <h3 className="font-semibold text-slate-700">热点板块</h3>
        </div>
        <div className="text-sm text-slate-400 py-8 text-center">暂无板块数据（非交易时间或数据源未连接）</div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
      <div className="flex items-center gap-2 mb-3">
        <Zap size={18} className="text-amber-500" />
        <h3 className="font-semibold text-slate-700">热点板块</h3>
      </div>
      <div className="space-y-2">
        {blocks.map((b) => (
          <div key={b.block_code || b.block_name} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
            <div className="flex items-center gap-2">
              <span className="text-xs w-5 h-5 flex items-center justify-center rounded bg-slate-100 text-slate-500 font-medium">
                {b.rank || '-'}
              </span>
              <span className="text-sm font-medium text-slate-700">{b.block_name}</span>
            </div>
            <div className="text-right">
              <div className={`text-sm font-semibold ${(b.change_pct || 0) >= 0 ? 'text-up' : 'text-down'}`}>
                {(b.change_pct || 0) >= 0 ? '▲' : '▼'} {(b.change_pct || 0) >= 0 ? '+' : ''}
                {(b.change_pct || 0).toFixed(2)}%
              </div>
              <div className="text-xs text-slate-400">
                {b.up_count !== undefined ? `${b.up_count}/${b.stock_count || '--'}家上涨` : ''}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function DataHealthPanel({ data, loading }: { data: any; loading: boolean }) {
  if (loading) {
    return (
      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200 animate-pulse">
        <div className="flex items-center gap-2 mb-3">
          <Database size={18} className="text-sky-500" />
          <h3 className="font-semibold text-slate-700">数据健康</h3>
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-8 bg-slate-100 rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
        <div className="flex items-center gap-2 mb-3">
          <Database size={18} className="text-sky-500" />
          <h3 className="font-semibold text-slate-700">数据健康</h3>
        </div>
        <div className="text-sm text-slate-400 py-4 text-center">数据状态未知</div>
      </div>
    )
  }

  const health = data.health || {}
  const status = data.status || 'unknown'
  const items = [
    { label: '离线数据', ok: health.offline_available, icon: CheckCircle },
    { label: '实时数据', ok: health.realtime_available, icon: CheckCircle },
    { label: '通达信目录', ok: health.tdxdir_exists, icon: CheckCircle },
  ]

  return (
    <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Database size={18} className="text-sky-500" />
          <h3 className="font-semibold text-slate-700">数据健康</h3>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          status === 'ok' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'
        }`}>
          {status === 'ok' ? '正常' : '异常'}
        </span>
      </div>
      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.label} className="flex items-center justify-between py-1.5">
            <div className="flex items-center gap-2 text-sm text-slate-600">
              {item.ok ? (
                <CheckCircle size={14} className="text-emerald-500" />
              ) : (
                <XCircle size={14} className="text-red-400" />
              )}
              {item.label}
            </div>
            <span className={`text-xs font-medium ${item.ok ? 'text-emerald-600' : 'text-red-500'}`}>
              {item.ok ? '可用' : '异常'}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-3 pt-3 border-t border-slate-100">
        <Link to="/data" className="text-xs text-sky-600 hover:text-sky-700 font-medium">
          查看详细数据 →
        </Link>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [quotes, setQuotes] = useState<Record<string, StandardQuote>>({})
  const [sentiment, setSentiment] = useState<any>(null)
  const [hotspots, setHotspots] = useState<any[]>([])
  const [dataHealth, setDataHealth] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [sentimentLoading, setSentimentLoading] = useState(true)
  const [hotspotsLoading, setHotspotsLoading] = useState(true)
  const [healthLoading, setHealthLoading] = useState(true)

  const [indexData, setIndexData] = useState<any[]>([])
  const [latestTradingDay, setLatestTradingDay] = useState<string | null>(null)
  const [indexLoading, setIndexLoading] = useState(true)

  useEffect(() => {
    async function loadIndexData() {
      try {
        const resp = await fetchMarketOverview()
        setIndexData(resp.indices || [])
        setLatestTradingDay(resp.latest_trading_day || null)
      } catch (e) {
        console.error('Failed to load market overview', e)
      } finally {
        setIndexLoading(false)
      }
    }

    async function loadSentiment() {
      try {
        const resp = await fetchMarketSentiment()
        setSentiment(resp)
      } catch (e) {
        console.error('Failed to load sentiment', e)
      } finally {
        setSentimentLoading(false)
      }
    }

    async function loadHotspots() {
      try {
        const resp = await fetchMarketHotspots(10)
        setHotspots(resp.hotspots || [])
      } catch (e) {
        console.error('Failed to load hotspots', e)
      } finally {
        setHotspotsLoading(false)
      }
    }

    async function loadHealth() {
      try {
        const resp = await fetchDataHealth()
        setDataHealth(resp)
      } catch (e) {
        console.error('Failed to load data health', e)
      } finally {
        setHealthLoading(false)
      }
    }

    loadIndexData()
    loadSentiment()
    loadHotspots()
    loadHealth()
  }, [])

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {indexLoading ? (
          [1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white rounded-xl p-4 shadow-sm border border-slate-200 animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-20 mb-2" />
              <div className="h-6 bg-slate-200 rounded w-24" />
            </div>
          ))
        ) : (
          indexData.map((idx) => (
            <IndexCard
              key={idx.code}
              name={idx.name}
              close={idx.close}
              change={idx.change}
              changePct={idx.change_pct}
              volume={idx.volume}
              date={idx.date}
            />
          ))
        )}
      </div>
      {latestTradingDay && !indexLoading && (
        <div className="text-xs text-slate-400 -mt-2 mb-2">
          最新交易日：{latestTradingDay}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <MarketSentiment data={sentiment} loading={sentimentLoading} />
        </div>
        <div className="space-y-4">
          <DataHealthPanel data={dataHealth} loading={healthLoading} />
          <HotBlocks data={hotspots} loading={hotspotsLoading} />
        </div>
      </div>

      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
        <h3 className="font-semibold text-slate-700 mb-3">快捷入口</h3>
        <div className="flex gap-3">
          <Link
            to="/watchlist"
            className="px-4 py-2 bg-sky-50 text-sky-700 rounded-lg text-sm font-medium hover:bg-sky-100 transition"
          >
            自选股中心
          </Link>
          <Link
            to="/stock/000001"
            className="px-4 py-2 bg-sky-50 text-sky-700 rounded-lg text-sm font-medium hover:bg-sky-100 transition"
          >
            个股分析
          </Link>
        </div>
      </div>
    </div>
  )
}
