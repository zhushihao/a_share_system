from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional
from datetime import datetime
import pandas as pd

from backend.services.data_platform import get_data_platform_service
from backend.services.data_provider import DataProviderService, get_data_provider_service

# 新分析模块导入
from backend.services.patterns import detect_all_patterns
from backend.services.volume_analysis import (
    detect_volume_nodes,
    detect_volume_price_divergence,
    calculate_support_resistance,
    calculate_fibonacci_levels as vol_fibonacci_levels,
)
from backend.services.wave import detect_wave_structure
from backend.services.signal_composer import compose_signal
from backend.services.multi_period_resonance import analyze_resonance

router = APIRouter()


# 技术指标中文标签
INDICATOR_LABELS = {
    "ma5": "5日均线",
    "ma10": "10日均线",
    "ma20": "20日均线",
    "ma60": "60日均线",
    "macd_dif": "MACD差离值",
    "macd_dea": "MACD信号线",
    "macd_bar": "MACD柱状线",
    "macd": "MACD",
    "kdj_k": "KDJ-K线",
    "kdj_d": "KDJ-D线",
    "kdj_j": "KDJ-J线",
    "rsi6": "RSI(6)",
    "rsi12": "RSI(12)",
    "rsi24": "RSI(24)",
    "boll_up": "布林上轨",
    "boll_mid": "布林中轨",
    "boll_down": "布林下轨",
    "obv": "OBV能量潮",
    "dmi_pdi": "DMI+DI",
    "dmi_mdi": "DMI-DI",
    "dmi_adx": "DMI-ADX",
}

# 技术形态中文显示名称与描述词映射
PATTERN_DISPLAY_NAMES = {
    "v_reversal": "V型反转",
    "head_shoulder_top": "头肩顶",
    "head_shoulder_bottom": "头肩底",
    "double_top": "双顶",
    "double_bottom": "双底",
    "triangle": "三角形",
    "fibonacci_retracement": "斐波那契回调",
}

PATTERN_SUBTYPE_LABELS = {
    "convergent": "收敛",
    "ascending": "上升",
    "descending": "下降",
    "bottom": "底部",
    "top": "顶部",
    "breakout": "突破",
}


def _get_platform():
    """获取数据中台实例"""
    return get_data_platform_service()


def _get_provider() -> DataProviderService:
    """获取数据服务实例（兼容旧代码）"""
    return get_data_provider_service()


@router.get("/quote/health")
async def quote_health():
    """数据源健康检查"""
    provider = _get_provider()
    health = provider.health_check()
    return {
        "status": "ok" if health.get("offline_available") or health.get("realtime_available") else "degraded",
        "sources": health,
    }


@router.get("/quotes/batch")
async def get_multi_quotes(symbols: str = Query(..., description="逗号分隔的股票代码，如 000001,600519")):
    """获取多股实时行情（批量接口）"""
    provider = _get_provider()
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    
    if not symbol_list:
        raise HTTPException(status_code=422, detail="symbols parameter is required")
    
    if len(symbol_list) > 50:
        raise HTTPException(status_code=400, detail="Max 50 symbols allowed")
    
    quotes = provider.fetch_realtime_quotes(symbol_list)
    
    return {
        "count": len(quotes),
        "symbols": symbol_list,
        "quotes": [q.model_dump() for q in quotes],
    }


