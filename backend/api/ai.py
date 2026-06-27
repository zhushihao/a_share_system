# -*- coding: utf-8 -*-
"""
AI 投研接口 — 预留模块

由于用户无 Kimi API，本模块仅提供：
1. API Key 配置状态检测
2. 快捷提问模板
3. 上下文注入（自动从本地数据获取行情/指标）
4. 聊天接口（已配置 Key 时透传，未配置时提示）
"""

import os
import sys
import time
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

# 兼容跨目录启动
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
for _path in (PARENT_ROOT, PROJECT_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from config import settings
except ImportError:
    from backend.config import settings

try:
    from models.schemas import AIChatRequest, AIChatResponse, AITemplate, AIStatus
except ImportError:
    from backend.models.schemas import AIChatRequest, AIChatResponse, AITemplate, AIStatus

try:
    from services.data_provider import get_data_provider_service
    from services.indicators import calculate_all_indicators, get_latest_indicators, calc_tech_score
except ImportError:
    from backend.services.data_provider import get_data_provider_service
    from backend.services.indicators import calculate_all_indicators, get_latest_indicators, calc_tech_score

router = APIRouter()


# ───────────────────────────────────────────────
# 快捷提问模板（预定义）
# ───────────────────────────────────────────────

_DEFAULT_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "caisen-w-bottom",
        "name": "蔡森 W 底形态分析",
        "description": "分析当前股票是否符合 W 底形态特征",
        "prompt": "请分析 {symbol} 最近的走势，判断是否出现蔡森 W 底形态特征。关注：1）两个低点的形成；2）颈线位置；3）成交量配合；4）等幅测量目标。给出详细的形态分析和技术判断。",
        "category": "蔡森",
        "icon": "trending-up",
    },
    {
        "id": "caisen-head-shoulders",
        "name": "头肩底形态分析",
        "description": "分析当前股票是否符合头肩底形态特征",
        "prompt": "请分析 {symbol} 最近的走势，判断是否出现头肩底形态特征。关注：1）左肩、头部、右肩的形成；2）颈线突破；3）成交量配合；4）等幅测量目标。",
        "category": "蔡森",
        "icon": "activity",
    },
    {
        "id": "baida-right-side",
        "name": "白大右侧交易分析",
        "description": "基于均线多头排列和 MACD 金叉判断右侧交易机会",
        "prompt": "请分析 {symbol} 的右侧交易机会。要求：1）检查均线是否多头排列（MA5>MA10>MA20）；2）MACD 是否金叉；3）KD 是否处于合理区间；4）判断当前是回调还是反弹。给出明确的交易建议。",
        "category": "白大",
        "icon": "arrow-right-circle",
    },
    {
        "id": "baida-open-eight",
        "name": "开盘八法分析",
        "description": "基于开盘前5分钟K线判断当日走势",
        "prompt": "请分析 {symbol} 今日开盘前5分钟的K线特征，根据白大开盘八法判断：1）阴阳比例；2）量能对比；3）当日可能走势方向；4）适合的应对策略。",
        "category": "开盘八法",
        "icon": "sunrise",
    },
    {
        "id": "volume-price-breakout",
        "name": "量价突破分析",
        "description": "分析放量突破的关键信号",
        "prompt": "请分析 {symbol} 最近的量价关系。关注：1）是否出现放量突破20日新高；2）成交量是否显著放大（>2倍均量）；3）价格突破的有效性；4）后续目标位和止损位建议。",
        "category": "量价",
        "icon": "bar-chart-2",
    },
    {
        "id": "volume-price-collapse",
        "name": "量价崩溃预警",
        "description": "识别放量跌破支撑的风险信号",
        "prompt": "请分析 {symbol} 最近的量价关系，识别是否存在量价崩溃风险。关注：1）是否放量跌破20日新低；2）关键支撑位是否被击穿；3）MACD 和 KD 是否同步走弱；4）建议的止损策略。",
        "category": "量价",
        "icon": "alert-triangle",
    },
    {
        "id": "wave-elliott",
        "name": "波浪结构分析",
        "description": "基于艾略特波浪理论分析走势结构",
        "prompt": "请尝试分析 {symbol} 当前处于艾略特波浪理论的哪个浪型。关注：1）推动浪还是调整浪；2）当前浪的位置（1-5或ABC）；3）斐波那契回调比例；4）下一浪的可能目标。注意：波浪理论为主观分析，需结合其他指标验证。",
        "category": "波浪",
        "icon": "waves",
    },
    {
        "id": "tech-summary",
        "name": "技术面综合诊断",
        "description": "汇总所有技术指标给出综合判断",
        "prompt": "请对 {symbol} 进行技术面综合诊断。要求：1）汇总 MA/KD/MACD/RSI/BOLL 所有指标状态；2）给出技术评分（0-100）；3）判断当前趋势（多/空/震荡）；4）给出短期和中期目标位；5）明确止损位。",
        "category": "通用",
        "icon": "stethoscope",
    },
    {
        "id": "risk-assessment",
        "name": "风险收益评估",
        "description": "基于当前价格和指标评估风险收益比",
        "prompt": "请评估 {symbol} 当前的风险收益比。要求：1）当前技术形态的风险等级；2）关键支撑和阻力位；3）建议仓位比例；4）盈亏比估算；5）是否适合当前入场。",
        "category": "通用",
        "icon": "shield",
    },
]


