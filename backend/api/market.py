# -*- coding: utf-8 -*-
"""
Market API - 行情看板接口

功能：
1. 四大指数实时数据
2. 市场情绪指标（涨跌比、涨停跌停数）
3. 热点板块 TOP10
4. 涨停梯队

降级策略：
- 优先使用东方财富网络接口（实时数据）
- 网络不可用时降级为空列表（不返回 mock 数据）
"""

import sys, os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Query
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

from backend.core.observability import get_obs

router = APIRouter()

# 轻量线程池（用于并发获取板块成分股数量）
_sector_count_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="sector_count")

# 板块成分股数量缓存：{sector_code: (count, cached_at)}
_sector_count_cache: Dict[str, Any] = {}
_SECTOR_COUNT_TTL = 300

# 市场情绪 / 热点板块 fallback 缓存
_sentiment_cache: Optional[Dict[str, Any]] = None
_sentiment_cache_time: Optional[datetime] = None
_hotspots_cache: Optional[List[Dict[str, Any]]] = None
_hotspots_cache_time: Optional[datetime] = None
_HOTSPOTS_CACHE_TTL = 300

# 四大指数代码
INDEX_CODES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
}


# ───────────────────────────────────────────────
# 数据源接口
# ───────────────────────────────────────────────

def _get_data_platform():
    """获取数据中台实例（带缓存）"""
    try:
        from backend.services.data_platform import get_data_platform_service
    except ImportError:
        from services.data_platform import get_data_platform_service
    return get_data_platform_service()


def _fetch_index_quotes() -> List[Dict[str, Any]]:
    """获取四大指数实时行情（5分钟缓存）"""
    platform = _get_data_platform()
    codes = list(INDEX_CODES.keys())
    quotes = platform.get_index_quotes(codes)
    result = []
    for q in quotes:
        result.append({
            "symbol": q.symbol,
            "name": INDEX_CODES.get(q.symbol, q.name or q.symbol),
            "timestamp": q.timestamp.isoformat() if q.timestamp else datetime.now().isoformat(),
            "open": q.open,
            "high": q.high,
            "low": q.low,
            "close": q.close,
            "volume": q.volume,
            "amount": q.amount,
            "change": q.close - q.open,
            "change_pct": ((q.close - q.open) / q.open * 100) if q.open else 0,
        })
    return result


def _fetch_market_sentiment() -> Dict[str, Any]:
    """
    获取市场情绪数据（5分钟缓存）
    数据来源：优先 mootdx Quotes 实时接口，失败时降级到东方财富全市场快照 + 涨跌停统计。
    """
    global _sentiment_cache, _sentiment_cache_time
    now = datetime.now()
    if _sentiment_cache is not None and _sentiment_cache_time is not None:
        if (now - _sentiment_cache_time).total_seconds() < _HOTSPOTS_CACHE_TTL:
            return _sentiment_cache

    # 1. 优先 mootdx 全市场概览
    try:
        platform = _get_data_platform()
        overview = platform.get_market_overview()
        if overview is not None and overview.get("total_valid", 0) > 0:
            result = {
                "up_down_ratio": overview.get("up_down_ratio"),
                "limit_up": overview.get("limit_up"),
                "limit_down": overview.get("limit_down"),
                "advancing": overview.get("advancing"),
                "declining": overview.get("declining"),
                "source": "mootdx",
            }
            _sentiment_cache = result
            _sentiment_cache_time = now
            return result
    except Exception as e:
        get_obs().log("WARN", f"mootdx market overview failed: {e}", "MarketAPI")

    # 2. 降级：东方财富全市场快照 + 涨跌停
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from utils.data_fetcher import fetch_stock_list, fetch_limit_up_down

        stock_df = fetch_stock_list()
        advancing, declining = 0, 0
        up_down_ratio = None
        if stock_df is not None and len(stock_df) > 0:
            advancing = int((stock_df["change_pct"] > 0).sum())
            declining = int((stock_df["change_pct"] < 0).sum())
            if declining > 0:
                up_down_ratio = round(advancing / declining, 2)

        limit_df = fetch_limit_up_down(datetime.now().strftime("%Y-%m-%d"))
        limit_up, limit_down = 0, 0
        if limit_df is not None and len(limit_df) > 0 and "limit_type" in limit_df.columns:
            limit_up = int((limit_df["limit_type"] == "U").sum())
            limit_down = int((limit_df["limit_type"] == "D").sum())

        result = {
            "up_down_ratio": up_down_ratio,
            "limit_up": limit_up if limit_up > 0 else None,
            "limit_down": limit_down if limit_down > 0 else None,
            "advancing": advancing if advancing > 0 else None,
            "declining": declining if declining > 0 else None,
            "source": "eastmoney",
        }
        _sentiment_cache = result
        _sentiment_cache_time = now
        return result
    except Exception as e:
        get_obs().log("WARN", f"eastmoney sentiment fallback failed: {e}", "MarketAPI")

    # 3. 彻底不可用
    result = {
        "up_down_ratio": None,
        "limit_up": None,
        "limit_down": None,
        "advancing": None,
        "declining": None,
        "source": "unavailable",
    }
    _sentiment_cache = result
    _sentiment_cache_time = now
    return result


