import React, { useEffect, useRef } from 'react'
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  LineData,
  LineStyle,
  SeriesMarker,
} from 'lightweight-charts'
import type { PatternData, VolumeNodeData, SupportResistanceData, OHLCVRecord, TradingSignal } from '@/types'

interface ChartProps {
  data: OHLCVRecord[]
  height?: number
  patterns?: PatternData[]
  volumeAnalysis?: VolumeNodeData[]
  supportResistance?: SupportResistanceData
  signal?: TradingSignal | null
  indicators?: {
    ma5?: boolean
    ma20?: boolean
    ma60?: boolean
    boll?: boolean
    supportResistance?: boolean
  }
}

export default function TradingViewChart({
  data,
  height = 400,
  patterns = [],
  volumeAnalysis = [],
  supportResistance,
  signal,
  indicators = {},
}: ChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  const formatDate = (dateStr: string): string => {
    if (dateStr.length === 8 && !dateStr.includes('-')) {
      return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`
    }
    return dateStr
  }

  useEffect(() => {
    if (!chartContainerRef.current || data.length === 0) return

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#333333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: '#e0e0e0',
      },
      timeScale: {
        borderColor: '#e0e0e0',
      },
    })

    chartRef.current = chart

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#ef4444',
      downColor: '#22c55e',
      borderUpColor: '#ef4444',
      borderDownColor: '#22c55e',
      wickUpColor: '#ef4444',
      wickDownColor: '#22c55e',
    })
    candleSeriesRef.current = candleSeries

    const volumeSeries = chart.addHistogramSeries({
      color: '#26a69a',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '',
    })
    volumeSeriesRef.current = volumeSeries

    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    })

    const candleData: CandlestickData[] = data.map((row) => ({
      time: formatDate(row.date) as any,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }))

    const volumeData: HistogramData[] = data.map((row) => ({
      time: formatDate(row.date) as any,
      value: row.volume,
      color: row.close >= row.open ? '#ef4444' : '#22c55e',
    }))

    candleSeries.setData(candleData)
    volumeSeries.setData(volumeData)

    const firstTime = data.length > 0 ? (formatDate(data[0].date) as any) : null
    const lastTime = data.length > 0 ? (formatDate(data[data.length - 1].date) as any) : null

    // ───────────────────────────────────────────────
    // A. 主图指标叠加（MA + BOLL）
    // ───────────────────────────────────────────────

    const addLineSeries = (values: (number | undefined)[], color: string, lineStyle?: LineStyle) => {
      const lineData: LineData[] = data
        .map((row, i) => ({
          time: formatDate(row.date) as any,
          value: values[i]!,
        }))
        .filter((p) => p.value != null && !isNaN(p.value))
      if (lineData.length === 0) return null
      const series = chart.addLineSeries({
        color,
        lineWidth: 1,
        lineStyle: lineStyle ?? LineStyle.Solid,
      })
      series.setData(lineData)
      return series
    }

    // MA（根据 indicators 控制开关）
    if (indicators.ma5 !== false) {
      addLineSeries(data.map((r) => r.ma5), '#3b82f6')      // MA5 蓝色
    }
    if (indicators.ma20 !== false) {
      addLineSeries(data.map((r) => r.ma20), '#a855f7')     // MA20 紫色
    }
    if (indicators.ma60 !== false) {
      addLineSeries(data.map((r) => r.ma60), '#9ca3af')     // MA60 灰色
    }

    // BOLL
    if (indicators.boll !== false) {
      addLineSeries(data.map((r) => r.boll_up), '#fca5a5', LineStyle.Dashed)   // 上轨 浅红色虚线（压力）
      addLineSeries(data.map((r) => r.boll_mid), '#6b7280', LineStyle.Dashed)   // 中轨 中性灰色虚线
      addLineSeries(data.map((r) => r.boll_down), '#86efac', LineStyle.Dashed)  // 下轨 浅绿色虚线（支撑）
    }

    // ───────────────────────────────────────────────
    // B. 形态标记（Marker）
    // ───────────────────────────────────────────────
    const markers: SeriesMarker<any>[] = []
    const markerKeys = new Set<string>() // 用于去重：同一时间+位置+文本的标记只保留一个

    const addMarker = (m: SeriesMarker<any>) => {
      const key = `${m.time}-${m.position}-${m.text}-${m.shape}`
      if (!markerKeys.has(key)) {
        markerKeys.add(key)
        markers.push(m)
      }
    }

    const isTopPattern = (name: string) =>
      /double_top|head_shoulder_top|triple_top|top|reversal_top/i.test(name)
    const isBottomPattern = (name: string) =>
      /double_bottom|head_shoulder_bottom|triple_bottom|bottom|reversal_bottom/i.test(name)
    const isVShape = (name: string) =>
      /v_reversal|v_shape/i.test(name)

    // 安全获取形态日期（部分形态如V型反转使用 pivot_date，斐波那契无日期）
    const getPatternDate = (p: any): string | null => {
      if (p.end_date) return p.end_date
      if (p.pivot_date) return p.pivot_date
      if (p.start_date) return p.start_date
      return null
    }

    patterns.forEach((p) => {
      const dateStr = getPatternDate(p)
      if (!dateStr) return // 跳过无日期形态（如斐波那契回调位）
      const time = formatDate(dateStr) as any
      // 形态短名称映射（避免标记文字过长）
      const patternShortMap: Record<string, string> = {
        double_top: '双顶',
        double_bottom: '双底',
        head_shoulder_top: '头肩顶',
        head_shoulder_bottom: '头肩底',
        triangle: '三角',
        v_reversal: 'V转',
        fibonacci_retracement: '斐波',
      }
      const shortName = patternShortMap[p.pattern] || p.pattern.slice(0, 4)
      if (isTopPattern(p.pattern)) {
        addMarker({
          time,
          position: 'aboveBar',
          color: '#ef4444',
          shape: 'arrowDown',
          text: shortName,
        })
      } else if (isBottomPattern(p.pattern)) {
        addMarker({
          time,
          position: 'belowBar',
          color: '#22c55e',
          shape: 'arrowUp',
          text: shortName,
        })
      } else if (isVShape(p.pattern)) {
        const subtype = (p as any).subtype
        if (subtype === 'bottom') {
          addMarker({
            time,
            position: 'belowBar',
            color: '#22c55e',
            shape: 'arrowUp',
            text: 'V底',
          })
        } else if (subtype === 'top') {
          addMarker({
            time,
            position: 'aboveBar',
            color: '#ef4444',
            shape: 'arrowDown',
            text: 'V顶',
          })
        } else {
          addMarker({
            time,
            position: 'inBar',
            color: '#3b82f6',
            shape: 'circle',
            text: 'V转',
          })
        }
      }
    })

    // ───────────────────────────────────────────────
    // C. 量价节点标记（根据 direction 显示正确语义）
    // ───────────────────────────────────────────────
    volumeAnalysis.forEach((v) => {
      const time = formatDate(v.date) as any
      const type = v.type
      const direction = v.direction
      
      // A股红涨绿跌：up=红色/belowBar+arrowUp, down=绿色/aboveBar+arrowDown
      const isUp = direction === 'up' || (!direction && /breakout|contraction/.test(type))
      
      if (/volume_breakout|breakout|突破|放量|突/.test(type)) {
        addMarker({
          time,
          position: isUp ? 'belowBar' : 'aboveBar',
          color: isUp ? '#ef4444' : '#22c55e',
          shape: isUp ? 'arrowUp' : 'arrowDown',
          text: '突',
        })
      } else if (/volume_contraction|contraction|缩量|回调|缩/.test(type)) {
        addMarker({
          time,
          position: isUp ? 'belowBar' : 'aboveBar',
          color: isUp ? '#ef4444' : '#22c55e',
          shape: isUp ? 'arrowUp' : 'arrowDown',
          text: '缩',
        })
      } else if (/volume_spike|spike|天量/.test(type)) {
        addMarker({
          time,
          position: isUp ? 'belowBar' : 'aboveBar',
          color: isUp ? '#ef4444' : '#22c55e',
          shape: isUp ? 'arrowUp' : 'arrowDown',
          text: '天量',
        })
      } else if (/volume_dry|dry|地量/.test(type)) {
        addMarker({
          time,
          position: 'belowBar',
          color: '#3b82f6',
          shape: 'circle',
          text: '地量',
        })
      }
    })

    // 统一设置所有标记（形态+量价+买卖点）
    if (markers.length > 0) {
      candleSeries.setMarkers(markers)
    }

    // ───────────────────────────────────────────────
    // D. 支撑阻力水平线（根据 indicators 控制开关）
    // ───────────────────────────────────────────────
    if (indicators.supportResistance !== false && supportResistance && data.length > 0 && firstTime && lastTime) {
      supportResistance.support?.forEach((price) => {
        const line = chart.addLineSeries({
          color: '#22c55e',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          lastValueVisible: false,
          title: `支撑 ${price.toFixed(2)}`,
        })
        line.setData([
          { time: firstTime, value: price },
          { time: lastTime, value: price },
        ])
      })

      supportResistance.resistance?.forEach((price) => {
        const line = chart.addLineSeries({
          color: '#ef4444',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          lastValueVisible: false,
          title: `阻力 ${price.toFixed(2)}`,
        })
        line.setData([
          { time: firstTime, value: price },
          { time: lastTime, value: price },
        ])
      })
    }

    // ───────────────────────────────────────────────
    // E. 买卖点标记 + 止损止盈水平线 + 风险收益比标注
    // ───────────────────────────────────────────────
    if (signal && signal.type !== 'HOLD' && data.length > 0) {
      const lastDate = formatDate(data[data.length - 1].date) as any

      // 买卖点标记（最后一根K线）—— 采用国际惯例：BUY=蓝色，SELL=红色/橙色
      if (signal.type === 'BUY') {
        addMarker({
          time: lastDate,
          position: 'belowBar',
          color: '#3b82f6',  // 蓝色买入，与红色止损区分
          shape: 'arrowUp',
          text: '买入',
          size: 2,
        })
      } else if (signal.type === 'SELL') {
        addMarker({
          time: lastDate,
          position: 'aboveBar',
          color: '#f97316',  // 橙色卖出，与绿色止盈区分
          shape: 'arrowDown',
          text: '卖出',
          size: 2,
        })
      }

      // 止损水平线（红色虚线）
      if (signal.stop_loss > 0) {
        const slLine = chart.addLineSeries({
          color: '#ef4444',
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          lastValueVisible: true,
          title: `止损 ${signal.stop_loss.toFixed(2)}`,
        })
        slLine.setData([
          { time: firstTime, value: signal.stop_loss },
          { time: lastTime, value: signal.stop_loss },
        ])
      }

      // 止盈水平线（绿色虚线）
      if (signal.take_profit > 0) {
        const tpLine = chart.addLineSeries({
          color: '#22c55e',
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          lastValueVisible: true,
          title: `止盈 ${signal.take_profit.toFixed(2)}`,
        })
        tpLine.setData([
          { time: firstTime, value: signal.take_profit },
          { time: lastTime, value: signal.take_profit },
        ])
      }

      // 风险收益比标注（入场价水平线，浅蓝色）
      if (signal.entry_price > 0) {
        const entryLine = chart.addLineSeries({
          color: '#3b82f6',
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          lastValueVisible: true,
          title: `入场 ${signal.entry_price.toFixed(2)}`,
        })
        entryLine.setData([
          { time: firstTime, value: signal.entry_price },
          { time: lastTime, value: signal.entry_price },
        ])
      }
    }

    chart.timeScale().fitContent()

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [data, height, patterns, volumeAnalysis, supportResistance, signal, indicators])

  return <div ref={chartContainerRef} className="w-full" />
}
