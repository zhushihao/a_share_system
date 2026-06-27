import React, { useEffect, useRef } from 'react'
import { createChart, LineStyle } from 'lightweight-charts'
import type { OHLCVRecord } from '@/types'

interface IndicatorPanelProps {
  data: OHLCVRecord[]
  activeTab: 'macd' | 'kdj' | 'rsi'
  onTabChange: (tab: 'macd' | 'kdj' | 'rsi') => void
}

const formatDate = (dateStr: string): string => {
  if (dateStr.length === 8 && !dateStr.includes('-')) {
    return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`
  }
  return dateStr
}

export default function IndicatorPanel({ data, activeTab, onTabChange }: IndicatorPanelProps) {
  return (
    <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
      <div className="flex items-center gap-2 mb-3">
        {[
          { key: 'macd' as const, label: 'MACD' },
          { key: 'kdj' as const, label: 'KDJ' },
          { key: 'rsi' as const, label: 'RSI' },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className={`px-3 py-1 text-xs rounded-md transition font-medium ${
              activeTab === tab.key
                ? 'bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="h-[140px]">
        {activeTab === 'macd' && <MACDChart data={data} />}
        {activeTab === 'kdj' && <KDJChart data={data} />}
        {activeTab === 'rsi' && <RSIChart data={data} />}
      </div>
    </div>
  )
}

// ───────────────────────────────────────────────
// MACD 副图
// ───────────────────────────────────────────────
function MACDChart({ data }: { data: OHLCVRecord[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 140,
      layout: { background: { color: '#ffffff' }, textColor: '#333333' },
      grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
      rightPriceScale: { borderColor: '#e0e0e0' },
      timeScale: { borderColor: '#e0e0e0', visible: false },
      crosshair: { mode: 1 },
    })

    // MACD柱状图：直接用 macd_bar
    const histData = data
      .filter((r) => r.macd_bar != null && !isNaN(r.macd_bar))
      .map((r) => ({
        time: formatDate(r.date) as any,
        value: r.macd_bar!,
        color: (r.macd_bar || 0) >= 0 ? '#ef4444' : '#22c55e',
      }))

    const histSeries = chart.addHistogramSeries({
      priceScaleId: '',
    })
    histSeries.setData(histData)

    histSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.2, bottom: 0.2 },
    })

    // DIF线
    const difData = data
      .filter((r) => r.macd_dif != null && !isNaN(r.macd_dif))
      .map((r) => ({ time: formatDate(r.date) as any, value: r.macd_dif }))
    if (difData.length > 0) {
      const difSeries = chart.addLineSeries({ color: '#3b82f6', lineWidth: 1 })
      difSeries.setData(difData)
    }

    // DEA线
    const deaData = data
      .filter((r) => r.macd_dea != null && !isNaN(r.macd_dea))
      .map((r) => ({ time: formatDate(r.date) as any, value: r.macd_dea }))
    if (deaData.length > 0) {
      const deaSeries = chart.addLineSeries({ color: '#f97316', lineWidth: 1 })
      deaSeries.setData(deaData)
    }

    chart.timeScale().fitContent()

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [data])

  return <div ref={containerRef} className="w-full h-full" />
}

// ───────────────────────────────────────────────
// KDJ 副图
// ───────────────────────────────────────────────
function KDJChart({ data }: { data: OHLCVRecord[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 140,
      layout: { background: { color: '#ffffff' }, textColor: '#333333' },
      grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
      rightPriceScale: { borderColor: '#e0e0e0' },
      timeScale: { borderColor: '#e0e0e0', visible: false },
      crosshair: { mode: 1 },
    })

    const kData = data
      .filter((r) => r.kdj_k != null && !isNaN(r.kdj_k))
      .map((r) => ({ time: formatDate(r.date) as any, value: r.kdj_k }))
    const dData = data
      .filter((r) => r.kdj_d != null && !isNaN(r.kdj_d))
      .map((r) => ({ time: formatDate(r.date) as any, value: r.kdj_d }))
    const jData = data
      .filter((r) => r.kdj_j != null && !isNaN(r.kdj_j))
      .map((r) => ({ time: formatDate(r.date) as any, value: r.kdj_j }))

    if (kData.length > 0) {
      const kSeries = chart.addLineSeries({ color: '#3b82f6', lineWidth: 1 })
      kSeries.setData(kData)
    }
    if (dData.length > 0) {
      const dSeries = chart.addLineSeries({ color: '#f97316', lineWidth: 1 })
      dSeries.setData(dData)
    }
    if (jData.length > 0) {
      const jSeries = chart.addLineSeries({ color: '#a855f7', lineWidth: 1 })
      jSeries.setData(jData)
    }

    chart.timeScale().fitContent()

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [data])

  return <div ref={containerRef} className="w-full h-full" />
}

// ───────────────────────────────────────────────
// RSI 副图
// ───────────────────────────────────────────────
function RSIChart({ data }: { data: OHLCVRecord[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 140,
      layout: { background: { color: '#ffffff' }, textColor: '#333333' },
      grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
      rightPriceScale: { borderColor: '#e0e0e0' },
      timeScale: { borderColor: '#e0e0e0', visible: false },
      crosshair: { mode: 1 },
    })

    const rsi6Data = data
      .filter((r) => r.rsi6 != null && !isNaN(r.rsi6))
      .map((r) => ({ time: formatDate(r.date) as any, value: r.rsi6 }))
    const rsi12Data = data
      .filter((r) => r.rsi12 != null && !isNaN(r.rsi12))
      .map((r) => ({ time: formatDate(r.date) as any, value: r.rsi12 }))
    const rsi24Data = data
      .filter((r) => r.rsi24 != null && !isNaN(r.rsi24))
      .map((r) => ({ time: formatDate(r.date) as any, value: r.rsi24 }))

    if (rsi6Data.length > 0) {
      const s6 = chart.addLineSeries({ color: '#3b82f6', lineWidth: 1 })
      s6.setData(rsi6Data)
    }
    if (rsi12Data.length > 0) {
      const s12 = chart.addLineSeries({ color: '#f97316', lineWidth: 1 })
      s12.setData(rsi12Data)
    }
    if (rsi24Data.length > 0) {
      const s24 = chart.addLineSeries({ color: '#a855f7', lineWidth: 1 })
      s24.setData(rsi24Data)
    }

    // 超买线 70（红色虚线）
    const firstTime = formatDate(data[0].date) as any
    const lastTime = formatDate(data[data.length - 1].date) as any
    const overbought = chart.addLineSeries({
      color: '#ef4444',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
    })
    overbought.setData([
      { time: firstTime, value: 70 },
      { time: lastTime, value: 70 },
    ])

    // 超卖线 30（绿色虚线）
    const oversold = chart.addLineSeries({
      color: '#22c55e',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
    })
    oversold.setData([
      { time: firstTime, value: 30 },
      { time: lastTime, value: 30 },
    ])

    chart.timeScale().fitContent()

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [data])

  return <div ref={containerRef} className="w-full h-full" />
}
