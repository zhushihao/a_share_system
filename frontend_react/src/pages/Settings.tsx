import React, { useState, useEffect } from 'react'
import { Save, RotateCcw, AlertTriangle, CheckCircle, Settings as SettingsIcon } from 'lucide-react'
import {
  fetchSettings,
  updateSettingsBatch,
  resetSettings,
} from '@/api/client'

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    try {
      const data = await fetchSettings()
      if (data.settings) {
        setSettings(data.settings)
      }
    } catch (e) {
      console.error('Failed to load settings', e)
      setError('加载设置失败')
    }
  }

  const handleSave = async () => {
    setLoading(true)
    setError('')
    try {
      await updateSettingsBatch({
        tdx_dir: settings.tdx_dir,
        theme: settings.theme,
        default_adjust: settings.default_adjust,
        default_period: settings.default_period,
        default_initial_cash: settings.default_initial_cash,
        default_commission_rate: settings.default_commission_rate,
        default_slippage: settings.default_slippage,
        ai_api_key: settings.ai_api_key,
        ai_model: settings.ai_model,
        ai_enabled: settings.ai_enabled,
        offline_mode: settings.offline_mode,
        language: settings.language,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError('保存失败')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    if (!confirm('确定重置所有设置为默认值？')) return
    try {
      await resetSettings()
      loadSettings()
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError('重置失败')
    }
  }

  const updateField = (key: string, value: any) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
        <h2 className="text-lg font-semibold text-slate-800 mb-6 flex items-center gap-2">
          <SettingsIcon size={20} />
          系统设置
        </h2>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
            <AlertTriangle size={16} />
            {error}
          </div>
        )}

        {saved && (
          <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-700 text-sm flex items-center gap-2">
            <CheckCircle size={16} />
            保存成功
          </div>
        )}

        <div className="space-y-5">
          {/* Data Source */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">通达信数据目录</label>
            <input
              type="text"
              value={settings.tdx_dir || 'D:/TDX'}
              onChange={(e) => updateField('tdx_dir', e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
            <p className="text-xs text-slate-400 mt-1">本地通达信安装目录，用于读取离线行情数据</p>
          </div>

          {/* Theme */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">界面主题</label>
            <div className="flex gap-3">
              <button
                onClick={() => updateField('theme', 'light')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                  settings.theme === 'light' ? 'bg-sky-600 text-white' : 'bg-slate-100 text-slate-600'
                }`}
              >
                浅色
              </button>
              <button
                onClick={() => updateField('theme', 'dark')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                  settings.theme === 'dark' ? 'bg-sky-600 text-white' : 'bg-slate-100 text-slate-600'
                }`}
              >
                深色
              </button>
            </div>
          </div>

          {/* Default Period */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">默认周期</label>
            <select
              value={settings.default_period || 'daily'}
              onChange={(e) => updateField('default_period', e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <option value="daily">日线</option>
              <option value="weekly">周线</option>
              <option value="monthly">月线</option>
            </select>
          </div>

          {/* Default Adjust */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">默认复权</label>
            <select
              value={settings.default_adjust || 'qfq'}
              onChange={(e) => updateField('default_adjust', e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <option value="qfq">前复权</option>
              <option value="hfq">后复权</option>
              <option value="none">不复权</option>
            </select>
          </div>

          {/* Backtest Defaults */}
          <div className="pt-4 border-t border-slate-100">
            <h3 className="text-sm font-medium text-slate-700 mb-3">回测默认参数</h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">初始资金</label>
                <input
                  type="number"
                  value={settings.default_initial_cash || 100000}
                  onChange={(e) => updateField('default_initial_cash', Number(e.target.value))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">手续费率</label>
                <input
                  type="number"
                  step={0.0001}
                  value={settings.default_commission_rate || 0.0003}
                  onChange={(e) => updateField('default_commission_rate', Number(e.target.value))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>
            </div>
          </div>

          {/* AI Settings */}
          <div className="pt-4 border-t border-slate-100">
            <h3 className="text-sm font-medium text-slate-700 mb-3">AI 投研（预留）</h3>
            <div>
              <label className="block text-xs text-slate-500 mb-1">API Key</label>
              <input
                type="password"
                value={settings.ai_api_key || ''}
                onChange={(e) => updateField('ai_api_key', e.target.value)}
                placeholder="未配置"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
              <p className="text-xs text-slate-400 mt-1">配置后可使用 AI 投研功能</p>
            </div>
          </div>

          {/* Actions */}
          <div className="pt-4 border-t border-slate-100 flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 transition disabled:opacity-50"
            >
              <Save size={16} />
              {loading ? '保存中...' : '保存设置'}
            </button>
            <button
              onClick={handleReset}
              className="flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-600 rounded-lg text-sm font-medium hover:bg-slate-200 transition"
            >
              <RotateCcw size={16} />
              重置默认
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200 mt-4">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">关于</h2>
        <p className="text-sm text-slate-600">
          Quant Workbench v1.0 — 本地金融分析工作台
        </p>
        <p className="text-sm text-slate-400 mt-2">
          基于 FastAPI + React + mootdx 构建
        </p>
      </div>
    </div>
  )
}