def _fetch_hotspots() -> List[Dict[str, Any]]:
    """
    获取热点板块 TOP10（5分钟缓存）
    数据来源：优先 mootdx Quotes 实时接口；失败时降级到东方财富板块涨幅榜。
    """
    global _hotspots_cache, _hotspots_cache_time
    now = datetime.now()
    if _hotspots_cache is not None and _hotspots_cache_time is not None:
        if (now - _hotspots_cache_time).total_seconds() < _HOTSPOTS_CACHE_TTL:
            return _hotspots_cache

    # 1. 优先 mootdx
    try:
        platform = _get_data_platform()
        hotspots = platform.get_hotspots()
        if hotspots:
            result = [
                {
                    "block_code": "",
                    "block_name": h["block_name"],
                    "change_pct": h["change_pct"],
                    "volume_ratio": 1.0,
                    "money_flow": 0.0,
                    "rank": i + 1,
                    "stock_count": h.get("stock_count", 0),
                    "up_count": h.get("up_count", 0),
                    "limit_up_count": 0,
                }
                for i, h in enumerate(hotspots)
            ]
            _hotspots_cache = result
            _hotspots_cache_time = now
            return result
    except Exception as e:
        get_obs().log("WARN", f"mootdx hotspots failed: {e}", "MarketAPI")

    # 2. 降级：东方财富板块涨幅榜
    try:
        network_sectors = _fetch_sector_list_from_network()
        if network_sectors is not None and len(network_sectors) > 0:
            df = network_sectors.sort_values("change_pct", ascending=False).head(10)
            codes = df["sector_code"].astype(str).tolist()
            count_map = _get_sector_component_counts(codes)
            result = []
            for i, (_, row) in enumerate(df.iterrows()):
                code = str(row.get("sector_code", ""))
                result.append({
                    "block_code": code,
                    "block_name": row.get("sector_name", ""),
                    "change_pct": round(row.get("change_pct", 0), 2),
                    "volume_ratio": 1.0,
                    "money_flow": round(row.get("amount", 0), 2),
                    "rank": i + 1,
                    "stock_count": count_map.get(code, 0),
                    "up_count": 0,
                    "limit_up_count": 0,
                })
            _hotspots_cache = result
            _hotspots_cache_time = now
            return result
    except Exception as e:
        get_obs().log("WARN", f"eastmoney hotspots fallback failed: {e}", "MarketAPI")

    _hotspots_cache = []
    _hotspots_cache_time = now
    return []


