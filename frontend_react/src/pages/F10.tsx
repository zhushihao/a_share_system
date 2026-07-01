import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, BookOpen, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react'
import { fetchF10, fetchQuote } from '@/api/client'

const F10_LABELS: Record<string, string> = {
  symbol: '股票代码',
  name: '股票名称',
  market: '所属市场',
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

// 分组定义：将 F10 字段按类别分组展示
const F10_GROUPS = [
  {
    title: '基本信息',
    fields: ['symbol', 'name', 'market', 'industry'],
    icon: BookOpen,
  },
  {
    title: '估值指标',
    fields: ['pe', 'pb', 'eps', 'bvps', 'roe', 'dividend'],
    icon: TrendingUp,
  },
  {
    title: '财务数据',
    fields: ['revenue', 'profit'],
    icon: TrendingUp,
  },
  {
    title: '股本市值',
    fields: ['total_capital', 'circulating_capital', 'market_cap', 'circulating_market_cap'],
    icon: TrendingUp,
  },
  {
    title: '交易指标',
    fields: ['turnover_rate', 'amplitude', 'volume_ratio', 'fiv_min_rise'],
    icon: TrendingDown,
  },
]

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  if (Number.isNaN(num)) return String(value)

  // 金额类字段格式化
  if (['revenue', 'profit', 'market_cap', 'circulating_market_cap'].includes(key)) {
    if (num >= 100000000) return `${(num / 100000000).toFixed(2)}亿`
    if (num >= 10000) return `${(num / 10000).toFixed(2)}万`
    return num.toLocaleString()
  }

  // 股本类字段格式化
  if (['total_capital', 'circulating_capital'].includes(key)) {
    if (num >= 100000000) return `${(num / 100000000).toFixed(2)}亿股`
    if (num >= 10000) return `${(num / 10000).toFixed(2)}万股`
    return `${num}股`
  }

  // 百分比类
  if (['roe', 'dividend', 'turnover_rate', 'amplitude', 'fiv_min_rise'].includes(key)) {
    return `${num.toFixed(2)}%`
  }

  // 比率类
  if (['pe', 'pb', 'volume_ratio'].includes(key)) {
    return num.toFixed(2)
  }

  return String(value)
}

function getValueColor(key: string, value: unknown): string {
  if (value === null || value === undefined) return 'text-slate-400'
  const num = Number(value)
  if (Number.isNaN(num)) return 'text-slate-800'

  // 红涨绿跌：正值红色，负值绿色
  if (['fiv_min_rise', 'amplitude'].includes(key)) {
    return num >= 0 ? 'text-up' : 'text-down'
  }

  // PE/PB 过高警示
  if (key === 'pe' && num > 100) return 'text-red-500'
  if (key === 'pb' && num > 10) return 'text-red-500'

  return 'text-slate-800'
}

function F10Page() {
  const { symbol } = useParams<{ symbol: string }>()
  const [f10Data, setF10Data] = useState<Record<string, unknown> | null>(null)
  const [source, setSource] = useState<string>('')
  const [quote, setQuote] = useState<{ name?: string; price?: number; change?: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!symbol) return

    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const [f10Res, quoteRes] = await Promise.all([
          fetchF10(symbol),
          fetchQuote(symbol).catch(() => null),
        ])

        if (f10Res && f10Res.data) {
          setF10Data(f10Res.data)
          setSource(f10Res.source || '')
        } else {
          setError('F10 数据返回格式异常')
        }

        if (quoteRes) {
          setQuote(quoteRes)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载 F10 数据失败')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [symbol])

  const isFallback = source === 'stock_list_fallback' || source === 'minimal'

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96 text-slate-400">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mr-3" />
        加载 F10 数据中...
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-slate-500">
        <AlertCircle size={48} className="mb-4 text-red-400" />
        <p>{error}</p>
        <Link to={`/stock/${symbol}`} className="mt-4 text-blue-600 hover:underline">
          ← 返回个股详情
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            to={`/stock/${symbol}`}
            className="flex items-center gap-1 text-slate-500 hover:text-slate-700 transition-colors"
          >
            <ArrowLeft size={18} />
            <span>返回</span>
          </Link>
          <div className="h-6 w-px bg-slate-200" />
          <div className="flex items-center gap-2">
            <BookOpen size={20} className="text-blue-600" />
            <h1 className="text-xl font-bold text-slate-800">
              F10 基本面数据
            </h1>
          </div>
          {quote?.name && (
            <span className="text-slate-500">
              {quote.name} ({symbol})
            </span>
          )}
        </div>
        {isFallback && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 text-amber-700 rounded-lg text-sm border border-amber-200">
            <AlertCircle size={14} />
            <span>F10 实时接口暂不可用，显示基础信息</span>
          </div>
        )}
      </div>

      {/* 实时报价卡片 */}
      {quote && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
          <div className="flex items-center gap-6">
            <div>
              <div className="text-sm text-slate-500 mb-1">最新价</div>
              <div className={`text-2xl font-bold ${quote.change && quote.change >= 0 ? 'text-up' : 'text-down'}`}>
                {quote.price?.toFixed(2) ?? '-'}
              </div>
            </div>
            <div>
              <div className="text-sm text-slate-500 mb-1">涨跌幅</div>
              <div className={`text-lg font-semibold ${quote.change && quote.change >= 0 ? 'text-up' : 'text-down'}`}>
                {quote.change && quote.change >= 0 ? '+' : ''}
                {quote.change?.toFixed(2) ?? '-'}%
              </div>
            </div>
            <div className="h-10 w-px bg-slate-200" />
            <div>
              <div className="text-sm text-slate-500 mb-1">数据来源</div>
              <div className="text-sm font-medium text-slate-700">
                {source === 'mootdx-F10' ? 'mootdx 实时 F10' : source === 'stock_list_fallback' ? '股票列表降级' : source}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* F10 数据卡片网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {F10_GROUPS.map((group) => {
          const hasData = group.fields.some((f) => f10Data?.[f] !== null && f10Data?.[f] !== undefined)
          if (!hasData) return null

          const Icon = group.icon
          return (
            <div key={group.title} className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
              <div className="flex items-center gap-2 mb-4">
                <Icon size={18} className="text-blue-600" />
                <h3 className="font-semibold text-slate-700">{group.title}</h3>
              </div>
              <div className="space-y-3">
                {group.fields.map((field) => {
                  const value = f10Data?.[field]
                  const hasValue = value !== null && value !== undefined
                  return (
                    <div key={field} className="flex justify-between items-center">
                      <span className="text-sm text-slate-500">{F10_LABELS[field] || field}</span>
                      <span className={`text-sm font-medium ${hasValue ? getValueColor(field, value) : 'text-slate-400'}`}>
                        {formatValue(field, value)}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {/* 原始数据展开（开发调试用，默认折叠） */}
      {f10Data && Object.keys(f10Data).length > 0 && (
        <details className="bg-slate-50 rounded-xl border border-slate-200">
          <summary className="px-5 py-3 text-sm text-slate-500 cursor-pointer hover:text-slate-700 select-none">
            查看原始数据 ({Object.keys(f10Data).length} 个字段)
          </summary>
          <div className="px-5 pb-4">
            <pre className="text-xs text-slate-600 overflow-x-auto">
              {JSON.stringify(f10Data, null, 2)}
            </pre>
          </div>
        </details>
      )}
    </div>
  )
}

export default React.memo(F10Page)
