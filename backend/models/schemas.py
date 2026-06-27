# -*- coding: utf-8 -*-
"""Pydantic Schema - 数据模型"""

from datetime import datetime, date, time
from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field


class StandardQuote(BaseModel):
    """基础行情"""
    symbol: str
    name: Optional[str] = None
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: Optional[float] = None
    source: Literal["mootdx", "yahoo", "ifind", "hybrid"] = "mootdx"
    adj_factor: Optional[float] = None
    freq: Literal["1d", "1m", "5m", "15m", "30m", "60m", "tick"] = "1d"


class MarketIndex(BaseModel):
    """大盘指数"""
    symbol: str
    name: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    change_pct: float
    change_amount: float
    volume: int
    amount: float


class HotspotBlock(BaseModel):
    """热点板块"""
    block_code: str
    block_name: str
    change_pct: float
    leading_stock: str
    leading_stock_name: str
    volume_ratio: float
    money_flow: float
    rank: int
    stock_count: int
    up_count: int
    limit_up_count: int


class WatchlistItem(BaseModel):
    """自选股"""
    id: str
    symbol: str
    name: str
    group: str = "默认"
    added_at: datetime
    notes: Optional[str] = None
    tags: List[str] = []
    alert_price_high: Optional[float] = None
    alert_price_low: Optional[float] = None


class WatchlistQuote(BaseModel):
    """自选股行情（含指标）"""
    symbol: str
    name: str
    price: float
    pre_close: float
    change_pct: float
    change_amount: float
    open: float
    high: float
    low: float
    volume: int
    amount: float
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    kd_k: Optional[float] = None
    kd_d: Optional[float] = None
    macd_dif: Optional[float] = None
    macd_dea: Optional[float] = None
    macd_bar: Optional[float] = None
    rsi6: Optional[float] = None
    tech_score: int = 0


class Signal(BaseModel):
    """交易信号"""
    id: str
    symbol: str
    name: str
    timestamp: datetime
    signal_type: str
    strategy: str
    description: str
    confidence: int
    price: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    triggered: bool = True
    acknowledged: bool = False


class BacktestConfig(BaseModel):
    """回测配置"""
    strategy_name: str
    symbols: List[str]
    start_date: date
    end_date: date
    initial_cash: float = 100000.0
    commission_rate: float = 0.0003
    slippage: float = 0.001


class BacktestResult(BaseModel):
    """回测结果"""
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    equity_curve: List[Dict]


class APIResponse(BaseModel):
    """通用响应"""
    data: Optional[Dict] = None
    source: str = "mootdx"
    timestamp: datetime
    latency_ms: int
    fallback: bool = False
    fallback_reason: Optional[str] = None


class AIChatRequest(BaseModel):
    """AI 对话请求"""
    message: str = Field(..., description="用户输入消息")
    context_type: Optional[Literal["stock", "watchlist", "signals", "backtest", "general"]] = "general"
    symbol: Optional[str] = None
    history: List[Dict] = []
    stream: bool = False


class AIChatResponse(BaseModel):
    """AI 对话响应"""
    reply: str
    context_injected: Optional[Dict] = None
    tokens_used: Optional[int] = None
    model: Optional[str] = None
    latency_ms: int = 0


class AITemplate(BaseModel):
    """AI 快捷提问模板"""
    id: str
    name: str
    description: str
    prompt: str
    category: Literal["蔡森", "白大", "量价", "波浪", "开盘八法", "通用"]
    icon: str = "message-circle"


class AIStatus(BaseModel):
    """AI 服务状态"""
    enabled: bool
    api_key_configured: bool
    model: Optional[str] = None
    message: str
    available_models: List[str] = []