def _fetch_limit_up_ladder() -> List[Dict[str, Any]]:
    """
    获取涨停梯队
    
    尝试东方财富接口，失败时降级为空列表（不返回 mock 数据）。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from utils.data_fetcher import fetch_limit_up_down
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        df = fetch_limit_up_down(date_str)
        if df is not None and len(df) > 0:
            # 只取涨停（limit_type == 'U'）
            df = df[df["limit_type"] == "U"].sort_values("ud_rate", ascending=False).head(20)
            return [
                {
                    "code": row["code"],
                    "name": row["name"],
                    "close": row["close"],
                    "board_amount": round(row.get("board_amount", 0), 2),
                    "board_ratio": round(row.get("board_ratio", 0), 2),
                    "open_times": int(row.get("open_times", 0)),
                    "first_time": row.get("first_time", ""),
                    "last_time": row.get("last_time", ""),
                    "consecutive_days": 1,
                }
                for _, row in df.iterrows()
            ]
    except Exception:
        pass
    
    # 降级：不返回 mock 数据，返回空列表
    return []


# ───────────────────────────────────────────────
# API 路由
# ───────────────────────────────────────────────

@router.get("/market/indices")
async def market_indices():
    """四大指数实时数据"""
    indices = _fetch_index_quotes()
    return {
        "count": len(indices),
        "indices": indices,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/market/sentiment")
async def market_sentiment():
    """市场情绪指标"""
    sentiment = _fetch_market_sentiment()
    return {
        **sentiment,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/market/hotspots")
async def market_hotspots(limit: int = Query(10, ge=1, le=50)):
    """热点板块 TOP N"""
    hotspots = _fetch_hotspots()
    _limit = int(limit) if isinstance(limit, (int, float, str)) else 10
    return {
        "count": len(hotspots),
        "hotspots": hotspots[:_limit],
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/market/limit-up")
async def market_limit_up(limit: int = Query(20, ge=1, le=100)):
    """涨停梯队"""
    ladder = _fetch_limit_up_ladder()
    _limit = int(limit) if isinstance(limit, (int, float, str)) else 20
    return {
        "count": len(ladder),
        "ladder": ladder[:_limit],
        "timestamp": datetime.now().isoformat(),
    }


# ───────────────────────────────────────────────
# 板块 / 行业数据
# ───────────────────────────────────────────────

# 预定义主要板块（申万一级 + 热门概念）
PREDEFINED_SECTORS = [
    {"code": "sw801120", "name": "食品饮料", "type": "industry", "level": "一级"},
    {"code": "sw801110", "name": "家用电器", "type": "industry", "level": "一级"},
    {"code": "sw801150", "name": "医药生物", "type": "industry", "level": "一级"},
    {"code": "sw801080", "name": "电子", "type": "industry", "level": "一级"},
    {"code": "sw801750", "name": "计算机", "type": "industry", "level": "一级"},
    {"code": "sw801770", "name": "通信", "type": "industry", "level": "一级"},
    {"code": "sw801880", "name": "汽车", "type": "industry", "level": "一级"},
    {"code": "sw801030", "name": "化工", "type": "industry", "level": "一级"},
    {"code": "sw801730", "name": "电力设备", "type": "industry", "level": "一级"},
    {"code": "sw801890", "name": "机械设备", "type": "industry", "level": "一级"},
    {"code": "sw801710", "name": "建筑材料", "type": "industry", "level": "一级"},
    {"code": "sw801720", "name": "建筑装饰", "type": "industry", "level": "一级"},
    {"code": "sw801170", "name": "纺织服装", "type": "industry", "level": "一级"},
    {"code": "sw801010", "name": "农林牧渔", "type": "industry", "level": "一级"},
    {"code": "sw801790", "name": "非银金融", "type": "industry", "level": "一级"},
    {"code": "sw801780", "name": "银行", "type": "industry", "level": "一级"},
    {"code": "sw801210", "name": "社会服务", "type": "industry", "level": "一级"},
    {"code": "sw801140", "name": "轻工制造", "type": "industry", "level": "一级"},
    {"code": "sw801200", "name": "商贸零售", "type": "industry", "level": "一级"},
    {"code": "sw801130", "name": "纺织服饰", "type": "industry", "level": "一级"},
    {"code": "sw801160", "name": "公用事业", "type": "industry", "level": "一级"},
    {"code": "sw801050", "name": "有色金属", "type": "industry", "level": "一级"},
    {"code": "sw801040", "name": "钢铁", "type": "industry", "level": "一级"},
    {"code": "sw801950", "name": "煤炭", "type": "industry", "level": "一级"},
    {"code": "sw801960", "name": "石油石化", "type": "industry", "level": "一级"},
    {"code": "sw801970", "name": "环保", "type": "industry", "level": "一级"},
    {"code": "sw801980", "name": "美容护理", "type": "industry", "level": "一级"},
    {"code": "sw801990", "name": "综合", "type": "industry", "level": "一级"},
    {"code": "gn-ai", "name": "人工智能", "type": "concept", "level": "概念"},
    {"code": "gn-xny", "name": "新能源", "type": "concept", "level": "概念"},
    {"code": "gn-bdt", "name": "半导体", "type": "concept", "level": "概念"},
    {"code": "gn-xfc", "name": "新能车", "type": "concept", "level": "概念"},
    {"code": "gn-yy", "name": "创新药", "type": "concept", "level": "概念"},
    {"code": "gn-jg", "name": "军工", "type": "concept", "level": "概念"},
    {"code": "gn-zgb", "name": "中特估", "type": "concept", "level": "概念"},
    {"code": "gn-dc", "name": "房地产", "type": "concept", "level": "概念"},
]


# 板块数据缓存（5分钟）
_sector_cache: Optional[pd.DataFrame] = None
_sector_cache_time: Optional[datetime] = None
_SECTOR_CACHE_TTL = 300


def _fetch_sector_list_from_network() -> Optional[pd.DataFrame]:
    """从网络获取板块列表（东方财富）"""
    global _sector_cache, _sector_cache_time
    now = datetime.now()
    if _sector_cache is not None and _sector_cache_time is not None:
        if (now - _sector_cache_time).total_seconds() < _SECTOR_CACHE_TTL:
            return _sector_cache
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from utils.data_fetcher import fetch_sector_list
        df = fetch_sector_list()
        if df is not None and len(df) > 0:
            _sector_cache = df
            _sector_cache_time = now
            return df
    except Exception:
        pass
    return None


def _fetch_sector_components_from_network(sector_code: str) -> Optional[pd.DataFrame]:
    """从网络获取板块成分股（东方财富）"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from utils.data_fetcher import fetch_sector_components
        df = fetch_sector_components(sector_code)
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass
    return None


