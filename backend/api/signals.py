# -*- coding: utf-8 -*-
"""
Signals API - 信号中心接口

功能：
1. 信号列表查询（分页、筛选）
2. 信号扫描（单股/批量/全市场）
3. 策略列表
4. 信号统计
5. 信号确认/删除

降级策略：
- 扫描时使用数据服务引擎，失败时返回空列表
- 信号历史从 SQLite 数据库读取
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query, Body

from backend.models.database import (
    DATABASE_PATH,
    init_db,
    add_signal,
    get_signals,
    acknowledge_signal,
    delete_signal,
    get_db,
    track_signal_performance,
    get_signal_performance_stats,
    update_signal_status,
)
from backend.services.data_provider import get_data_provider_service
from backend.services.signal_engine import (
    get_signal_engine,
    SignalEngine,
    SignalResult,
    SignalStrategy,
    SignalCategory,
    SignalType,
)

router = APIRouter()


# 信号类型 / 策略中文映射
SIGNAL_TYPE_LABELS = {
    "BUY": "买入",
    "SELL": "卖出",
    "WATCH": "关注",
    "ALERT": "预警",
    "HOLD": "观望",
}

STRATEGY_LABELS = {
    "ma_golden_cross": "均线金叉",
    "ma_death_cross": "均线死叉",
    "vol_price_breakout": "放量突破",
    "vol_price_collapse": "放量下跌",
    "cai_sen_w_bottom": "蔡森 W 底",
    "cai_sen_head_shoulder": "蔡森头肩底",
    "bai_da_right_side": "右侧买入",
    "signal_composer": "多因子合成",
    "vwap_break": "突破均价",
    "vol_surge_stagnation": "放量滞涨",
    "opening_eight": "开盘八法",
}


# ───────────────────────────────────────────────
# Pydantic Models
# ───────────────────────────────────────────────

class SignalScanRequest(BaseModel):
    """信号扫描请求"""
    symbols: List[str] = Field(default_factory=list, description="股票代码列表")
    strategies: Optional[List[str]] = None
    category: Optional[str] = None  # daily / intraday


class SignalAcknowledgeRequest(BaseModel):
    """信号确认请求"""
    pass


# ───────────────────────────────────────────────
# Helper functions
# ───────────────────────────────────────────────

async def _get_db_conn():
    """获取数据库连接"""
    return await init_db(DATABASE_PATH)


def _get_data_provider():
    """获取数据服务"""
    return get_data_provider_service()


def _get_engine() -> SignalEngine:
    """获取信号引擎"""
    provider = _get_data_provider()
    return get_signal_engine(data_provider=provider)


def _signal_result_to_dict(s: SignalResult) -> Dict[str, Any]:
    """将 SignalResult 转换为字典"""
    st = s.signal_type.value
    stg = s.strategy.value
    return {
        "symbol": s.symbol,
        "name": s.name,
        "timestamp": s.timestamp.isoformat() if isinstance(s.timestamp, datetime) else str(s.timestamp),
        "signal_type": st,
        "signal_type_label": SIGNAL_TYPE_LABELS.get(st, st),
        "strategy": stg,
        "strategy_label": STRATEGY_LABELS.get(stg, stg),
        "category": s.category.value,
        "description": s.description,
        "confidence": round(s.confidence, 2) if s.confidence is not None else None,
        "price": round(s.price, 2) if s.price is not None else None,
        "target_price": round(s.target_price, 2) if s.target_price is not None else None,
        "stop_loss": round(s.stop_loss, 2) if s.stop_loss is not None else None,
        "extra_data": s.extra_data,
    }


# ───────────────────────────────────────────────
# API Routes
# ───────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    symbol: Optional[str] = Query(None, description="筛选股票代码"),
    strategy: Optional[str] = Query(None, description="筛选策略"),
    category: Optional[str] = Query(None, description="筛选分类 daily/intraday"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    获取信号历史列表
    
    从 SQLite 数据库读取已保存的信号。
    """
    conn = await _get_db_conn()
    try:
        # 数据库查询（暂时使用 strategy 参数，数据库字段为 strategy）
        items = await get_signals(conn, symbol=symbol, strategy=strategy, limit=limit, offset=offset)
        
        # 过滤 category（如果数据库中没有 category 字段，信号扫描时保存再处理）
        if category:
            # category 字段在数据库中目前没有，返回全部
            pass
        
        # 为 DB 结果补充 category 字段（根据 strategy 名称推断）
        strategy_to_category = {
            'ma_golden_cross': 'daily', 'ma_death_cross': 'daily',
            'vol_price_breakout': 'daily', 'vol_price_collapse': 'daily',
            'cai_sen_w_bottom': 'daily', 'cai_sen_head_shoulder': 'daily',
            'bai_da_right_side': 'daily',
            'vwap_break': 'intraday', 'vol_surge_stagnation': 'intraday',
            'opening_eight': 'intraday',
        }
        for item in items:
            item['category'] = strategy_to_category.get(item.get('strategy', ''), 'daily')
        
        # 从 stock-list 补充缺失的中文名称，并附加中文标签
        name_map = {}
        try:
            stock_df = _get_data_provider().fetch_stock_list()
            if stock_df is not None and len(stock_df) > 0 and "code" in stock_df.columns and "name" in stock_df.columns:
                for _, row in stock_df.iterrows():
                    code = str(row.get("code", "")).zfill(6)
                    name = str(row.get("name", "")).strip()
                    if code and name and name != code:
                        name_map[code] = name
        except Exception:
            pass
        
        for item in items:
            symbol = str(item.get("symbol", "")).zfill(6)
            name = item.get("name", "")
            if not name or name == symbol:
                item["name"] = name_map.get(symbol, symbol)

            st = item.get("signal_type", "")
            item["signal_type_label"] = SIGNAL_TYPE_LABELS.get(st, st)
            stg = item.get("strategy", "")
            item["strategy_label"] = STRATEGY_LABELS.get(stg, stg)

            # 价格字段保留两位小数，消除浮点精度溢出
            for key in ("price", "target_price", "stop_loss"):
                val = item.get(key)
                if val is not None and isinstance(val, (int, float)):
                    item[key] = round(float(val), 2)

        return {
            "count": len(items),
            "limit": limit,
            "offset": offset,
            "signals": items,
        }
    finally:
        await conn.close()