@router.get("/quote/{symbol}/ohlcv")
@router.get("/quote/{symbol}/daily")
async def get_ohlcv(
    symbol: str,
    start_date: str = "",
    end_date: str = "",
    period: str = Query("daily", enum=["1m", "5m", "15m", "30m", "60m", "minute", "daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
    limit: int = Query(0, ge=0, le=1000),
):
    """
    获取K线数据（OHLCV）— 走数据平台缓存
    
    - **symbol**: 股票代码（如 600519, 000001）
    - **start_date**: 起始日期（YYYYMMDD）
    - **end_date**: 结束日期（YYYYMMDD）
    - **period**: 周期（minute/daily/weekly/monthly）
    - **adjust**: 复权方式（qfq: 前复权, hfq: 后复权, none: 不复权）
    - **limit**: 返回最近 N 条（0 表示全部）
    """
    platform = _get_platform()
    df = platform.get_ohlcv(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        period=period,
        adjust=adjust,
    )
    
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Kline data not found for {symbol}")
    
    # 限制返回条数
    if limit > 0:
        df = df.tail(limit).reset_index(drop=True)
    
    # 对价格字段做精度处理（A股价格通常为2位小数）
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols:
        if col in df.columns:
            df[col] = df[col].round(2)

    # 转换为字典列表
    records = df.to_dict("records")

    # 数据时效性检查：若最新数据延迟超过30天，返回告警信息
    data_warning = None
    delay_days = None
    latest_date = None
    if "date" in df.columns and len(df) > 0:
        latest_date = df["date"].iloc[-1]
        try:
            latest_dt = pd.to_datetime(latest_date).date()
            delay_days = (datetime.date.today() - latest_dt).days
            if delay_days > 30:
                data_warning = f"个股K线数据延迟 {delay_days} 天，最新数据日期为 {latest_dt}，建议更新本地数据源"
        except Exception:
            pass

    return {
        "symbol": symbol,
        "period": period,
        "adjust": adjust,
        "count": len(records),
        "latest_date": latest_date,
        "delay_days": delay_days,
        "data_warning": data_warning,
        "data": records,
    }


@router.get("/quote/{symbol}/indicators")
async def get_indicators(
    symbol: str,
    start_date: str = "",
    end_date: str = "",
    period: str = Query("daily", enum=["1m", "5m", "15m", "30m", "60m", "minute", "daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
    limit: int = Query(120, ge=0, le=1000),
):
    """
    获取K线数据 + 技术指标（走数据平台缓存）
    
    返回最近 N 条 K 线数据，以及最新一行的指标值。
    """
    platform = _get_platform()
    df = platform.get_indicators(symbol, period=period, adjust=adjust)
    
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Data not found for {symbol}")
    
    # 限制返回条数
    if limit > 0:
        df = df.tail(limit).reset_index(drop=True)
    
    # 获取最新指标
    latest_indicators = platform.get_latest_indicators(symbol, period=period, adjust=adjust)
    
    records = df.to_dict("records")
    indicator_keys = list(latest_indicators.keys()) if latest_indicators else []
    labels = {k: INDICATOR_LABELS.get(k, k) for k in indicator_keys}
    
    return {
        "symbol": symbol,
        "period": period,
        "adjust": adjust,
        "count": len(records),
        "indicators": latest_indicators or {},
        "labels": labels,
        "data": records,
    }


@router.get("/quote/{symbol}/score")
async def get_tech_score(
    symbol: str,
    period: str = Query("daily", enum=["1m", "5m", "15m", "30m", "60m", "minute", "daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
):
    """获取技术评分（0-100）— 支持多周期"""
    from backend.services.indicators import calc_tech_score
    
    platform = _get_platform()
    df = platform.get_indicators(symbol, period=period, adjust=adjust)
    
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Data not found for {symbol}")
    
    try:
        score = calc_tech_score(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Score calculation failed: {str(e)}")
    
    return {
        "symbol": symbol,
        "period": period,
        "score": score,
        "level": "强势" if score >= 70 else "中性" if score >= 40 else "弱势",
    }


@router.get("/quote/{symbol}")
async def get_realtime_quote(symbol: str):
    """获取单股实时行情（5分钟缓存）"""
    platform = _get_platform()
    quote = platform.get_stock_quote(symbol)
    
    if not quote:
        raise HTTPException(status_code=404, detail=f"Quote not found for {symbol}")
    
    return quote


# ═══════════════════════════════════════════════════════
# 新增：形态识别 / 量价分析 / 波浪结构 路由
# ═══════════════════════════════════════════════════════


@router.get("/quote/{symbol}/patterns")
async def get_patterns(
    symbol: str,
    period: str = Query("daily", enum=["1m", "5m", "15m", "30m", "60m", "minute", "daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
):
    """
    获取价格形态识别结果

    检测双顶、双底、头肩顶、头肩底、三角形、V型反转、斐波那契回调。
    """
    platform = _get_platform()
    df = platform.get_ohlcv(symbol, period=period, adjust=adjust)
    
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Kline data not found for {symbol}")
    
    patterns = detect_all_patterns(df)
    
    # 统一字段名：兼容前端 PatternData 类型和 API 规范
    normalized_patterns = []
    for p in patterns:
        np = dict(p)
        ptype = np.pop("type", "") or np.get("pattern", "")
        np["pattern"] = ptype
        np["pattern_type"] = ptype
        np["name"] = ptype
        # 中文显示名称
        np["display_name"] = PATTERN_DISPLAY_NAMES.get(ptype, ptype)
        # position 映射：从 subtype 推断，若为空则根据形态类型推断
        subtype = np.get("subtype", "")
        if not subtype or not str(subtype).strip():
            ptype = np.get("pattern", "") or np.get("pattern_type", "") or np.get("type", "")
            if "top" in ptype.lower():
                subtype = "top"
            elif "bottom" in ptype.lower():
                subtype = "bottom"
            elif "breakout" in ptype.lower() or "breakdown" in ptype.lower():
                subtype = "breakout"
        np["position"] = subtype
        np["accuracy"] = np.get("confidence", 0)
        # 将 description 中的英文子类型翻译为中文，提升可读性
        reason = str(np.get("description", "") or "")
        for en, cn in PATTERN_SUBTYPE_LABELS.items():
            reason = reason.replace(en, cn)
        np["reason"] = reason
        normalized_patterns.append(np)
    
    return {
        "symbol": symbol,
        "period": period,
        "count": len(normalized_patterns),
        "patterns": normalized_patterns,
    }


@router.get("/quote/{symbol}/volume-analysis")
async def get_volume_analysis(
    symbol: str,
    period: str = Query("daily", enum=["1m", "5m", "15m", "30m", "60m", "minute", "daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
    window: int = Query(20, ge=5, le=60, description="背离检测窗口"),
):
    """
    获取量价分析结果

    返回量价节点（放量突破、缩量回调、天量、地量）和量价背离。
    节点字段：node_type, volume, price, timestamp, strength, reason
    """
    platform = _get_platform()
    df = platform.get_ohlcv(symbol, period=period, adjust=adjust)
    
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Kline data not found for {symbol}")
    
    nodes = detect_volume_nodes(df)
    divergences = detect_volume_price_divergence(df, window=window)
    fibonacci = vol_fibonacci_levels(df)
    
    # 限制返回最近 30 个量价节点（避免历史数据过多导致前端负载）
    nodes = nodes[-30:] if len(nodes) > 30 else nodes
    
    # 统一字段名：兼容前端 VolumeNodeData 类型和 API 规范
    normalized_nodes = []
    for n in nodes:
        nn = dict(n)
        nn["node_type"] = nn.get("type", "")
        nn["price"] = nn.get("close", 0)
        nn["timestamp"] = nn.get("date", "")
        nn["volume_ratio"] = nn.get("vol_ratio", 0)
        nn["strength"] = nn.get("vol_ratio", 0)  # 用成交量倍率作为强度
        nn["reason"] = nn.get("description", "")
        normalized_nodes.append(nn)
    
    return {
        "symbol": symbol,
        "period": period,
        "nodes": normalized_nodes,
        "divergences": divergences,
        "fibonacci_levels": fibonacci,
        "node_count": len(normalized_nodes),
        "divergence_count": len(divergences),
    }


@router.get("/quote/{symbol}/support-resistance")
async def get_support_resistance(
    symbol: str,
    period: str = Query("daily", enum=["1m", "5m", "15m", "30m", "60m", "minute", "daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
    window: int = Query(60, ge=20, le=120, description="近期窗口"),
    lookback: int = Query(252, ge=60, le=500, description="历史回看窗口"),
):
    """
    获取关键支撑与阻力位
    """
    platform = _get_platform()
    df = platform.get_ohlcv(symbol, period=period, adjust=adjust)
    
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Kline data not found for {symbol}")
    
    sr = calculate_support_resistance(df, window=window, lookback=lookback)
    fibonacci = vol_fibonacci_levels(df)
    
    # 统一返回格式：前端期望 support: number[] 和 resistance: number[]
    # 同时保留 levels 字段用于详细表格展示
    support_prices = [s["price"] for s in sr.get("support_levels", [])]
    resistance_prices = [r["price"] for r in sr.get("resistance_levels", [])]
    
    # 构建 levels 数组（兼容前端表格）
    levels = []
    for s in sr.get("support_levels", []):
        levels.append({
            "price": s["price"],
            "type": "support",
            "strength": s.get("strength", 0.5),
        })
    for r in sr.get("resistance_levels", []):
        levels.append({
            "price": r["price"],
            "type": "resistance",
            "strength": r.get("strength", 0.5),
        })
    
    return {
        "symbol": symbol,
        "period": period,
        "support": sorted(support_prices),
        "resistance": sorted(resistance_prices),
        "levels": levels,
        "fibonacci_levels": fibonacci,
        "recent_high": sr.get("recent_high"),
        "recent_low": sr.get("recent_low"),
    }


@router.get("/quote/{symbol}/wave-structure")
async def get_wave_structure(
    symbol: str,
    period: str = Query("daily", enum=["1m", "5m", "15m", "30m", "60m", "minute", "daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
    window: int = Query(120, ge=60, le=252, description="波浪检测窗口"),
):
    """
    获取艾略特波浪结构分析

    基于高低点序列识别 5-3 波浪结构。
    """
    platform = _get_platform()
    df = platform.get_ohlcv(symbol, period=period, adjust=adjust)
    
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Kline data not found for {symbol}")
    
    waves = detect_wave_structure(df, window=window)
    
    return {
        "symbol": symbol,
        "period": period,
        "count": len(waves),
        "waves": waves,
    }


@router.get("/quote/{symbol}/fibonacci")
async def get_fibonacci(
    symbol: str,
    period: str = Query("daily", enum=["1m", "5m", "15m", "30m", "60m", "minute", "daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
    swing_window: int = Query(30, ge=10, le=60, description="波段窗口"),
):
    """
    获取斐波那契关键位

    返回回调位和扩展位。
    """
    platform = _get_platform()
    df = platform.get_ohlcv(symbol, period=period, adjust=adjust)
    
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Kline data not found for {symbol}")
    
    levels = vol_fibonacci_levels(df, swing_window=swing_window)
    
    return {
        "symbol": symbol,
        "period": period,
        **levels,
    }


@router.get("/quote/{symbol}/signal")
async def get_trading_signal(
    symbol: str,
    period: str = Query("daily", enum=["1m", "5m", "15m", "30m", "60m", "minute", "daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
):
    """
    获取多因子合成交易信号（买卖点）

    综合技术指标、形态识别、量价分析、支撑阻力，
    输出完整交易计划：买入/卖出 + 入场价 + 止损 + 止盈 + 置信度 + 理由。
    """
    platform = _get_platform()
    
    # 1. 获取基础数据
    df = platform.get_ohlcv(symbol, period=period, adjust=adjust)
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Kline data not found for {symbol}")
    
    # 2. 获取指标（带指标列的K线数据）
    indicators_df = platform.get_indicators(symbol, period=period, adjust=adjust)
    if indicators_df is None or len(indicators_df) == 0:
        raise HTTPException(status_code=404, detail=f"Indicator data not found for {symbol}")
    
    latest_indicators = {}
    from backend.services.indicators import get_latest_indicators
    latest_indicators = get_latest_indicators(indicators_df)
    
    # 3. 获取形态
    patterns = detect_all_patterns(df)
    
    # 4. 获取量价分析
    volume_nodes = detect_volume_nodes(df)
    divergences = detect_volume_price_divergence(df)
    volume_analysis = volume_nodes + divergences
    
    # 5. 获取支撑阻力
    sr = calculate_support_resistance(df)
    
    # 6. 合成信号
    signal = compose_signal(
        symbol=symbol,
        df=indicators_df,
        indicators=latest_indicators,
        patterns=patterns,
        volume_analysis=volume_analysis,
        support_resistance=sr,
        period=period,
    )
    
    # 7. 保存信号到数据库（confidence >= 0.5 即保存，用于历史追踪和策略评估）
    if signal.confidence >= 0.5:
        try:
            from backend.models.database import init_db, DATABASE_PATH, add_signal
            import asyncio
            import logging
            
            logger = logging.getLogger("quote")
            
            async def _save_signal():
                conn = await init_db(DATABASE_PATH)
                try:
                    # 获取股票真实名称
                    stock_name = symbol
                    try:
                        quote_info = platform.get_stock_quote(symbol)
                        if quote_info and quote_info.get("name"):
                            stock_name = quote_info.get("name")
                    except Exception:
                        pass
                    await add_signal(
                        conn,
                        symbol=symbol,
                        name=stock_name,
                        signal_type=signal.type,
                        strategy="signal_composer",
                        description=signal.rationale,
                        confidence=int(signal.confidence * 100),
                        price=signal.entry_price,
                        target_price=signal.take_profit if signal.take_profit > 0 else None,
                        stop_loss=signal.stop_loss if signal.stop_loss > 0 else None,
                        timestamp=signal.timestamp,
                    )
                except Exception as e:
                    logger.error(f"Signal save failed for {symbol}: {e}")
                finally:
                    await conn.close()
            
            # 在后台执行保存（不阻塞API响应）
            asyncio.create_task(_save_signal())
        except Exception as e:
            logger = logging.getLogger("quote")
            logger.error(f"Signal save task creation failed for {symbol}: {e}")
    
    return signal.to_dict()


@router.get("/quote/{symbol}/resonance")
async def get_resonance(
    symbol: str,
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
):
    """
    多周期共振分析

    同时分析日/周/月三个周期的趋势方向，
    判断三周期是否同向（共振 = 高置信度）。
    """
    platform = _get_platform()
    result = analyze_resonance(symbol, platform)
    
    return {
        "symbol": symbol,
        **result,
    }


@router.post("/quote/scan/resonance")
async def scan_resonance(
    symbols: List[str] = Body(..., description="股票代码列表"),
    min_confidence: float = Query(0.7, ge=0.5, le=1.0, description="最小置信度"),
    require_resonance: bool = Query(True, description="是否要求三周期共振"),
):
    """
    批量多周期共振扫描

    对给定股票列表进行多周期共振分析，筛选出符合条件的标的。
    """
    platform = _get_platform()
    results = []
    
    for symbol in symbols:
        try:
            result = analyze_resonance(symbol, platform)
            if result["confidence"] >= min_confidence:
                if not require_resonance or result["resonance"]:
                    results.append({
                        "symbol": symbol,
                        **result,
                    })
        except Exception:
            pass
    
    # 按置信度排序
    results.sort(key=lambda x: x["confidence"], reverse=True)
    
    return {
        "scanned": len(symbols),
        "matched": len(results),
        "results": results,
    }


# ═══════════════════════════════════════════════════════
# 新增：个股详情 / 五档 / 分时 / F10 路由
# ═══════════════════════════════════════════════════════

@router.get("/quote/{symbol}/intraday")
async def get_intraday(
    symbol: str,
    date: str = Query("", description="日期(YYYYMMDD)，空则返回最新交易日"),
):
    """
    获取个股分时图数据（分钟级）

    数据来源：本地通达信离线分钟数据（reader.minute）
    返回当日或指定日期的 1 分钟 OHLCV 数据。
    """
    provider = _get_provider()
    code = provider.provider._normalize_code(symbol) if hasattr(provider.provider, '_normalize_code') else symbol
    try:
        provider.provider._offline._init_reader()
        reader = provider.provider._offline._reader
        if reader is None:
            raise HTTPException(status_code=503, detail="Reader not initialized")
        df = reader.minute(symbol=code)
        if df is None or len(df) == 0:
            raise HTTPException(status_code=404, detail=f"Intraday data not found for {symbol}")
        # Ensure date index is a column
        if df.index.name == "date":
            df = df.reset_index()
        elif "date" not in df.columns:
            df = df.reset_index()
        # Convert date to datetime and create a YYYYMMDD string for filtering
        df["date_dt"] = pd.to_datetime(df["date"])
        df["date_str"] = df["date_dt"].dt.strftime("%Y%m%d")
        # Filter by date
        if date:
            df = df[df["date_str"] == date]
            date_str = date
        else:
            # Get latest trading day
            date_str = df["date_str"].iloc[-1]
            df = df[df["date_str"] == date_str]
        if len(df) == 0:
            raise HTTPException(status_code=404, detail=f"Intraday data not found for {symbol} on {date_str}")
        records = []
        for _, row in df.iterrows():
            ts = row["date_dt"]
            if hasattr(ts, "isoformat"):
                ts_str = ts.isoformat()
            elif hasattr(ts, "strftime"):
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts_str = str(ts)
            records.append({
                "time": ts_str,
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": int(row["volume"]),
                "amount": round(float(row.get("amount", 0)), 2),
            })
        return {
            "symbol": symbol,
            "date": date_str,
            "count": len(records),
            "data": records,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Intraday fetch failed: {str(e)}")


def _fix_gbk_text(text) -> str:
    """尝试修复 mootdx F10 的 GBK 编码问题"""
    if isinstance(text, bytes):
        return text.decode("gbk", errors="ignore")
    if not isinstance(text, str):
        return str(text)
    # mootdx 常把 GBK 字节按 latin1/ISO-8859-1 解码成字符串，
    # 因此用 latin1 重新编码回字节再按 GBK 解码。
    # 如果字符串本身是正确的中文（codepoint>255），encode('latin1') 会直接报错，
    # 此时原样返回即可。
    try:
        return text.encode("latin1").decode("gbk", errors="ignore")
    except UnicodeEncodeError:
        return text


def _fix_gbk_value(value):
    """递归修复 F10 返回对象中的字符串编码"""
    if isinstance(value, str):
        return _fix_gbk_text(value)
    if isinstance(value, bytes):
        return _fix_gbk_text(value)
    if isinstance(value, dict):
        return {_fix_gbk_text(k): _fix_gbk_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_fix_gbk_value(v) for v in value]
    return value


@router.get("/quote/{symbol}/profile")
async def get_stock_profile(symbol: str):
    """
    获取个股基本信息（F10）

    优先调用 mootdx F10 接口；若不可用则降级到股票列表基本信息。
    """
    provider = _get_provider()
    try:
        # 尝试通过实时客户端获取 F10
        if not getattr(provider.provider._realtime, "_initialized", False):
            provider.provider._realtime._init_client()
        client = getattr(provider.provider._realtime, "_client", None)
        if client is not None:
            f10 = client.F10(symbol=symbol)
            if f10 is not None and isinstance(f10, dict):
                # 修复编码（含嵌套结构）
                fixed = _fix_gbk_value(f10)
                if not isinstance(fixed, dict):
                    fixed = {"data": fixed}
                return {
                    "symbol": symbol,
                    "source": "mootdx-F10",
                    "data": fixed,
                }
    except Exception:
        pass

    # 降级：从股票列表获取基本信息
    try:
        stock_list = provider.fetch_stock_list()
        name = None
        if stock_list is not None and len(stock_list) > 0:
            code_col = "code" if "code" in stock_list.columns else stock_list.columns[0]
            match = stock_list[stock_list[code_col].astype(str).str.strip().str.zfill(6) == symbol.zfill(6)]
            if len(match) > 0:
                row = match.iloc[0]
                name = str(row.get("name", "")).strip()
        # 如果 stock_list 没有名称，尝试从 quote 获取
        if not name or name == symbol:
            try:
                q = provider.get_stock_quote(symbol)
                if q and q.name:
                    name = q.name
            except Exception:
                pass
        market = "sh" if symbol.startswith("6") else "sz" if symbol.startswith(("0", "3")) else "bj"
        return {
            "symbol": symbol,
            "source": "stock_list_fallback",
            "data": {
                "股票代码": symbol,
                "股票名称": name or symbol,
                "所属市场": market,
                "备注": "F10 实时接口暂不可用，仅返回基础信息",
            },
        }
    except Exception:
        pass

    # 最终降级：仅返回代码
    return {
        "symbol": symbol,
        "source": "minimal",
        "data": {
            "股票代码": symbol,
            "备注": "F10 数据暂不可用",
        },
    }


@router.get("/quote/{symbol}/orderbook")
async def get_orderbook(symbol: str):
    """
    获取个股五档行情（买卖盘）

    优先调用 mootdx 实时 quotes 接口；若不可用则降级到基于最新K线的模拟五档。
    """
    provider = _get_provider()
    try:
        df = provider.provider.fetch_realtime_quote([symbol])
        if df is not None and len(df) > 0:
            row = df.iloc[0]
            bids = []
            asks = []
            for i in range(1, 6):
                bid_price = row.get(f"bid{i}", 0)
                bid_vol = row.get(f"bid_vol{i}", 0)
                ask_price = row.get(f"ask{i}", 0)
                ask_vol = row.get(f"ask_vol{i}", 0)
                bids.append({"level": i, "price": float(bid_price) if bid_price else 0, "volume": int(bid_vol) if bid_vol else 0})
                asks.append({"level": i, "price": float(ask_price) if ask_price else 0, "volume": int(ask_vol) if ask_vol else 0})
            return {
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
                "price": float(row.get("price", row.get("close", 0))),
                "bids": bids,
                "asks": asks,
                "source": "mootdx",
            }
    except Exception:
        pass

    # 降级：基于最新K线生成模拟五档
    try:
        df = provider.fetch_ohlcv(symbol, period="daily", adjust="qfq")
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            close = float(latest["close"])
            open_p = float(latest["open"])
            high = float(latest["high"])
            low = float(latest["low"])
            volume = int(latest.get("volume", 0))
            avg_vol = volume // 10  # 估算每档成交量
            spread = max(0.01, (high - low) * 0.01)  # 最小价差

            bids = []
            asks = []
            for i in range(1, 6):
                bid_price = round(close - i * spread, 2)
                ask_price = round(close + i * spread, 2)
                bid_vol = max(100, avg_vol + i * 100)
                ask_vol = max(100, avg_vol + i * 100)
                bids.append({"level": i, "price": bid_price, "volume": bid_vol})
                asks.append({"level": i, "price": ask_price, "volume": ask_vol})

            return {
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
                "price": close,
                "bids": bids,
                "asks": asks,
                "source": "simulated",
                "note": "实时五档暂不可用，基于最新K线模拟",
            }
    except Exception:
        pass

    # 最终降级
    return {
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "price": 0,
        "bids": [{"level": i, "price": 0, "volume": 0} for i in range(1, 6)],
        "asks": [{"level": i, "price": 0, "volume": 0} for i in range(1, 6)],
        "source": "unavailable",
        "note": "五档数据暂不可用",
    }


# ─────────────────────────────────────────
# 大盘数据
# ─────────────────────────────────────────

@router.get("/market/overview")
async def get_market_overview():
    """
    大盘概览

    返回上证指数、深证成指、创业板指等核心指数的最新行情，
    以及市场情绪指标（涨跌家数、涨跌比、涨停跌停数）。
    """
    from backend.services.data_provider import get_data_provider_service
    from backend.services.data_platform import get_data_platform_service
    
    platform = get_data_provider_service()
    data_platform = get_data_platform_service()
    
    indices = [
        {"code": "sh000001", "name": "上证指数", "key": "sh"},
        {"code": "sz399001", "name": "深证成指", "key": "sz"},
        {"code": "sz399006", "name": "创业板指", "key": "cy"},
        {"code": "sh000688", "name": "科创50", "key": "kc"},
        {"code": "sh000300", "name": "沪深300", "key": "hs300"},
    ]
    
    results = []
    for idx in indices:
        try:
            # 获取指数K线（取最新一条）
            df = platform.fetch_ohlcv(idx["code"], period="daily", adjust="none", source="offline")
            if df is not None and len(df) > 0:
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) >= 2 else latest
                close = float(latest["close"])
                prev_close = float(prev["close"])
                change = close - prev_close
                change_pct = (change / prev_close) * 100 if prev_close > 0 else 0
                
                results.append({
                    "code": idx["code"],
                    "name": idx["name"],
                    "key": idx["key"],
                    "close": round(close, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "open": round(float(latest["open"]), 2),
                    "high": round(float(latest["high"]), 2),
                    "low": round(float(latest["low"]), 2),
                    "volume": int(latest.get("volume", 0)),
                    "date": str(latest.get("date", "")),
                })
        except Exception:
            pass
    
    # 添加市场情绪数据
    sentiment = {}
    try:
        overview = data_platform.get_market_overview()
        if overview:
            sentiment = {
                "up_down_ratio": overview.get("up_down_ratio"),
                "advancing": overview.get("advancing"),
                "declining": overview.get("declining"),
                "flat": overview.get("flat"),
                "limit_up": overview.get("limit_up"),
                "limit_down": overview.get("limit_down"),
                "total_valid": overview.get("total_valid"),
                "source": overview.get("source", "mootdx"),
            }
        else:
            sentiment = {
                "up_down_ratio": None,
                "advancing": None,
                "declining": None,
                "flat": None,
                "limit_up": None,
                "limit_down": None,
                "total_valid": None,
                "source": "unavailable",
                "note": "实时情绪数据暂不可用（非交易日/Quotes客户端未连接）",
            }
    except Exception:
        sentiment = {
            "up_down_ratio": None,
            "advancing": None,
            "declining": None,
            "flat": None,
            "limit_up": None,
            "limit_down": None,
            "total_valid": None,
            "source": "unavailable",
            "note": "实时情绪数据暂不可用（非交易日/Quotes客户端未连接）",
        }
    
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "indices": results,
        "sentiment": sentiment,
    }


@router.get("/market/index/{index_code}")
async def get_index_kline(
    index_code: str,
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
    limit: int = Query(60, ge=1, le=500),
):
    """
    指数K线数据

    支持上证指数(sh000001)、深证成指(sz399001)、创业板指(sz399006)等。
    """
    platform = _get_platform()
    df = platform.get_ohlcv(index_code, period=period, adjust="none")
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Index data not found: {index_code}")
    
    df = df.tail(limit).reset_index(drop=True)
    data = []
    for _, row in df.iterrows():
        data.append({
            "date": str(row.get("date", "")),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row.get("volume", 0)),
        })
    
    return {
        "index_code": index_code,
        "period": period,
        "count": len(data),
        "data": data,
    }