def _get_sector_component_count(sector_code: str) -> int:
    """获取板块成分股数量，带 5 分钟缓存"""
    now = datetime.now()
    cached = _sector_count_cache.get(sector_code)
    if cached is not None:
        count, cached_at = cached
        if (now - cached_at).total_seconds() < _SECTOR_COUNT_TTL:
            return count
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from utils.data_fetcher import em_fetch_sector_component_count
        count = em_fetch_sector_component_count(sector_code)
    except Exception:
        count = 0
    _sector_count_cache[sector_code] = (count, now)
    return count


def _get_sector_component_counts(sector_codes: List[str]) -> Dict[str, int]:
    """并发获取多个板块的成分股数量"""
    if not sector_codes:
        return {}
    results = list(_sector_count_executor.map(_get_sector_component_count, sector_codes))
    return {code: count for code, count in zip(sector_codes, results)}


def _read_local_blocks() -> Dict[str, List[str]]:
    """读取本地通达信板块文件"""
    blocks = {}
    tdx_dir = os.environ.get("TDX_DIR", "D:/TDX")
    block_dir = os.path.join(tdx_dir, "T0002", "blocknew")
    if not os.path.exists(block_dir):
        return blocks
    for fname in os.listdir(block_dir):
        if fname.endswith(".blk"):
            fpath = os.path.join(block_dir, fname)
            try:
                with open(fpath, "r", encoding="gbk", errors="ignore") as f:
                    codes = [line.strip() for line in f.readlines() if line.strip()]
                sector_name = fname.replace(".blk", "")
                blocks[sector_name] = codes
            except Exception:
                pass
    return blocks


