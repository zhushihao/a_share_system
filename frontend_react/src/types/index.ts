export interface StandardQuote {
  symbol: string
  name?: string
  timestamp: string
  date?: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number
  pre_close?: number
  source: string
  freq: string
}

export interface OHLCVRecord {
  date: string
  code: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number
  ma5?: number
  ma10?: number
  ma20?: number
  ma60?: number
  boll_up?: number
  boll_mid?: number
  boll_down?: number
  macd_dif?: number
  macd_dea?: number
  macd_bar?: number
  kdj_k?: number
  kdj_d?: number
  kdj_j?: number
  rsi6?: number
  rsi12?: number
  rsi24?: number
}

export interface PatternData {
  pattern: string
  display_name?: string
  confidence: number
  start_date: string
  end_date: string
  description: string
  position?: 'top' | 'bottom' | 'breakout'
}

export interface VolumeNodeData {
  date: string
  type: string
  direction?: 'up' | 'down' | 'neutral'
  description: string
  volume_ratio?: number
}

export interface SupportResistanceData {
  support: number[]
  resistance: number[]
  levels: {
    price: number
    type: 'support' | 'resistance'
    strength: number
  }[]
}

export interface WatchlistItem {
  id: string
  symbol: string
  name: string
  group: string
  added_at: string
  notes?: string
  tags?: string[]
  alert_price_high?: number
  alert_price_low?: number
}

export interface WatchlistWithQuote extends WatchlistItem {
  quote?: StandardQuote
  indicators?: Record<string, number | null>
  score?: number
}

export interface TechIndicators {
  ma5?: number
  ma10?: number
  ma20?: number
  ma60?: number
  kdj_k?: number
  kdj_d?: number
  kdj_j?: number
  macd_dif?: number
  macd_dea?: number
  macd_bar?: number
  rsi6?: number
  rsi12?: number
  rsi24?: number
  boll_mid?: number
  boll_up?: number
  boll_down?: number
  obv?: number
  dmi_pdi?: number
  dmi_mdi?: number
  dmi_adx?: number
}

export interface SignalItem {
  id?: string
  symbol: string
  name: string
  timestamp: string
  signal_type: 'BUY' | 'SELL' | 'WATCH' | 'ALERT'
  signal_type_label?: string
  strategy: string
  strategy_label?: string
  category: 'daily' | 'intraday'
  description: string
  confidence: number
  price: number
  target_price?: number
  stop_loss?: number
  extra_data?: Record<string, any>
  acknowledged?: boolean
  status?: string
  pnl_pct?: number
  exit_price?: number
  exit_date?: string
}

export interface SignalStrategy {
  name: string
  category: string
  display_name: string
}

// ───────────────────────────────────────────────
// 交易信号类型（多因子合成）
// ───────────────────────────────────────────────

export interface FactorScore {
  name: string
  name_label?: string
  score: number
  weight: number
  description: string
  details?: Record<string, any>
}

export interface TradingSignal {
  type: 'BUY' | 'SELL' | 'HOLD'
  type_label?: string
  confidence: number
  entry_price: number
  stop_loss: number
  take_profit: number
  tp1: number
  tp2: number
  tp3: number
  position_pct: number
  risk_reward_ratio: number
  rationale: string
  factors: FactorScore[]
  timestamp: string
  symbol: string
  period: string
  trailing_stop?: number
}

export interface ResonanceData {
  daily_trend: 'bull' | 'bear' | 'neutral'
  weekly_trend: 'bull' | 'bear' | 'neutral'
  monthly_trend: 'bull' | 'bear' | 'neutral'
  resonance: boolean
  confidence: number
  direction: 'bull' | 'bear' | 'neutral'
  description: string
  symbol: string
}

// ───────────────────────────────────────────────
// AI 投研类型
// ───────────────────────────────────────────────

export interface AIChatRequest {
  message: string
  context_type?: 'stock' | 'watchlist' | 'signals' | 'backtest' | 'general'
  symbol?: string
  history?: Array<{ role: string; content: string }>
  stream?: boolean
}

export interface AIChatResponse {
  reply: string
  context_injected?: Record<string, any>
  tokens_used?: number
  model?: string
  latency_ms: number
}

export interface AITemplate {
  id: string
  name: string
  description: string
  prompt: string
  category: string
  icon: string
}

export interface AIStatus {
  enabled: boolean
  api_key_configured: boolean
  model?: string
  message: string
  available_models: string[]
}

export interface AIContext {
  type: string
  symbol?: string
  timestamp: string
  data: Record<string, any>
  latency_ms?: number
}

