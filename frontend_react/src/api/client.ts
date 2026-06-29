import axios from 'axios'

const API_BASE = '/api/v1'

export const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

export async function fetchHealth() {
  const { data } = await axios.get('/api/health')
  return data
}

export async function fetchQuote(symbol: string) {
  const { data } = await apiClient.get(`/quote/${symbol}`)
  return data
}

export async function fetchQuotesBatch(symbols: string[]) {
  const { data } = await apiClient.get(`/quotes/batch?symbols=${symbols.join(',')}`)
  return data
}

export async function fetchOHLCV(symbol: string, params?: { limit?: number; adjust?: string; period?: string }) {
  const { data } = await apiClient.get(`/quote/${symbol}/ohlcv`, { params })
  return data
}

export async function fetchIndicators(symbol: string, params?: { limit?: number; adjust?: string; period?: string }) {
  const { data } = await apiClient.get(`/quote/${symbol}/indicators`, { params })
  return data
}

export async function fetchScore(symbol: string) {
  const { data } = await apiClient.get(`/quote/${symbol}/score`)
  return data
}

export async function fetchPatterns(symbol: string, params?: { limit?: number; adjust?: string; period?: string }) {
  const { data } = await apiClient.get(`/quote/${symbol}/patterns`, { params })
  return data
}

export async function fetchVolumeAnalysis(symbol: string, params?: { limit?: number; adjust?: string; period?: string }) {
  const { data } = await apiClient.get(`/quote/${symbol}/volume-analysis`, { params })
  return data
}

export async function fetchSupportResistance(symbol: string, params?: { limit?: number; adjust?: string; period?: string }) {
  const { data } = await apiClient.get(`/quote/${symbol}/support-resistance`, { params })
  return data
}

export async function fetchFibonacci(symbol: string, params?: { limit?: number; adjust?: string; period?: string }) {
  const { data } = await apiClient.get(`/quote/${symbol}/fibonacci`, { params })
  return data
}

export async function searchStocks(q: string) {
  const { data } = await apiClient.get('/stock/search', { params: { q, limit: 10 } })
  return data
}

export async function fetchWatchlist(group?: string) {
  const { data } = await apiClient.get('/watchlist/with-quotes', { params: { group } })
  return data
}

export async function fetchWatchlistRaw(group?: string) {
  const { data } = await apiClient.get('/watchlist', { params: { group } })
  return data
}

export async function addWatchlist(item: { symbol: string; name: string; group?: string; notes?: string; tags?: string[] }) {
  const { data } = await apiClient.post('/watchlist', item)
  return data
}

export async function addWatchlistBatch(items: { symbol: string; name: string; group?: string; notes?: string; tags?: string[] }[]) {
  const { data } = await apiClient.post('/watchlist/batch', { items })
  return data
}

export async function deleteWatchlist(symbol: string) {
  const { data } = await apiClient.delete(`/watchlist/${symbol}`)
  return data
}

export async function updateWatchlistGroup(symbol: string, group: string) {
  const { data } = await apiClient.put(`/watchlist/${symbol}/group`, { group })
  return data
}

export async function updateWatchlistGroupBatch(symbols: string[], group: string) {
  const { data } = await apiClient.put('/watchlist/batch/group', { symbols, group })
  return data
}

export async function fetchWatchlistGroups() {
  const { data } = await apiClient.get('/watchlist/groups')
  return data
}

export async function fetchWatchlistWithQuotes() {
  const { data } = await apiClient.get('/watchlist/with-quotes')
  return data
}

export async function fetchSignals(params?: { symbol?: string; strategy?: string; limit?: number; offset?: number }) {
  const { data } = await apiClient.get('/signals', { params })
  return data
}

export async function scanSignals(body: { symbols: string[]; strategies?: string[] }) {
  const { data } = await apiClient.post('/signals/scan', body)
  return data
}

export async function scanWatchlistSignals(strategies?: string[]) {
  const { data } = await apiClient.get('/signals/watchlist-scan', { params: { strategies } })
  return data
}

export async function fetchSignalStrategies() {
  const { data } = await apiClient.get('/signals/strategies')
  return data
}

export async function fetchSignalStats(days?: number) {
  const { data } = await apiClient.get('/signals/stats', { params: { days } })
  return data
}

export async function acknowledgeSignal(signalId: string) {
  const { data } = await apiClient.post(`/signals/${signalId}/acknowledge`)
  return data
}

export async function deleteSignal(signalId: string) {
  const { data } = await apiClient.delete(`/signals/${signalId}`)
  return data
}

// ───────────────────────────────────────────────
// Backtest API
// ───────────────────────────────────────────────

export async function fetchBacktestStrategies() {
  const { data } = await apiClient.get('/backtest/strategies')
  return data
}

export async function fetchBacktestCustomTemplate() {
  const { data } = await apiClient.get('/backtest/custom-template')
  return data
}

export async function runBacktest(body: {
  symbol: string
  strategy_name: string
  start_date: string
  end_date: string
  initial_cash?: number
  commission_rate?: number
  slippage?: number
  params?: Record<string, any>
  custom_code?: string
}) {
  const { data } = await apiClient.post('/backtest/run', body)
  return data
}

export async function fetchBacktestResults(strategyName?: string, limit?: number) {
  const { data } = await apiClient.get('/backtest/results', { params: { strategy_name: strategyName, limit } })
  return data
}

export async function fetchBacktestDetail(resultId: string) {
  const { data } = await apiClient.get(`/backtest/results/${resultId}`)
  return data
}

export async function deleteBacktestResult(resultId: string) {
  const { data } = await apiClient.delete(`/backtest/results/${resultId}`)
  return data
}

