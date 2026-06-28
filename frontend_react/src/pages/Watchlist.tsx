import React, { useEffect, useState, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Trash2, Upload, Download, RefreshCw, ArrowUpDown, ArrowUp, ArrowDown, Search, Check } from 'lucide-react'
import { fetchWatchlist, addWatchlist, deleteWatchlist, updateWatchlistGroup, updateWatchlistGroupBatch, fetchWatchlistGroups, searchStocks } from '@/api/client'
import type { WatchlistWithQuote } from '@/types'

export default function Watchlist() {
  const [items, setItems] = useState<WatchlistWithQuote[]>([])
  const [groups, setGroups] = useState<string[]>([])
  const [selectedGroup, setSelectedGroup] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Array<{ code: string; name: string; market: string }>>([])
  const [allStocks, setAllStocks] = useState<Array<{ code: string; name: string; market: string }>>([])
  const [showSearchDropdown, setShowSearchDropdown] = useState(false)
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const [sortField, setSortField] = useState<string>('')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')
  const [filterQuery, setFilterQuery] = useState('')
  const [targetGroup, setTargetGroup] = useState(selectedGroup || '默认')
  const [togglingCodes, setTogglingCodes] = useState<Set<string>>(new Set())
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([])
  const [moveGroup, setMoveGroup] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const searchRef = useRef<HTMLDivElement>(null)

  const [searchLoading, setSearchLoading] = useState(false)

  // 加载全市场股票列表（兜底离线搜索）
  useEffect(() => {
    async function loadStockList() {
      try {
        const resp = await fetch('/api/v1/data/stock-list?limit=20000')
        const data = await resp.json()
        if (data.stocks && data.stocks.length > 0) {
          setAllStocks(data.stocks)
        }
      } catch (e) {
        console.error('Failed to load stock list', e)
      }
    }
    loadStockList()
  }, [])

  const handleSearch = useCallback(async (query: string) => {
    if (!query || query.length < 2 || query.length > 20) {
      setSearchResults([])
      setShowSearchDropdown(false)
      return
    }
    setSearchLoading(true)
    try {
      // 优先走服务端全量搜索，避免本地 5000 条截断导致搜不到（如 300308 中际旭创）
      const data = await searchStocks(query)
      let matches = (data.stocks || []).slice(0, 10)

      // 服务端不可用时回退到本地列表
      if (!matches.length && allStocks.length > 0) {
        const q = query.trim().toLowerCase()
        matches = allStocks.filter((s) => {
          const code = s.code.toLowerCase()
          const name = s.name.toLowerCase()
          return code.startsWith(q) || name.includes(q)
        }).slice(0, 10)
      }

      setSearchResults(matches)
      setShowSearchDropdown(matches.length > 0)
    } catch (e) {
      console.error('Search failed', e)
      // 兜底本地搜索
      const q = query.trim().toLowerCase()
      const matches = allStocks.filter((s) => {
        const code = s.code.toLowerCase()
        const name = s.name.toLowerCase()
        return code.startsWith(q) || name.includes(q)
      }).slice(0, 10)
      setSearchResults(matches)
      setShowSearchDropdown(matches.length > 0)
    } finally {
      setSearchLoading(false)
    }
  }, [allStocks])

  const onSearchInputChange = (value: string) => {
    setSearchQuery(value)
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }
    searchTimeoutRef.current = setTimeout(() => {
      handleSearch(value)
    }, 200)
  }

  const watchlistMap = React.useMemo(() => {
    const map: Record<string, WatchlistWithQuote> = {}
    for (const item of items) {
      map[item.symbol] = item
    }
    return map
  }, [items])

  async function handleToggleStock(stock: { code: string; name: string; market: string }) {
    if (togglingCodes.has(stock.code)) return
    setTogglingCodes((prev) => new Set(prev).add(stock.code))
    try {
      const existing = watchlistMap[stock.code]
      if (existing && existing.group === targetGroup) {
        await deleteWatchlist(stock.code)
      } else {
        await addWatchlist({ symbol: stock.code, name: stock.name, group: targetGroup })
      }
      await load()
    } finally {
      setTogglingCodes((prev) => {
        const next = new Set(prev)
        next.delete(stock.code)
        return next
      })
    }
  }

  async function handleAddAllResults() {
    const toAdd = searchResults.filter((s) => !watchlistMap[s.code])
    if (toAdd.length === 0) return
    setTogglingCodes((prev) => new Set([...prev, ...toAdd.map((s) => s.code)]))
    try {
      await Promise.all(
        toAdd.map((s) => addWatchlist({ symbol: s.code, name: s.name, group: targetGroup }))
      )
      await load()
    } finally {
      setTogglingCodes((prev) => {
        const next = new Set(prev)
        toAdd.forEach((s) => next.delete(s.code))
        return next
      })
    }
  }

  // 点击外部关闭下拉
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowSearchDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [listResp, groupsResp] = await Promise.all([
        selectedGroup ? fetchWatchlist(selectedGroup) : fetchWatchlist(),
        fetchWatchlistGroups(),
      ])
      setItems(listResp.items || [])
      setGroups(groupsResp.groups || [])
      setLastUpdated(new Date().toLocaleTimeString())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [selectedGroup])

  useEffect(() => {
    load()
  }, [load])

  // 切换分组过滤时，添加面板的目标分组同步跟随
  useEffect(() => {
    setTargetGroup(selectedGroup || '默认')
  }, [selectedGroup])

  // 定时刷新：每30秒刷新一次
  useEffect(() => {
    refreshTimerRef.current = setInterval(() => {
      load()
    }, 30000)
    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current)
      }
    }
  }, [load])

  async function handleDelete(symbol: string) {
    if (!confirm(`确定删除 ${symbol} 吗？`)) return
    await deleteWatchlist(symbol)
    load()
  }

  async function handleImport(file: File) {
    const text = await file.text()
    const lines = text.split('\n').filter((l) => l.trim())
    if (lines.length < 2) {
      alert('CSV 格式不正确')
      return
    }
    const headers = lines[0].split(',')
    const symIdx = headers.indexOf('symbol')
    const nameIdx = headers.indexOf('name')
    const groupIdx = headers.indexOf('group')

    if (symIdx < 0 || nameIdx < 0) {
      alert('CSV 必须包含 symbol 和 name 列')
      return
    }

    const importItems = []
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(',')
      importItems.push({
        symbol: cols[symIdx]?.trim() || '',
        name: cols[nameIdx]?.trim() || '',
        group: groupIdx >= 0 ? (cols[groupIdx]?.trim() || '默认') : '默认',
      })
    }

    try {
      const resp = await fetch('/api/v1/watchlist/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: importItems }),
      })
      const data = await resp.json()
      alert(`导入完成：成功 ${data.added} 条，失败 ${data.failed} 条`)
      load()
    } catch (e) {
      alert('导入失败')
    }
  }

  async function handleExport() {
    try {
      const resp = await fetch('/api/v1/watchlist/export')
      const data = await resp.json()
      if (data.csv) {
        const blob = new Blob([data.csv], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `watchlist_${new Date().toISOString().slice(0, 10)}.csv`
        a.click()
        URL.revokeObjectURL(url)
      }
    } catch (e) {
      alert('导出失败')
    }
  }

  function handleSort(field: string) {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('desc')
    }
  }

  function getSortIcon(field: string) {
    if (sortField !== field) return <ArrowUpDown size={14} className="text-slate-300 inline ml-1" />
    return sortDirection === 'asc'
      ? <ArrowUp size={14} className="text-sky-600 inline ml-1" />
      : <ArrowDown size={14} className="text-sky-600 inline ml-1" />
  }

  const filtered = items.filter((i) => {
    const matchGroup = selectedGroup ? i.group === selectedGroup : true
    if (!filterQuery.trim()) return matchGroup
    const q = filterQuery.trim().toLowerCase()
    const matchSearch =
      i.symbol.toLowerCase().includes(q) || (i.name || '').toLowerCase().includes(q)
    return matchGroup && matchSearch
  })

  const sorted = [...filtered].sort((a, b) => {
    if (!sortField) return 0
    let valA: number | string = 0
    let valB: number | string = 0
    switch (sortField) {
      case 'symbol':
        valA = a.symbol
        valB = b.symbol
        break
      case 'name':
        valA = a.name || ''
        valB = b.name || ''
        break
      case 'price':
        valA = a.quote?.close || 0
        valB = b.quote?.close || 0
        break
      case 'changePct':
        valA = a.quote ? ((a.quote.close - a.quote.open) / a.quote.open) * 100 : 0
        valB = b.quote ? ((b.quote.close - b.quote.open) / b.quote.open) * 100 : 0
        break
      case 'score':
        valA = a.score || 0
        valB = b.score || 0
        break
      case 'group':
        valA = a.group || ''
        valB = b.group || ''
        break
      default:
        return 0
    }
    if (typeof valA === 'string') {
      return sortDirection === 'asc' ? valA.localeCompare(valB as string) : (valB as string).localeCompare(valA)
    }
    return sortDirection === 'asc' ? (valA as number) - (valB as number) : (valB as number) - (valA as number)
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-2 items-center">
          <div className="relative">
            <Search size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="搜索代码或名称..."
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="pl-9 pr-3 py-1.5 border border-slate-200 rounded-lg text-sm w-56 focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>
          <button
            onClick={() => setSelectedGroup('')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              selectedGroup === '' ? 'bg-sky-600 text-white' : 'bg-white text-slate-600 border border-slate-200'
            }`}
          >
            全部
          </button>
          {groups.map((g) => (
            <button
              key={g}
              onClick={() => setSelectedGroup(g)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                selectedGroup === g ? 'bg-sky-600 text-white' : 'bg-white text-slate-600 border border-slate-200'
              }`}
            >
              {g}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1 px-3 py-1.5 bg-white text-slate-600 border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50 transition"
          >
            <RefreshCw size={16} />
            刷新
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1 px-3 py-1.5 bg-white text-slate-600 border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50 transition"
          >
            <Upload size={16} />
            导入
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleImport(file)
            }}
          />
          <button
            onClick={handleExport}
            className="flex items-center gap-1 px-3 py-1.5 bg-white text-slate-600 border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50 transition"
          >
            <Download size={16} />
            导出
          </button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="flex items-center gap-1 px-3 py-1.5 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition"
          >
            <Plus size={16} />
            添加
          </button>
        </div>
      </div>

      {selectedSymbols.length > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-2">
          <span className="text-sm text-amber-800">已选择 {selectedSymbols.length} 项</span>
          <select
            value={moveGroup}
            onChange={(e) => setMoveGroup(e.target.value)}
            className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <option value="">选择目标分组...</option>
            {groups.map((g) => (
              <option key={g} value={g}>{g}</option>
            ))}
          </select>
          <input
            placeholder="或新建分组"
            value={moveGroup}
            onChange={(e) => setMoveGroup(e.target.value)}
            className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm w-40 focus:outline-none focus:ring-2 focus:ring-sky-500"
          />
          <button
            onClick={async () => {
              if (!moveGroup || selectedSymbols.length === 0) return
              await updateWatchlistGroupBatch(selectedSymbols, moveGroup)
              setSelectedSymbols([])
              setMoveGroup('')
              load()
            }}
            disabled={!moveGroup || selectedSymbols.length === 0}
            className="px-3 py-1.5 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            移动到分组
          </button>
          <button
            onClick={() => setSelectedSymbols([])}
            className="text-sm text-slate-500 hover:text-slate-700"
          >
            取消
          </button>
        </div>
      )}

      {showAdd && (
        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200" ref={searchRef}>
          <div className="flex flex-col sm:flex-row gap-3 items-start">
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500 whitespace-nowrap">目标分组</span>
              <select
                value={targetGroup}
                onChange={(e) => {
                  const val = e.target.value
                  if (val === '__new__') {
                    const name = prompt('请输入新分组名称')
                    if (name) setTargetGroup(name)
                  } else {
                    setTargetGroup(val)
                  }
                }}
                className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-sky-500"
              >
                {Array.from(new Set([...groups, targetGroup])).filter(Boolean).map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
                <option value="__new__">+ 新建分组</option>
              </select>
            </div>
            <div className="relative flex-1 max-w-md w-full">
              <input
                placeholder="输入股票代码或名称，回车或自动搜索..."
                className="px-3 py-2 border border-slate-200 rounded-lg text-sm w-full"
                value={searchQuery}
                onChange={(e) => onSearchInputChange(e.target.value)}
                onFocus={() => { if (searchResults.length > 0) setShowSearchDropdown(true) }}
              />
              {searchLoading && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">搜索中...</span>
              )}
              {showSearchDropdown && searchResults.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-10 max-h-64 overflow-y-auto">
                  {searchResults.map((stock) => {
                    const existing = watchlistMap[stock.code]
                    const inTarget = existing && existing.group === targetGroup
                    const inOther = existing && existing.group !== targetGroup
                    const busy = togglingCodes.has(stock.code)
                    return (
                      <div
                        key={stock.code}
                        className="w-full text-left px-3 py-2 hover:bg-slate-50 text-sm flex items-center justify-between border-b border-slate-50 last:border-0"
                      >
                        <span>
                          <span className="font-medium text-slate-700">{stock.code}</span>
                          <span className="text-slate-400 mx-2">|</span>
                          <span className="text-slate-600">{stock.name}</span>
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-slate-400">{{ sh: '沪市', sz: '深市', bj: '北交所' }[stock.market] || stock.market}</span>
                          <button
                            onClick={() => handleToggleStock(stock)}
                            disabled={busy}
                            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition disabled:opacity-50 ${
                              inTarget
                                ? 'bg-green-50 text-green-600 hover:bg-green-100'
                                : inOther
                                ? 'bg-amber-50 text-amber-600 hover:bg-amber-100'
                                : 'bg-sky-50 text-sky-600 hover:bg-sky-100'
                            }`}
                          >
                            {inTarget ? <><Check size={14} /> 已在</> : <><Plus size={14} /> {inOther ? '移入' : '添加'}</>}
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
              {showSearchDropdown && searchResults.length === 0 && !searchLoading && searchQuery.trim() && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-10 py-3 text-center text-sm text-slate-400">
                  未找到匹配股票
                </div>
              )}
            </div>
            {searchResults.length > 0 && (
              <button
                onClick={handleAddAllResults}
                disabled={searchResults.every((s) => !!watchlistMap[s.code])}
                className="px-3 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                全部添加
              </button>
            )}
          </div>
          <div className="text-xs text-slate-400 mt-2">
            先选择目标分组（可新建），再搜索股票；已在该分组的显示“已在”，点击可移除；未加入该分组的点击直接加入
          </div>
        </div>
      )}

      {lastUpdated && (
        <div className="text-xs text-slate-400 text-right">
          数据更新于 {lastUpdated}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-slate-400">加载中...</div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left w-10">
                  <input
                    type="checkbox"
                    checked={sorted.length > 0 && sorted.every((i) => selectedSymbols.includes(i.symbol))}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedSymbols((prev) => Array.from(new Set([...prev, ...sorted.map((i) => i.symbol)])))
                      } else {
                        setSelectedSymbols((prev) => prev.filter((sym) => !sorted.some((i) => i.symbol === sym)))
                      }
                    }}
                    className="h-4 w-4 text-sky-600 rounded border-slate-300 focus:ring-sky-500"
                  />
                </th>
                <th className="px-4 py-3 text-left font-medium cursor-pointer select-none hover:text-slate-700" onClick={() => handleSort('symbol')}>
                  代码{getSortIcon('symbol')}
                </th>
                <th className="px-4 py-3 text-left font-medium cursor-pointer select-none hover:text-slate-700" onClick={() => handleSort('name')}>
                  名称{getSortIcon('name')}
                </th>
                <th className="px-4 py-3 text-right font-medium cursor-pointer select-none hover:text-slate-700" onClick={() => handleSort('price')}>
                  最新价{getSortIcon('price')}
                </th>
                <th className="px-4 py-3 text-right font-medium cursor-pointer select-none hover:text-slate-700" onClick={() => handleSort('changePct')}>
                  涨跌幅{getSortIcon('changePct')}
                </th>
                <th className="px-4 py-3 text-right font-medium cursor-pointer select-none hover:text-slate-700" onClick={() => handleSort('score')}>
                  技术评分{getSortIcon('score')}
                </th>
                <th className="px-4 py-3 text-left font-medium cursor-pointer select-none hover:text-slate-700" onClick={() => handleSort('group')}>
                  分组{getSortIcon('group')}
                </th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sorted.map((item) => {
                const quote = item.quote
                const changePct = quote
                  ? ((quote.close - quote.open) / quote.open) * 100
                  : 0
                const checked = selectedSymbols.includes(item.symbol)
                const groupOptions = Array.from(new Set([...(groups || []), item.group].filter(Boolean)))
                return (
                  <tr key={item.symbol} className="hover:bg-slate-50 transition">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          setSelectedSymbols((prev) =>
                            prev.includes(item.symbol)
                              ? prev.filter((sym) => sym !== item.symbol)
                              : [...prev, item.symbol]
                          )
                        }}
                        className="h-4 w-4 text-sky-600 rounded border-slate-300 focus:ring-sky-500"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Link to={`/stock/${item.symbol}`} className="text-sky-600 hover:underline font-medium">
                        {item.symbol}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <Link to={`/stock/${item.symbol}`} className="text-sky-600 hover:underline font-medium">
                        {item.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right font-medium">
                      {quote ? quote.close.toFixed(2) : '-'}
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${changePct >= 0 ? 'text-up' : 'text-down'}`}>
                      <span className="mr-1">{changePct >= 0 ? '▲' : '▼'}</span>
                      {changePct >= 0 ? '+' : ''}
                      {changePct.toFixed(2)}%
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          (item.score || 0) >= 70
                            ? 'bg-red-50 text-red-600'
                            : (item.score || 0) >= 40
                            ? 'bg-amber-50 text-amber-600'
                            : 'bg-slate-50 text-slate-500'
                        }`}
                      >
                        {item.score || 0}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={item.group || '默认'}
                        onChange={async (e) => {
                          let newGroup = e.target.value
                          if (!newGroup || newGroup === item.group) return
                          if (newGroup === '__new__') {
                            const input = prompt('请输入新分组名称')
                            if (!input) return
                            newGroup = input
                          }
                          await updateWatchlistGroup(item.symbol, newGroup)
                          load()
                        }}
                        className="px-2 py-1 bg-slate-100 rounded text-xs text-slate-600 border border-transparent hover:border-slate-300 focus:outline-none focus:ring-1 focus:ring-sky-500"
                      >
                        {groupOptions.map((g) => (
                          <option key={g} value={g}>{g}</option>
                        ))}
                        <option value="__new__">+ 新建分组</option>
                      </select>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleDelete(item.symbol)}
                        className="p-1 text-slate-400 hover:text-red-500 transition"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="text-center py-12 text-slate-400">
              {filterQuery ? '无匹配结果' : '暂无自选股'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