@router.post("/signals/scan")
async def scan_signals(request: SignalScanRequest):
    """
    扫描信号（单股/批量）
    
    对指定的股票列表运行信号检测，并将新信号保存到数据库。
    """
    engine = _get_engine()
    provider = _get_data_provider()
    conn = await _get_db_conn()
    
    try:
        all_results = []
        saved_count = 0
        
        # 解析策略过滤
        strategy_filter = None
        if request.strategies:
            strategy_filter = [SignalStrategy(s) for s in request.strategies]
        
        # 解析分类过滤
        category_filter = None
        if request.category:
            category_filter = SignalCategory(request.category)
        
        for symbol in request.symbols:
            # 获取股票名称（简化：使用 symbol 作为 name，实际应从数据服务获取）
            name = symbol
            try:
                quotes = provider.fetch_realtime_quotes([symbol])
                if quotes and quotes[0].name:
                    name = quotes[0].name
            except Exception:
                pass
            
            # 获取日线数据
            df = provider.get_kline_latest(symbol, n=60, period="daily")
            if df is None or len(df) < 30:
                continue
            
            # 检测日线信号
            if category_filter is None or category_filter == SignalCategory.DAILY:
                results = engine.detect_daily(df, symbol, name, strategies=strategy_filter)
                for r in results:
                    # 保存到数据库（去重）
                    try:
                        sid = await add_signal(
                            conn,
                            symbol=r.symbol,
                            name=r.name,
                            signal_type=r.signal_type.value,
                            strategy=r.strategy.value,
                            description=r.description,
                            confidence=r.confidence,
                            price=r.price,
                            target_price=r.target_price,
                            stop_loss=r.stop_loss,
                            timestamp=r.timestamp.isoformat() if isinstance(r.timestamp, datetime) else str(r.timestamp),
                        )
                        if sid:
                            saved_count += 1
                    except Exception as e:
                        pass
                    all_results.append(r)
            
            # 检测日内信号（需要分钟数据，暂不默认启用）
            # 仅在明确请求 intraday 时执行
        
        return {
            "status": "ok",
            "scanned": len(request.symbols),
            "signals_found": len(all_results),
            "saved": saved_count,
            "signals": [_signal_result_to_dict(s) for s in all_results],
        }
    
    finally:
        await conn.close()