// ───────────────────────────────────────────────
// Data Management API
// ───────────────────────────────────────────────

export async function fetchDataOverview() {
  const { data } = await apiClient.get('/data/overview')
  return data
}

export async function fetchStockList(market?: string, limit?: number) {
  const { data } = await apiClient.get('/data/stock-list', { params: { market, limit } })
  // 统一返回结构：后端使用 stocks，前端统一为 items
  return {
    ...data,
    items: data.items || data.stocks || [],
  }
}

export async function diagnoseData(symbol: string, period?: string) {
  const { data } = await apiClient.get('/data/diagnose', { params: { symbol, period } })
  return data
}

export async function exportData(params: {
  symbol: string
  start_date?: string
  end_date?: string
  period?: string
  adjust?: string
  format?: string
}) {
  const { data } = await apiClient.get('/data/export', { params })
  return data
}

export async function fetchDataHealth() {
  const { data } = await apiClient.get('/data/health')
  return data
}

// ───────────────────────────────────────────────
// Settings API
// ───────────────────────────────────────────────

export async function fetchSettings() {
  const { data } = await apiClient.get('/settings')
  return data
}

export async function fetchSetting(key: string) {
  const { data } = await apiClient.get(`/settings/${key}`)
  return data
}

export async function updateSetting(key: string, value: any) {
  const { data } = await apiClient.put(`/settings/${key}`, { value })
  return data
}

export async function updateSettingsBatch(settings: Record<string, any>) {
  const { data } = await apiClient.post('/settings/batch', { settings })
  return data
}

export async function deleteSetting(key: string) {
  const { data } = await apiClient.delete(`/settings/${key}`)
  return data
}

export async function resetSettings() {
  const { data } = await apiClient.post('/settings/reset')
  return data
}

// ───────────────────────────────────────────────
// AI Research API
// ───────────────────────────────────────────────

export async function fetchAIStatus() {
  const { data } = await apiClient.get('/ai/status')
  return data
}

export async function sendAIChat(request: {
  message: string
  context_type?: string
  symbol?: string
  history?: Array<{ role: string; content: string }>
  stream?: boolean
}) {
  const { data } = await apiClient.post('/ai/chat', request)
  return data
}

export async function fetchAITemplates(category?: string) {
  const { data } = await apiClient.get('/ai/templates', { params: { category } })
  return data
}

export async function fetchSignal(symbol: string, params?: { period?: string; adjust?: string }) {
  const { data } = await apiClient.get(`/quote/${symbol}/signal`, { params })
  return data
}

export async function fetchResonance(symbol: string) {
  const { data } = await apiClient.get(`/quote/${symbol}/resonance`)
  return data
}

export async function trackSignalPerformance(signalId: string, currentPrice: number) {
  const { data } = await apiClient.post(`/signals/${signalId}/track`, null, { params: { current_price: currentPrice } })
  return data
}

export async function fetchSignalPerformance(strategy?: string, days?: number) {
  const { data } = await apiClient.get('/signals/performance', { params: { strategy, days } })
  return data
}

export async function closeSignal(signalId: string, status: string, exitPrice: number) {
  const { data } = await apiClient.post(`/signals/${signalId}/close`, null, { params: { status, exit_price: exitPrice } })
  return data
}

export async function scanResonance(symbols: string[], minConfidence?: number, requireResonance?: boolean) {
  const { data } = await apiClient.post('/quote/scan/resonance', symbols, { params: { min_confidence: minConfidence, require_resonance: requireResonance } })
  return data
}

export async function expireOldSignals(days?: number) {
  const { data } = await apiClient.post('/signals/expire-old', null, { params: { days } })
  return data
}

export async function fetchMarketOverview() {
  const { data } = await apiClient.get('/market/overview')
  return data
}

export async function fetchIndexKline(indexCode: string, params?: { period?: string, limit?: number }) {
  const { data } = await apiClient.get(`/market/index/${indexCode}`, { params })
  return data
}

export async function fetchAIContext(symbol?: string, context_type?: string) {
  const { data } = await apiClient.post('/ai/context', null, { params: { symbol, context_type } })
  return data
}

export async function fetchMarketSentiment() {
  const { data } = await apiClient.get('/market/sentiment')
  return data
}

export async function fetchMarketHotspots(limit?: number) {
  const { data } = await apiClient.get('/market/hotspots', { params: { limit } })
  return data
}

export async function fetchMarketLimitUp(limit?: number) {
  const { data } = await apiClient.get('/market/limit-up', { params: { limit } })
  return data
}

// ───────────────────────────────────────────────
// 新增：个股详情 / 五档 / 分时 / F10
// ───────────────────────────────────────────────

export async function fetchIntraday(symbol: string, date?: string) {
  const { data } = await apiClient.get(`/quote/${symbol}/intraday`, { params: { date } })
  return data
}

export async function fetchProfile(symbol: string) {
  const { data } = await apiClient.get(`/quote/${symbol}/profile`)
  return data
}

export async function fetchF10(symbol: string) {
  const { data } = await apiClient.get(`/f10/${symbol}`)
  return data
}

export async function fetchOrderbook(symbol: string) {
  const { data } = await apiClient.get(`/quote/${symbol}/orderbook`)
  return data
}

export async function fetchMarketSectors(type_filter?: 'industry' | 'concept') {
  const { data } = await apiClient.get('/market/sectors', { params: { type_filter } })
  return data
}

export async function fetchDataCompare(symbol: string, period?: string, adjust?: string) {
  const { data } = await apiClient.get('/data/compare', { params: { symbol, period, adjust } })
  return data
}
