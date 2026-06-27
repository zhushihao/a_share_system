import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  fetchAIStatus,
  sendAIChat,
  fetchAITemplates,
  fetchAIContext,
} from '@/api/client'
import type { AIStatus, AITemplate, AIChatResponse } from '@/types'
import {
  Send,
  Bot,
  User,
  AlertCircle,
  Settings,
  TrendingUp,
  Activity,
  ArrowRightCircle,
  Sunrise,
  BarChart2,
  AlertTriangle,
  Waves,
  Stethoscope,
  Shield,
  MessageCircle,
  Loader2,
  Sparkles,
  ChevronDown,
  ChevronUp,
  BookOpen,
} from 'lucide-react'

const ICON_MAP: Record<string, React.ReactNode> = {
  'trending-up': <TrendingUp size={18} />,
  activity: <Activity size={18} />,
  'arrow-right-circle': <ArrowRightCircle size={18} />,
  sunrise: <Sunrise size={18} />,
  'bar-chart-2': <BarChart2 size={18} />,
  'alert-triangle': <AlertTriangle size={18} />,
  waves: <Waves size={18} />,
  stethoscope: <Stethoscope size={18} />,
  shield: <Shield size={18} />,
  'message-circle': <MessageCircle size={18} />,
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  latencyMs?: number
}