# ───────────────────────────────────────────────
# 辅助函数
# ───────────────────────────────────────────────

def _get_ai_status() -> Dict[str, Any]:
    """获取 AI 服务状态"""
    key = settings.AI_API_KEY.strip() if settings.AI_API_KEY else ""
    configured = bool(key) and len(key) > 10
    return {
        "enabled": configured,
        "api_key_configured": configured,
        "model": settings.AI_MODEL if configured else None,
        "message": (
            "AI 投研已就绪，可以使用完整对话功能。"
            if configured
            else "AI 投研未配置：请在系统设置中配置 Kimi API Key，或设置环境变量 KIMI_API_KEY。"
        ),
        "available_models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"] if configured else [],
    }


def _build_context(symbol: Optional[str], context_type: str) -> Dict[str, Any]:
    """根据股票代码和上下文类型构建数据摘要"""
    ctx = {
        "type": context_type,
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "data": {},
    }
    
    if not symbol:
        return ctx
    
    dp = get_data_provider_service(tdxdir=settings.TDX_DIR)
    
    # 1. 获取最新 K 线
    df = dp.get_kline_latest(symbol, n=60, period="daily", adjust="qfq")
    if df is not None and len(df) > 0:
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        price_data = {
            "latest_date": str(latest.get("date", "")),
            "open": round(float(latest.get("open", 0)), 2),
            "high": round(float(latest.get("high", 0)), 2),
            "low": round(float(latest.get("low", 0)), 2),
            "close": round(float(latest.get("close", 0)), 2),
            "volume": int(latest.get("volume", 0)),
            "change_pct": round((latest.get("close", 0) - prev.get("close", 0)) / prev.get("close", 0) * 100, 2) if prev.get("close", 0) > 0 else 0,
        }
        ctx["data"]["price"] = price_data
        
        # 2. 计算技术指标
        try:
            df_ind = calculate_all_indicators(df)
            latest_ind = get_latest_indicators(df_ind)
            score = calc_tech_score(df_ind)
            
            ctx["data"]["indicators"] = {
                k: round(v, 2) if isinstance(v, (int, float)) else v
                for k, v in latest_ind.items()
                if v is not None and not (isinstance(v, float) and (v != v))  # 过滤 NaN
            }
            ctx["data"]["tech_score"] = score
            ctx["data"]["trend"] = (
                " bullish" if score >= 70 else " bearish" if score <= 30 else " neutral"
            )
        except Exception as e:
            ctx["data"]["indicators_error"] = str(e)
        
        # 3. 近期走势摘要
        ctx["data"]["recent_trend"] = {
            "5d_change": round((latest.get("close", 0) - df.iloc[-5].get("close", 0)) / df.iloc[-5].get("close", 0) * 100, 2) if len(df) >= 5 else None,
            "20d_change": round((latest.get("close", 0) - df.iloc[-20].get("close", 0)) / df.iloc[-20].get("close", 0) * 100, 2) if len(df) >= 20 else None,
            "60d_high": round(df["high"].tail(60).max(), 2) if len(df) >= 60 else None,
            "60d_low": round(df["low"].tail(60).min(), 2) if len(df) >= 60 else None,
        }
    
    return ctx