@router.post("/signals/scan-daily")
async def scan_daily_signals(
    symbols: List[str] = Body(..., description="股票代码列表"),
    strategies: Optional[List[str]] = Body(None),
):
    """
    快速扫描日线信号
    
    对指定股票列表执行日线信号检测，返回最新信号。
    """
    engine = _get_engine()
    provider = _get_data_provider()
    conn = await _get_db_conn()
    
    try:
        all_results = []
        strategy_filter = [SignalStrategy(s) for s in strategies] if strategies else None
        
        for symbol in symbols:
            name = symbol
            try:
                quotes = provider.fetch_realtime_quotes([symbol])
                if quotes and quotes[0].name:
                    name = quotes[0].name
            except Exception:
                pass
            
            df = provider.get_kline_latest(symbol, n=60, period="daily")
            if df is None or len(df) < 30:
                continue
            
            results = engine.detect_daily(df, symbol, name, strategies=strategy_filter)
            
            # 保存到数据库（去重）
            for r in results:
                try:
                    await add_signal(
                        conn,
                        symbol=r.symbol,
                        name=r.name,
                        signal_type=r.signal_type.value,
                        strategy=r.strategy.value,
                        description=r.description,
                        confidence=r.confidence,
                        price=r.price,
                        target_price=r.target_price,
                        stop_loss=r.stop_loss,
                        timestamp=r.timestamp.isoformat() if isinstance(r.timestamp, datetime) else str(r.timestamp),
                    )
                except Exception:
                    pass
            
            all_results.extend(results)
        
        return {
            "status": "ok",
            "scanned": len(symbols),
            "signals_found": len(all_results),
            "signals": [_signal_result_to_dict(s) for s in all_results],
        }
    
    finally:
        await conn.close()


@router.get("/signals/strategies")
async def list_strategies():
    """获取所有可用策略列表"""
    engine = _get_engine()
    strategies = engine.get_strategy_list()
    
    return {
        "count": len(strategies),
        "strategies": strategies,
    }


@router.get("/signals/stats")
async def signal_stats(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    symbol: Optional[str] = Query(None),
):
    """
    信号统计
    
    统计信号类型分布、策略分布、成功率等。
    """
    conn = await _get_db_conn()
    try:
        # 获取最近信号
        since = (datetime.now() - timedelta(days=days)).isoformat()
        items = await get_signals(conn, symbol=symbol, limit=1000)
        
        # 过滤时间
        recent_items = [s for s in items if s.get("timestamp", "") >= since]
        
        # 统计
        type_counts = {}
        strategy_counts = {}
        
        for s in recent_items:
            t = s.get("signal_type", "UNKNOWN")
            type_counts[t] = type_counts.get(t, 0) + 1
            
            st = s.get("strategy", "UNKNOWN")
            strategy_counts[st] = strategy_counts.get(st, 0) + 1
        
        return {
            "period_days": days,
            "total_signals": len(recent_items),
            "by_type": type_counts,
            "by_strategy": strategy_counts,
        }
    
    finally:
        await conn.close()


