import React, { useEffect, useRef } from 'react'
import {
  createChart,
  IChartApi,
  ISeriesApi,
  LineData,
  HistogramData,
  AreaData,
} from 'lightweight-charts'

interface IntradayDataPoint {
  time: string
  price?: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number
}

interface IntradayChartProps {
  data: IntradayDataPoint[]
  height?: number
  avgPrice?: number
  prevClose?: number
}

export default function IntradayChart({
  data,
  height = 400,
  avgPrice,
  prevClose,
}: IntradayChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

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
        timeVisible: true,
      },
    })

    chartRef.current = chart

    // 价格线（面积图）
    const priceSeries = chart.addAreaSeries({
      topColor: 'rgba(239, 68, 68, 0.2)',
      bottomColor: 'rgba(239, 68, 68, 0.02)',
      lineColor: '#ef4444',
      lineWidth: 1,
    })

    const priceData: AreaData[] = data.map((row) => ({
      time: row.time.slice(11, 16) as any, // HH:MM
      value: row.price ?? row.close ?? 0,
    }))
    priceSeries.setData(priceData)

    // 均价线
    if (avgPrice && avgPrice > 0) {
      const avgSeries = chart.addLineSeries({
        color: '#f59e0b',
        lineWidth: 1,
        lineStyle: 2, // dashed
      })
      const avgData: LineData[] = data.map((row) => ({
        time: row.time.slice(11, 16) as any,
        value: avgPrice,
      }))
      avgSeries.setData(avgData)
    }

    // 昨收线
    if (prevClose && prevClose > 0) {
      const prevSeries = chart.addLineSeries({
        color: '#9ca3af',
        lineWidth: 1,
        lineStyle: 3, // dotted
      })
      const prevData: LineData[] = data.map((row) => ({
        time: row.time.slice(11, 16) as any,
        value: prevClose,
      }))
      prevSeries.setData(prevData)
    }

    // 成交量
    const volumeSeries = chart.addHistogramSeries({
      color: '#26a69a',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '',
    })
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.85,
        bottom: 0,
      },
    })

    const volumeData: HistogramData[] = data.map((row) => ({
      time: row.time.slice(11, 16) as any,
      value: row.volume,
      color: (row.price ?? row.close ?? 0) >= (prevClose || 0) ? '#ef4444' : '#22c55e',
    }))
    volumeSeries.setData(volumeData)

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
  }, [data, height, avgPrice, prevClose])

  return <div ref={chartContainerRef} className="w-full" />
}