def _mock_ai_reply(request: AIChatRequest) -> str:
    """未配置 API Key 时的模拟回复（友好提示）"""
    if not request.message or not request.message.strip():
        return "请输入您的问题。"
    
    msg = request.message.strip()
    
    # 如果用户直接问技术问题，给出基于本地数据的简要分析框架
    if request.symbol and request.context_type == "stock":
        return (
            f"【AI 投研预留模式】\n\n"
            f"您询问的是：{msg}\n"
            f"目标股票：{request.symbol}\n\n"
            f"⚠️ 当前未配置 Kimi API Key，无法调用 AI 进行深度分析。\n\n"
            f"请按以下步骤配置：\n"
            f"1. 登录 https://platform.moonshot.cn/ 获取 API Key\n"
            f"2. 在「系统设置」中填入 API Key，或设置环境变量 KIMI_API_KEY\n"
            f"3. 刷新页面后即可使用 AI 对话功能\n\n"
            f"💡 提示：配置前可使用「快捷提问模板」查看预设问题，"
            f"配置后 AI 将自动注入 {request.symbol} 的实时数据进行分析。"
        )
    
    return (
        f"【AI 投研预留模式】\n\n"
        f"您的问题：{msg}\n\n"
        f"⚠️ 当前未配置 Kimi API Key，无法调用 AI 进行深度分析。\n\n"
        f"请按以下步骤配置：\n"
        f"1. 登录 https://platform.moonshot.cn/ 获取 API Key\n"
        f"2. 在「系统设置」中填入 API Key，或设置环境变量 KIMI_API_KEY\n"
        f"3. 刷新页面后即可使用 AI 对话功能\n\n"
        f"💡 当前支持的功能：\n"
        f"• 快捷提问模板（9 种策略分析模板）\n"
        f"• 上下文注入（自动获取股票行情/指标）\n"
        f"• 本地数据驱动的策略分析（配置 Key 后启用 AI 深度分析）"
    )


# ───────────────────────────────────────────────
# API 路由
# ───────────────────────────────────────────────

@router.get("/ai/status", response_model=AIStatus)
async def ai_status():
    """获取 AI 服务状态（是否已配置 API Key）"""
    return AIStatus(**_get_ai_status())


@router.post("/ai/chat", response_model=AIChatResponse)
async def ai_chat(request: AIChatRequest):
    """
    AI 对话接口
    
    - 已配置 API Key：透传至 Kimi API（当前为预留，返回模拟回复）
    - 未配置 API Key：返回友好提示，引导用户配置
    """
    start = time.time()
    status = _get_ai_status()
    
    if not status["enabled"]:
        reply = _mock_ai_reply(request)
        latency = int((time.time() - start) * 1000)
        return AIChatResponse(
            reply=reply,
            context_injected=None,
            tokens_used=0,
            model=None,
            latency_ms=latency,
        )
    
    # 已配置 Key：这里可以接入真实 AI API（预留）
    # TODO: 接入 Kimi API 进行真实对话
    latency = int((time.time() - start) * 1000)
    return AIChatResponse(
        reply="【AI 已配置】对话功能即将启用（API 接入预留中）。",
        context_injected=None,
        tokens_used=0,
        model=settings.AI_MODEL,
        latency_ms=latency,
    )


@router.get("/ai/templates", response_model=List[AITemplate])
async def ai_templates(category: Optional[str] = None):
    """
    获取快捷提问模板列表
    
    Args:
        category: 筛选类别（蔡森/白大/量价/波浪/开盘八法/通用）
    """
    templates = [AITemplate(**t) for t in _DEFAULT_TEMPLATES]
    if category:
        templates = [t for t in templates if t.category == category]
    return templates


@router.post("/ai/context")
async def ai_context(
    symbol: Optional[str] = None,
    context_type: str = "stock",
) -> Dict[str, Any]:
    """
    上下文注入接口
    
    根据股票代码和上下文类型，自动从本地数据获取行情/指标，
    生成 AI 对话所需的上下文摘要。
    """
    start = time.time()
    context = _build_context(symbol, context_type)
    context["latency_ms"] = int((time.time() - start) * 1000)
    return context