@router.post("/signals/{signal_id}/acknowledge")
async def ack_signal(signal_id: str):
    """确认信号（标记为已读）"""
    conn = await _get_db_conn()
    try:
        ok = await acknowledge_signal(conn, signal_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Signal not found: {signal_id}")
        return {"status": "ok", "signal_id": signal_id}
    finally:
        await conn.close()


@router.delete("/signals/{signal_id}")
async def remove_signal(signal_id: str):
    """删除信号"""
    conn = await _get_db_conn()
    try:
        ok = await delete_signal(conn, signal_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Signal not found: {signal_id}")
        return {"status": "ok", "signal_id": signal_id}
    finally:
        await conn.close()


@router.get("/signals/watchlist-scan")
async def scan_watchlist_signals(
    strategies: Optional[List[str]] = Query(None),
):
    """
    扫描自选股信号
    
    自动获取所有自选股并运行信号检测。
    """
    from backend.models.database import get_watchlist
    
    conn = await _get_db_conn()
    provider = _get_data_provider()
    engine = _get_engine()
    
    try:
        # 获取自选股列表
        watchlist_items = await get_watchlist(conn)
        if not watchlist_items:
            return {"status": "ok", "scanned": 0, "signals_found": 0, "signals": []}
        
        symbols = [(item.symbol, item.name) for item in watchlist_items]
        strategy_filter = [SignalStrategy(s) for s in strategies] if strategies else None
        
        all_results = []
        for symbol, name in symbols:
            df = provider.get_kline_latest(symbol, n=60, period="daily")
            if df is None or len(df) < 30:
                continue
            
            results = engine.detect_daily(df, symbol, name, strategies=strategy_filter)
            
            # 保存新信号（去重）
            for r in results:
                try:
                    await add_signal(
                        conn,
                        symbol=r.symbol,
                        name=r.name,
                        signal_type=r.signal_type.value,
                        strategy=r.strategy.value,
                        description=r.description,
                        confidence=r.confidence,
                        price=r.price,
                        target_price=r.target_price,
                        stop_loss=r.stop_loss,
                        timestamp=r.timestamp.isoformat() if isinstance(r.timestamp, datetime) else str(r.timestamp),
                    )
                except Exception:
                    pass
            
            all_results.extend(results)
        
        return {
            "status": "ok",
            "scanned": len(symbols),
            "signals_found": len(all_results),
            "signals": [_signal_result_to_dict(s) for s in all_results],
        }
    
    finally:
        await conn.close()


@router.post("/signals/{signal_id}/track")
async def track_signal(signal_id: str, current_price: float = Query(..., description="当前价格")):
    """
    追踪信号绩效

    根据当前价格更新信号的浮动盈亏，并检查是否触发目标/止损。
    """
    conn = await _get_db_conn()
    try:
        result = await track_signal_performance(conn, signal_id, current_price)
        if not result:
            raise HTTPException(status_code=404, detail=f"Signal not found or already closed: {signal_id}")
        return {
            "status": "ok",
            "signal_id": signal_id,
            **result,
        }
    finally:
        await conn.close()


@router.get("/signals/performance")
async def signal_performance(
    strategy: Optional[str] = Query(None, description="策略过滤"),
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
):
    """
    信号绩效统计

    统计信号胜率、平均盈亏、最大盈利/亏损等。
    """
    conn = await _get_db_conn()
    try:
        stats = await get_signal_performance_stats(conn, strategy=strategy, days=days)
        return stats
    finally:
        await conn.close()


@router.post("/signals/{signal_id}/close")
async def close_signal(
    signal_id: str,
    status: str = Query(..., enum=["hit_target", "hit_stop", "expired", "manual"]),
    exit_price: float = Query(..., description="退出价格"),
):
    """
    手动关闭信号

    标记信号为已平仓，并记录退出价格和盈亏。
    """
    conn = await _get_db_conn()
    try:
        cursor = await conn.execute(
            "SELECT price, signal_type FROM signals WHERE id = ?",
            (signal_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Signal not found: {signal_id}")
        
        entry_price = row["price"] or exit_price
        signal_type = row["signal_type"]
        
        if signal_type == "BUY":
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100
        
        ok = await update_signal_status(conn, signal_id, status, exit_price, pnl_pct)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to close signal")
        
        return {
            "status": "ok",
            "signal_id": signal_id,
            "exit_price": exit_price,
            "pnl_pct": round(pnl_pct, 2),
        }
    finally:
        await conn.close()


@router.post("/signals/expire-old")
async def expire_old_signals_api(
    days: int = Query(7, ge=1, le=30, description="超过 N 天未触发的信号标记为过期"),
):
    """
    自动过期旧信号

    将超过 N 天仍未触发的信号标记为过期。
    """
    from backend.models.database import expire_old_signals
    conn = await _get_db_conn()
    try:
        count = await expire_old_signals(conn, days=days)
        return {
            "status": "ok",
            "expired_count": count,
            "days_threshold": days,
        }
    finally:
        await conn.close()
