import React, { useState, useEffect } from 'react'
import {
  Database,
  HardDrive,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Download,
  Search,
  Loader2,
  FileJson,
  FileSpreadsheet,
  RefreshCw,
  Activity,
  FolderOpen,
  List,
} from 'lucide-react'
import {
  fetchDataOverview,
  fetchStockList,
  diagnoseData,
  exportData,
  fetchDataHealth,
} from '@/api/client'

interface StockItem {
  code: string
  name: string
  market: string
}

export default function DataManager() {
  const [overview, setOverview] = useState<any>(null)
  const [stockList, setStockList] = useState<StockItem[]>([])
  const [diagnosis, setDiagnosis] = useState<any>(null)
  const [diagnoseSymbol, setDiagnoseSymbol] = useState('000001')
  const [exportSymbol, setExportSymbol] = useState('000001')
  const [exportFormat, setExportFormat] = useState('csv')
  const [exportPeriod, setExportPeriod] = useState('daily')
  const [exportAdjust, setExportAdjust] = useState('qfq')
  const [exportResult, setExportResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'stocks' | 'diagnose' | 'export'>('overview')
  const [stockMarket, setStockMarket] = useState('')
  const [health, setHealth] = useState<any>(null)

  useEffect(() => {
    loadOverview()
    loadHealth()
  }, [])

  const loadOverview = async () => {
    try {
      const data = await fetchDataOverview()
      setOverview(data)
    } catch (e) {
      console.error('Failed to load overview', e)
    }
  }

  const loadHealth = async () => {
    try {
      const data = await fetchDataHealth()
      setHealth(data)
    } catch (e) {
      console.error('Failed to load health', e)
    }
  }

  const loadStockList = async () => {
    setLoading(true)
    try {
      const data = await fetchStockList(stockMarket || undefined, 1000)
      setStockList(data.stocks || [])
    } catch (e) {
      console.error('Failed to load stock list', e)
    } finally {
      setLoading(false)
    }
  }

  const handleDiagnose = async () => {
    setLoading(true)
    try {
      const data = await diagnoseData(diagnoseSymbol)
      setDiagnosis(data)
    } catch (e) {
      console.error('Diagnose failed', e)
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async () => {
    setLoading(true)
    try {
      const data = await exportData({
        symbol: exportSymbol,
        period: exportPeriod,
        adjust: exportAdjust,
        format: exportFormat,
      })
      setExportResult(data)
      // If CSV, create download
      if (data.format === 'csv' && data.data) {
        const blob = new Blob([data.data], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', `${exportSymbol}_${exportPeriod}_${exportAdjust}.csv`)
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      }
    } catch (e) {
      console.error('Export failed', e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <Database size={22} />
          数据管理
        </h2>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200">
        <div className="flex border-b border-slate-200">
          {[
            { key: 'overview', label: '数据概览', icon: <Activity size={16} /> },
            { key: 'stocks', label: '股票列表', icon: <List size={16} /> },
            { key: 'diagnose', label: '数据诊断', icon: <AlertTriangle size={16} /> },
            { key: 'export', label: '数据导出', icon: <Download size={16} /> },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium transition border-b-2 ${
                activeTab === tab.key
                  ? 'border-sky-600 text-sky-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {overview && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <div className="flex items-center gap-2 mb-2">
                      <FolderOpen size={16} className="text-slate-400" />
                      <span className="text-sm text-slate-500">通达信目录</span>
                    </div>
                    <p className="text-sm font-medium text-slate-700">{overview.tdx_dir}</p>
                    <p className={`text-xs mt-1 ${overview.tdx_dir_exists ? 'text-emerald-600' : 'text-red-500'}`}>
                      {overview.tdx_dir_exists ? '存在' : '不存在'}
                    </p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <div className="flex items-center gap-2 mb-2">
                      <HardDrive size={16} className="text-slate-400" />
                      <span className="text-sm text-slate-500">数据文件</span>
                    </div>
                    <p className="text-lg font-semibold text-slate-800">
                      {overview.tdx_files?.total_files?.toLocaleString() || 'N/A'}
                    </p>
                    <p className="text-xs text-slate-400">
                      {overview.tdx_files?.total_size_mb?.toFixed(1) || 0} MB
                    </p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <div className="flex items-center gap-2 mb-2">
                      <List size={16} className="text-slate-400" />
                      <span className="text-sm text-slate-500">股票数量</span>
                    </div>
                    <p className="text-lg font-semibold text-slate-800">
                      {overview.stock_count?.toLocaleString() || 'N/A'}
                    </p>
                    <p className="text-xs text-slate-400">只</p>
                  </div>
                </div>
              )}

              {health && (
                <div className="p-4 bg-slate-50 rounded-xl">
                  <h3 className="text-sm font-medium text-slate-700 mb-3">数据源健康状态</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <HealthItem
                      label="离线数据"
                      available={health.health?.offline_available}
                    />
                    <HealthItem
                      label="实时数据"
                      available={health.health?.realtime_available}
                    />
                    <HealthItem
                      label="通达信目录"
                      available={health.health?.tdxdir_exists}
                    />
                    <HealthItem
                      label="网络连接"
                      available={health.health?.network_available}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Stock List Tab */}
          {activeTab === 'stocks' && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <select
                  value={stockMarket}
                  onChange={(e) => setStockMarket(e.target.value)}
                  className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="">全部市场</option>
                  <option value="sh">上海</option>
                  <option value="sz">深圳</option>
                  <option value="bj">北京</option>
                </select>
                <button
                  onClick={loadStockList}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50"
                >
                  {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                  加载
                </button>
                <span className="text-sm text-slate-400">
                  {stockList.length > 0 ? `共 ${stockList.length} 只` : ''}
                </span>
              </div>

              {stockList.length > 0 && (
                <div className="overflow-auto max-h-96 border border-slate-200 rounded-lg">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">代码</th>
                        <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">名称</th>
                        <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">市场</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stockList.map((stock) => (
                        <tr key={stock.code} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="py-2 px-3 text-slate-700 font-mono">{stock.code}</td>
                          <td className="py-2 px-3 text-slate-700">{stock.name}</td>
                          <td className="py-2 px-3">
                            <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                              stock.market === 'sh' ? 'bg-red-100 text-red-700' :
                              stock.market === 'sz' ? 'bg-blue-100 text-blue-700' :
                              'bg-emerald-100 text-emerald-700'
                            }`}>
                              {stock.market === 'sh' ? '沪' : stock.market === 'sz' ? '深' : '京'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Diagnose Tab */}
          {activeTab === 'diagnose' && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <input
                  type="text"
                  value={diagnoseSymbol}
                  onChange={(e) => setDiagnoseSymbol(e.target.value)}
                  placeholder="输入股票代码"
                  className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
                <button
                  onClick={handleDiagnose}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50"
                >
                  {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                  诊断
                </button>
              </div>

              {diagnosis && (
                <div className="space-y-4">
                  {diagnosis.available === false ? (
                    <div className="p-4 bg-red-50 rounded-xl border border-red-200">
                      <div className="flex items-center gap-2 text-red-700">
                        <XCircle size={18} />
                        <span className="font-medium">数据不可用</span>
                      </div>
                      <p className="text-sm text-red-600 mt-1">{diagnosis.message}</p>
                    </div>
                  ) : (
                    <>
                      <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-200">
                        <div className="flex items-center gap-2 text-emerald-700">
                          <CheckCircle size={18} />
                          <span className="font-medium">数据可用</span>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="p-3 bg-slate-50 rounded-lg">
                          <p className="text-xs text-slate-500">总记录数</p>
                          <p className="text-lg font-semibold text-slate-800">
                            {diagnosis.diagnosis?.total_rows}
                          </p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-lg">
                          <p className="text-xs text-slate-500">零成交量</p>
                          <p className="text-lg font-semibold text-slate-800">
                            {diagnosis.diagnosis?.zero_volume_days}
                          </p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-lg">
                          <p className="text-xs text-slate-500">价格异常</p>
                          <p className="text-lg font-semibold text-slate-800">
                            {diagnosis.diagnosis?.price_anomalies}
                          </p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-lg">
                          <p className="text-xs text-slate-500">日期断层</p>
                          <p className="text-lg font-semibold text-slate-800">
                            {diagnosis.diagnosis?.gap_count || 0}
                          </p>
                        </div>
                      </div>

                      {diagnosis.diagnosis?.gaps && diagnosis.diagnosis.gaps.length > 0 && (
                        <div className="p-4 bg-slate-50 rounded-xl">
                          <h4 className="text-sm font-medium text-slate-700 mb-2">日期断层</h4>
                          <div className="space-y-1">
                            {diagnosis.diagnosis.gaps.map((gap: any, i: number) => (
                              <div key={i} className="text-sm text-slate-600">
                                {gap.from} ~ {gap.to}（间隔 {gap.gap_days} 天）
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Export Tab */}
          {activeTab === 'export' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">股票代码</label>
                  <input
                    type="text"
                    value={exportSymbol}
                    onChange={(e) => setExportSymbol(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">周期</label>
                  <select
                    value={exportPeriod}
                    onChange={(e) => setExportPeriod(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    <option value="daily">日线</option>
                    <option value="weekly">周线</option>
                    <option value="monthly">月线</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">复权</label>
                  <select
                    value={exportAdjust}
                    onChange={(e) => setExportAdjust(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    <option value="qfq">前复权</option>
                    <option value="hfq">后复权</option>
                    <option value="none">不复权</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1">格式</label>
                  <select
                    value={exportFormat}
                    onChange={(e) => setExportFormat(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    <option value="csv">CSV</option>
                    <option value="json">JSON</option>
                  </select>
                </div>
              </div>

              <button
                onClick={handleExport}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50"
              >
                {loading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                {exportFormat === 'csv' ? '导出 CSV' : '导出 JSON'}
              </button>

              {exportResult && (
                <div className="p-4 bg-slate-50 rounded-xl">
                  <div className="flex items-center gap-2 text-emerald-700">
                    <CheckCircle size={18} />
                    <span className="font-medium">导出成功</span>
                  </div>
                  <p className="text-sm text-slate-600 mt-1">
                    {exportResult.symbol} | {exportResult.period} | 共 {exportResult.count} 条记录
                  </p>
                  {exportResult.format === 'json' && (
                    <pre className="mt-3 p-3 bg-slate-800 text-slate-200 rounded-lg text-xs overflow-auto max-h-64">
                      {JSON.stringify(exportResult.data.slice(0, 5), null, 2)}
                      {exportResult.data.length > 5 && '\n...'}
                    </pre>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function HealthItem({ label, available }: { label: string; available?: boolean }) {
  return (
    <div className="flex items-center gap-2 p-3 bg-white rounded-lg border border-slate-200">
      {available ? (
        <CheckCircle size={16} className="text-emerald-500" />
      ) : (
        <XCircle size={16} className="text-red-400" />
      )}
      <span className="text-sm text-slate-600">{label}</span>
    </div>
  )
}