@router.get("/market/sectors")
async def market_sectors(
    type_filter: Optional[str] = Query(None, enum=["industry", "concept"], description="筛选类型"),
):
    """
    获取行业板块 / 概念板块列表

    优先从东方财富网络获取真实板块数据，失败时降级到预定义列表。
    """
    # 1. 优先尝试网络获取
    network_sectors = _fetch_sector_list_from_network()
    if network_sectors is not None and len(network_sectors) > 0:
        sector_codes = network_sectors["sector_code"].astype(str).tolist()
        count_map = _get_sector_component_counts(sector_codes)
        sectors = []
        for _, row in network_sectors.iterrows():
            code = str(row.get("sector_code", ""))
            sectors.append({
                "code": code,
                "name": row.get("sector_name", ""),
                "type": "industry",
                "level": "一级",
                "change_pct": round(row.get("change_pct", 0), 2),
                "stock_count": count_map.get(code, 0),
                "stocks": [],
            })
        return {
            "count": len(sectors),
            "sectors": sectors,
            "timestamp": datetime.now().isoformat(),
            "source": "eastmoney",
        }
    
    # 2. 降级：预定义列表
    local_blocks = _read_local_blocks()
    sectors = []
    for s in PREDEFINED_SECTORS:
        if type_filter and s["type"] != type_filter:
            continue
        # 尝试关联本地成分股
        stocks = []
        for block_name, codes in local_blocks.items():
            if block_name in s["name"] or s["name"] in block_name:
                stocks = [{"code": c, "name": ""} for c in codes if c]
                break
        sectors.append({
            "code": s["code"],
            "name": s["name"],
            "type": s["type"],
            "level": s["level"],
            "stock_count": len(stocks),
            "stocks": stocks[:50],  # 最多返回50只
        })
    return {
        "count": len(sectors),
        "sectors": sectors,
        "timestamp": datetime.now().isoformat(),
        "source": "predefined",
    }


@router.get("/market/sector/{sector_name}")
async def market_sector_detail(
    sector_name: str,
    limit: int = Query(50, ge=1, le=200),
):
    """
    获取板块详情及成分股涨跌幅

    优先从东方财富网络获取成分股，失败时降级到本地通达信板块文件。
    """
    # 1. 尝试从网络获取成分股
    # 先查找 sector_code：从缓存或预定义列表匹配
    sector_code = None
    network_sectors = _fetch_sector_list_from_network()
    if network_sectors is not None and len(network_sectors) > 0:
        match = network_sectors[network_sectors["sector_name"] == sector_name]
        if len(match) > 0:
            sector_code = match.iloc[0].get("sector_code", "")
    
    if not sector_code:
        for s in PREDEFINED_SECTORS:
            if s["name"] == sector_name or s["code"] == sector_name:
                sector_code = s["code"]
                break
    
    stocks = []
    if sector_code:
        comp_df = _fetch_sector_components_from_network(sector_code)
        if comp_df is not None and len(comp_df) > 0:
            comp_df = comp_df.head(limit)
            for _, row in comp_df.iterrows():
                stocks.append({
                    "code": row.get("code", ""),
                    "name": row.get("name", ""),
                    "price": round(row.get("close", 0), 2),
                    "change_pct": round(row.get("change_pct", 0), 2),
                    "volume": 0,
                })
            return {
                "sector_name": sector_name,
                "sector_code": sector_code,
                "stock_count": len(stocks),
                "stocks": stocks,
                "timestamp": datetime.now().isoformat(),
                "source": "eastmoney",
            }
    
    # 2. 降级：本地通达信板块文件
    local_blocks = _read_local_blocks()
    codes = []
    for block_name, block_codes in local_blocks.items():
        if block_name == sector_name or block_name in sector_name or sector_name in block_name:
            codes = block_codes
            break
    
    # 获取实时行情计算涨跌幅
    if codes:
        try:
            from backend.services.data_provider import get_data_provider_service
            dp = get_data_provider_service()
            quotes = dp.fetch_realtime_quotes(codes[:limit])
            quote_map = {q.symbol: q for q in quotes}
            for c in codes[:limit]:
                q = quote_map.get(c)
                if q:
                    change_pct = ((q.close - q.open) / q.open * 100) if q.open else 0
                    stocks.append({
                        "code": c,
                        "name": q.name or "",
                        "price": round(q.close, 2),
                        "change_pct": round(change_pct, 2),
                        "volume": q.volume,
                    })
                else:
                    stocks.append({"code": c, "name": "", "price": 0, "change_pct": 0, "volume": 0})
        except Exception:
            stocks = [{"code": c, "name": "", "price": 0, "change_pct": 0, "volume": 0} for c in codes[:limit]]
    
    return {
        "sector_name": sector_name,
        "stock_count": len(stocks),
        "stocks": stocks,
        "timestamp": datetime.now().isoformat(),
        "source": "local" if codes else "empty",
    }