export default function AIResearch() {
  const [searchParams] = useSearchParams()
  const defaultSymbol = searchParams.get('symbol') || ''

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'system',
      content: '欢迎使用 AI 投研助手！我可以帮您分析个股技术形态、评估交易策略、解读市场信号。请从下方选择快捷模板或直接输入问题。',
      timestamp: new Date().toISOString(),
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [aiStatus, setAiStatus] = useState<AIStatus | null>(null)
  const [templates, setTemplates] = useState<AITemplate[]>([])
  const [showTemplates, setShowTemplates] = useState(true)
  const [selectedSymbol, setSelectedSymbol] = useState(defaultSymbol)
  const [contextType, setContextType] = useState('stock')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // 初始化：获取状态 + 模板
  useEffect(() => {
    fetchAIStatus().then(setAiStatus).catch(console.error)
    fetchAITemplates().then(setTemplates).catch(console.error)
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const generateId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res: AIChatResponse = await sendAIChat({
        message: text,
        symbol: selectedSymbol || undefined,
        context_type: contextType as any,
        history: messages
          .filter((m) => m.role === 'user' || m.role === 'assistant')
          .map((m) => ({ role: m.role, content: m.content })),
      })

      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: res.reply,
        timestamp: new Date().toISOString(),
        latencyMs: res.latency_ms,
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: `❌ 请求失败：${err.message || '网络异常'}`,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setLoading(false)
    }
  }, [input, loading, selectedSymbol, contextType, messages])

  const handleTemplateClick = useCallback(
    async (template: AITemplate) => {
      const prompt = template.prompt.replace(/{symbol}/g, selectedSymbol || '某股票')
      const userMsg: ChatMessage = {
        id: generateId(),
        role: 'user',
        content: `【${template.name}】${prompt}`,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])
      setLoading(true)

      try {
        // 先获取上下文注入数据
        let contextData = null
        if (selectedSymbol) {
          try {
            contextData = await fetchAIContext(selectedSymbol, contextType)
          } catch {
            // 忽略上下文获取失败
          }
        }

        const res: AIChatResponse = await sendAIChat({
          message: prompt,
          symbol: selectedSymbol || undefined,
          context_type: contextType as any,
        })

        const assistantMsg: ChatMessage = {
          id: generateId(),
          role: 'assistant',
          content: res.reply,
          timestamp: new Date().toISOString(),
          latencyMs: res.latency_ms,
          ...(contextData ? { contextData } : {}),
        }
        setMessages((prev) => [...prev, assistantMsg])
      } catch (err: any) {
        const errorMsg: ChatMessage = {
          id: generateId(),
          role: 'assistant',
          content: `❌ 请求失败：${err.message || '网络异常'}`,
          timestamp: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, errorMsg])
      } finally {
        setLoading(false)
      }
    },
    [selectedSymbol, contextType]
  )

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const categories = Array.from(new Set(templates.map((t) => t.category)))

  return (
    <div className="flex h-full gap-4">
      {/* 左侧：聊天区域 */}
      <div className="flex-1 flex flex-col min-w-0 bg-white rounded-lg border border-slate-200 shadow-sm">
        {/* 顶部：状态栏 + 上下文选择 */}
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-sky-500" />
            <span className="font-semibold text-slate-800">AI 投研助手</span>
            {aiStatus && (
              <span
                className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
                  aiStatus.enabled
                    ? 'bg-emerald-50 text-emerald-600'
                    : 'bg-amber-50 text-amber-600'
                }`}
              >
                {aiStatus.enabled ? (
                  <>
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    已启用
                  </>
                ) : (
                  <>
                    <AlertCircle size={10} />
                    未配置
                  </>
                )}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="股票代码 (如 600519)"
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value)}
              className="text-xs px-2 py-1 border border-slate-200 rounded w-28 focus:outline-none focus:ring-1 focus:ring-sky-400"
            />
            <select
              value={contextType}
              onChange={(e) => setContextType(e.target.value)}
              className="text-xs px-2 py-1 border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-sky-400"
            >
              <option value="stock">个股</option>
              <option value="watchlist">自选股</option>
              <option value="signals">信号</option>
              <option value="general">通用</option>
            </select>
          </div>
        </div>

        {/* 未配置提示 */}
        {aiStatus && !aiStatus.enabled && (
          <div className="mx-4 mt-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-start gap-3">
            <AlertCircle size={18} className="text-amber-500 mt-0.5 shrink-0" />
            <div className="text-sm text-amber-800">
              <p className="font-medium">AI 投研尚未配置</p>
              <p className="mt-1">
                请在「系统设置」中配置 Kimi API Key，或设置环境变量 KIMI_API_KEY。配置后即可使用 AI
                深度分析功能。
              </p>
              <a
                href="https://platform.moonshot.cn/"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 mt-2 text-sky-600 hover:text-sky-700 text-xs font-medium"
              >
                <BookOpen size={12} />
                前往 Moonshot 获取 API Key
              </a>
            </div>
          </div>
        )}

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role !== 'user' && (
                <div className="w-8 h-8 rounded-full bg-sky-50 flex items-center justify-center shrink-0 mt-1">
                  {msg.role === 'system' ? (
                    <Sparkles size={16} className="text-sky-500" />
                  ) : (
                    <Bot size={16} className="text-sky-500" />
                  )}
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-lg px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-sky-500 text-white'
                    : msg.role === 'system'
                    ? 'bg-slate-100 text-slate-600 italic'
                    : 'bg-slate-50 text-slate-800 border border-slate-200'
                }`}
              >
                {msg.content}
                {msg.latencyMs && msg.role === 'assistant' && (
                  <div className="text-xs text-slate-400 mt-1 text-right">
                    {msg.latencyMs}ms
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-sky-500 flex items-center justify-center shrink-0 mt-1">
                  <User size={16} className="text-white" />
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex gap-3 justify-start">
              <div className="w-8 h-8 rounded-full bg-sky-50 flex items-center justify-center shrink-0">
                <Bot size={16} className="text-sky-500" />
              </div>
              <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 flex items-center gap-2">
                <Loader2 size={16} className="animate-spin text-sky-500" />
                <span className="text-sm text-slate-500">AI 思考中...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="px-4 py-3 border-t border-slate-100">
          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入您的问题，按 Enter 发送..."
              rows={1}
              className="flex-1 resize-none border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-sky-400 focus:border-sky-400 min-h-[40px] max-h-[120px]"
              disabled={loading}
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center gap-1"
            >
              <Send size={16} />
            </button>
          </div>
          <div className="text-xs text-slate-400 mt-1.5">
            提示：Shift + Enter 换行，Enter 直接发送。快捷提问模板在右侧面板。
          </div>
        </div>
      </div>

      {/* 右侧：快捷模板 + 帮助 */}
      <div className="w-72 shrink-0 flex flex-col gap-4">
        {/* 快捷提问模板 */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <button
            onClick={() => setShowTemplates((s) => !s)}
            className="w-full px-4 py-3 flex items-center justify-between bg-slate-50 hover:bg-slate-100 transition"
          >
            <div className="flex items-center gap-2 font-semibold text-slate-700 text-sm">
              <Sparkles size={16} className="text-sky-500" />
              快捷提问模板
            </div>
            {showTemplates ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {showTemplates && (
            <div className="p-3 space-y-3 max-h-[400px] overflow-y-auto">
              {categories.map((cat) => (
                <div key={cat}>
                  <div className="text-xs font-medium text-slate-400 mb-1.5 px-1">
                    {cat}
                  </div>
                  <div className="space-y-1">
                    {templates
                      .filter((t) => t.category === cat)
                      .map((t) => (
                        <button
                          key={t.id}
                          onClick={() => handleTemplateClick(t)}
                          disabled={loading}
                          className="w-full text-left px-3 py-2 rounded-md text-sm text-slate-700 hover:bg-sky-50 hover:text-sky-700 transition flex items-center gap-2 disabled:opacity-50"
                          title={t.description}
                        >
                          <span className="text-sky-500 shrink-0">
                            {ICON_MAP[t.icon] || <MessageCircle size={18} />}
                          </span>
                          <span className="truncate">{t.name}</span>
                        </button>
                      ))}
                  </div>
                </div>
              ))}
              {templates.length === 0 && (
                <div className="text-sm text-slate-400 text-center py-4">加载中...</div>
              )}
            </div>
          )}
        </div>

        {/* 使用说明 */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4">
          <div className="flex items-center gap-2 font-semibold text-slate-700 text-sm mb-3">
            <BookOpen size={16} className="text-sky-500" />
            使用说明
          </div>
          <div className="text-xs text-slate-500 space-y-2">
            <p>1. 在顶部输入股票代码，AI 将自动注入该股的行情和指标数据。</p>
            <p>2. 选择「上下文类型」可切换分析维度（个股/自选股/信号）。</p>
            <p>3. 点击右侧「快捷模板」可快速发起专业分析请求。</p>
            <p>4. 配置 Kimi API Key 后，AI 将基于真实数据给出深度分析。</p>
          </div>
        </div>

        {/* 配置入口 */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4">
          <div className="flex items-center gap-2 font-semibold text-slate-700 text-sm mb-3">
            <Settings size={16} className="text-sky-500" />
            配置状态
          </div>
          {aiStatus ? (
            <div className="text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-slate-500">API Key:</span>
                <span className={aiStatus.api_key_configured ? 'text-emerald-600' : 'text-amber-600'}>
                  {aiStatus.api_key_configured ? '已配置' : '未配置'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">模型:</span>
                <span className="text-slate-700">{aiStatus.model || '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">可用模型:</span>
                <span className="text-slate-700">
                  {aiStatus.available_models.length > 0
                    ? aiStatus.available_models.join(', ')
                    : '-'}
                </span>
              </div>
            </div>
          ) : (
            <div className="text-xs text-slate-400">加载中...</div>
          )}
          <a
            href="#/settings"
            className="mt-3 inline-flex items-center gap-1 text-xs text-sky-600 hover:text-sky-700 font-medium"
          >
            <Settings size={12} />
            前往系统设置
          </a>
        </div>
      </div>
    </div>
  )
}
