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
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Query
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

from backend.core.observability import get_obs

try:
    from backend.services.guosen.client import GuosenClient, GuosenSkillError
except ImportError:
    from services.guosen.client import GuosenClient, GuosenSkillError

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
_SENTIMENT_CACHE_TTL = 300
_HOTSPOTS_CACHE_TTL = 300

# 四大指数缓存（60秒）
_index_quotes_cache: Optional[List[Dict[str, Any]]] = None
_index_quotes_cache_time: Optional[datetime] = None
_INDEX_QUOTES_CACHE_TTL = 60

# 板块网络可用性探测缓存
_sector_network_available: Optional[bool] = None
_sector_network_probe_time: Optional[datetime] = None
_SECTOR_NETWORK_PROBE_TTL = 60

# 国信 skill 客户端（延迟初始化）
_guosen_client: Optional[GuosenClient] = None

# 四大指数代码
INDEX_CODES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
}

# 内置默认板块成分股数量（当网络/akshare 均不可用时兜底，避免全部返回 0）
_DEFAULT_SECTOR_COUNTS = {
    "BK0477": 37, "BK0478": 42, "BK0479": 46, "BK0480": 51,
    "BK0481": 95, "BK0482": 110, "BK0483": 380, "BK0484": 60,
    "BK0485": 130, "BK0486": 60, "BK0487": 280, "BK0488": 120,
    "BK0489": 130, "BK0490": 260, "BK0491": 260, "BK0492": 130,
    "BK0493": 170, "BK0494": 80, "BK0495": 90, "BK0496": 40,
    "BK0497": 180, "BK0498": 120, "BK0499": 120, "BK0500": 120,
    "BK0501": 80, "BK0502": 90, "BK0503": 50, "BK0504": 90,
    "BK0505": 45, "BK0506": 70, "BK0507": 80, "BK0508": 60,
    "BK0509": 120, "BK0510": 70, "BK0511": 50, "BK0512": 30,
    "BK0513": 20, "BK0514": 50, "BK0515": 30, "BK0516": 60,
    "BK0517": 110, "BK0518": 25, "BK0519": 40, "BK0520": 35,
    "BK0521": 40, "BK0522": 15, "BK0523": 45, "BK0524": 40,
    "BK0525": 50, "BK0526": 40, "BK0527": 30, "BK0528": 80,
    "BK0529": 35, "BK0530": 60, "BK0531": 90, "BK0532": 95,
}

# 预定义板块近似成分股数量（网络不可用时兜底，数值为经验近似，仅作展示参考）
_APPROX_SECTOR_COUNTS = {
    # 申万一级（按常见规模估算）
    "sw801120": 130, "食品饮料": 130,
    "sw801110": 90, "家用电器": 90,
    "sw801150": 470, "医药生物": 470,
    "sw801080": 450, "电子": 450,
    "sw801750": 330, "计算机": 330,
    "sw801770": 130, "通信": 130,
    "sw801880": 260, "汽车": 260,
    "sw801030": 370, "化工": 370,
    "sw801730": 360, "电力设备": 360,
    "sw801890": 530, "机械设备": 530,
    "sw801710": 90, "建筑材料": 90,
    "sw801720": 170, "建筑装饰": 170,
    "sw801170": 110, "纺织服装": 110,
    "sw801010": 110, "农林牧渔": 110,
    "sw801790": 80, "非银金融": 80,
    "sw801780": 40, "银行": 40,
    "sw801210": 100, "社会服务": 100,
    "sw801140": 140, "轻工制造": 140,
    "sw801200": 160, "商贸零售": 160,
    "sw801130": 90, "纺织服饰": 90,
    "sw801160": 170, "公用事业": 170,
    "sw801050": 130, "有色金属": 130,
    "sw801040": 40, "钢铁": 40,
    "sw801950": 40, "煤炭": 40,
    "sw801960": 50, "石油石化": 50,
    "sw801970": 120, "环保": 120,
    "sw801980": 30, "美容护理": 30,
    "sw801990": 40, "综合": 40,
    # 热门概念
    "gn-ai": 200, "人工智能": 200,
    "gn-xny": 250, "新能源": 250,
    "gn-bdt": 200, "半导体": 200,
    "gn-xfc": 200, "新能车": 200,
    "gn-yy": 150, "创新药": 150,
    "gn-jg": 150, "军工": 150,
    "gn-zgb": 100, "中特估": 100,
    "gn-dc": 110, "房地产": 110,
}


def _approx_sector_count(code: str, name: str = "") -> int:
    """获取板块近似成分股数量（网络完全不可用时兜底）"""
    if code:
        count = _APPROX_SECTOR_COUNTS.get(code)
        if count:
            return count
        # 兼容纯数字申万代码（如 801120）
        count = _APPROX_SECTOR_COUNTS.get(f"sw{code}")
        if count:
            return count
    if name:
        count = _APPROX_SECTOR_COUNTS.get(name)
        if count:
            return count
    return 0


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


def _get_latest_trading_day() -> Optional[str]:
    """获取最新交易日（以上证指数离线K线最后日期为准）"""
    try:
        from backend.services.data_provider import get_data_provider_service
        df = get_data_provider_service().fetch_ohlcv(
            "sh000001", period="daily", adjust="none", source="offline"
        )
        if df is not None and len(df) > 0:
            return str(df.iloc[-1].get("date", ""))
    except Exception:
        pass
    return None


def _sanitize_msg(text: str) -> str:
    """清除日志/异常中的 API Key 等敏感信息"""
    if not text:
        return text
    text = re.sub(r"apiKey=[^\s&\"']+", "apiKey=***", text, flags=re.IGNORECASE)
    text = re.sub(r"V2V-[A-Za-z0-9_-]{50,}", "V2V-***", text)
    return text


def _get_guosen_client() -> Optional[GuosenClient]:
    """延迟初始化国信客户端；未配置 key 或缺少 skill 时返回 None"""
    global _guosen_client
    if _guosen_client is not None:
        return _guosen_client
    if not os.environ.get("GS_API_KEY"):
        return None
    try:
        _guosen_client = GuosenClient()
        return _guosen_client
    except Exception as e:
        get_obs().log("WARN", f"Guosen client init failed: {_sanitize_msg(str(e))}", "MarketAPI")
        return None


def _parse_pct(value: Any) -> Optional[float]:
    """将字符串/数字安全转换为浮点百分比"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _infer_set_code(code: str) -> int:
    """根据代码前缀推断证券市场代码（0深圳，1上海，2北交所）"""
    code = str(code)
    if code.startswith("6"):
        return 1
    if code.startswith(("0", "3")):
        return 0
    if code.startswith(("4", "8", "9")):
        return 2
    return 0


def _extract_data_list(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """提取国信接口返回中的 data 列表（兼容 result 为 dict 或 list 的错误响应）"""
    if not resp or not isinstance(resp, dict):
        return []
    result = resp.get("result")
    if isinstance(result, list) and result:
        result = result[0]
    if not isinstance(result, dict) or result.get("code") != 0:
        return []
    data = resp.get("data")
    return data if isinstance(data, list) else []


def _is_limit_up(item: Dict[str, Any]) -> bool:
    """根据涨跌幅判断是否为涨停（区分 10%/20%/30% 板块）"""
    pct = _parse_pct(item.get("priceChangePct"))
    if pct is None:
        return False
    code = str(item.get("code", ""))
    if code.startswith(("30", "68")):
        return pct >= 19.85
    if code.startswith(("4", "8", "9")):
        return pct >= 29.0
    return pct >= 9.85


def _is_limit_down(item: Dict[str, Any]) -> bool:
    """根据涨跌幅判断是否为跌停"""
    pct = _parse_pct(item.get("priceChangePct"))
    if pct is None:
        return False
    code = str(item.get("code", ""))
    if code.startswith(("30", "68")):
        return pct <= -19.85
    if code.startswith(("4", "8", "9")):
        return pct <= -29.0
    return pct <= -9.85


def _fetch_guosen_sentiment() -> Dict[str, Any]:
    """
    通过国信 query_multi_hq 获取涨跌停家数。
    由于接口只返回前 N 名，涨跌家数仍依赖 mootdx/eastmoney。
    """
    client = _get_guosen_client()
    if not client:
        return {}
    try:
        gainers = client.query_multi_hq(set_domain=6, want_num=80, sort_type=1)
        decliners = client.query_multi_hq(set_domain=6, want_num=80, sort_type=2)
        up_list = _extract_data_list(gainers)
        down_list = _extract_data_list(decliners)
        return {
            "limit_up": sum(1 for i in up_list if _is_limit_up(i)),
            "limit_down": sum(1 for i in down_list if _is_limit_down(i)),
        }
    except Exception as e:
        get_obs().log("WARN", f"Guosen sentiment failed: {_sanitize_msg(str(e))}", "MarketAPI")
        return {}


def _fetch_index_quotes() -> List[Dict[str, Any]]:
    """获取四大指数实时行情（60秒缓存）"""
    global _index_quotes_cache, _index_quotes_cache_time
    now = datetime.now()
    if _index_quotes_cache is not None and _index_quotes_cache_time is not None:
        if (now - _index_quotes_cache_time).total_seconds() < _INDEX_QUOTES_CACHE_TTL:
            return _index_quotes_cache

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
    _index_quotes_cache = result
    _index_quotes_cache_time = now
    return result


def _fetch_market_sentiment() -> Dict[str, Any]:
    """
    获取市场情绪数据（5分钟缓存）
    数据来源：优先 mootdx Quotes 实时接口，失败时降级到东方财富全市场快照 + 涨跌停统计。
    国信 skill 作为并行补充，用于在 mootdx/eastmoney 不可用时提供涨跌停家数。
    """
    global _sentiment_cache, _sentiment_cache_time
    now = datetime.now()
    if _sentiment_cache is not None and _sentiment_cache_time is not None:
        if (now - _sentiment_cache_time).total_seconds() < _SENTIMENT_CACHE_TTL:
            return _sentiment_cache

    data_date = _get_latest_trading_day()
    guosen_extra = _fetch_guosen_sentiment()

    def _merge_guosen(target: Dict[str, Any]) -> None:
        """当主数据源未返回涨跌停家数时，用国信数据补全"""
        if target.get("limit_up") in (None, 0) and guosen_extra.get("limit_up"):
            target["limit_up"] = guosen_extra["limit_up"]
        if target.get("limit_down") in (None, 0) and guosen_extra.get("limit_down"):
            target["limit_down"] = guosen_extra["limit_down"]

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
                "data_date": data_date,
                "source": "mootdx",
            }
            _merge_guosen(result)
            _sentiment_cache = result
            _sentiment_cache_time = now
            return result
    except Exception as e:
        get_obs().log("WARN", f"mootdx market overview failed: {type(e).__name__}", "MarketAPI")

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
            "data_date": data_date,
            "source": "eastmoney",
        }
        _merge_guosen(result)
        _sentiment_cache = result
        _sentiment_cache_time = now
        return result
    except Exception as e:
        get_obs().log("WARN", f"eastmoney sentiment fallback failed: {type(e).__name__}", "MarketAPI")

    # 3. 彻底不可用：如有历史缓存，返回缓存数据避免面板空白
    if _sentiment_cache is not None and _sentiment_cache.get("source") not in (None, "unavailable"):
        cached = dict(_sentiment_cache)
        cached["source"] = "cache"
        cached["data_date"] = data_date
        _merge_guosen(cached)
        return cached

    result = {
        "up_down_ratio": None,
        "limit_up": guosen_extra.get("limit_up"),
        "limit_down": guosen_extra.get("limit_down"),
        "advancing": None,
        "declining": None,
        "data_date": data_date,
        "source": "guosen" if guosen_extra else "unavailable",
    }
    _sentiment_cache = result
    _sentiment_cache_time = now
    return result


def _is_valid_hotspots_result(result: List[Dict[str, Any]]) -> bool:
    """判断热点板块结果是否有效（至少存在非零涨幅或资金流向）"""
    if not result:
        return False
    return any(
        abs(h.get("change_pct", 0) or 0) > 0.0001 or (h.get("money_flow") and h.get("money_flow") > 0)
        for h in result
    )


def _default_hotspots() -> List[Dict[str, Any]]:
    """网络不可用时返回的市场层热点兜底，确保首屏快速有数据"""
    return [
        {"block_code": "", "block_name": "科创板", "change_pct": 0, "volume_ratio": None, "money_flow": 0.0, "rank": 1, "stock_count": 414, "up_count": 0, "limit_up_count": 0},
        {"block_code": "", "block_name": "上海主板", "change_pct": 0, "volume_ratio": None, "money_flow": 0.0, "rank": 2, "stock_count": 1357, "up_count": 0, "limit_up_count": 0},
        {"block_code": "", "block_name": "深圳主板", "change_pct": 0, "volume_ratio": None, "money_flow": 0.0, "rank": 3, "stock_count": 1235, "up_count": 0, "limit_up_count": 0},
        {"block_code": "", "block_name": "创业板", "change_pct": 0, "volume_ratio": None, "money_flow": 0.0, "rank": 4, "stock_count": 1100, "up_count": 0, "limit_up_count": 0},
    ]


def _guosen_related_boards(stock_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """查询单只股票的关联板块（供热点聚合使用）"""
    client = _get_guosen_client()
    if not client:
        return []
    code = str(stock_item.get("code", ""))
    if not code:
        return []
    set_code = _infer_set_code(code)
    try:
        resp = client.query_related_comb_hq(code, set_code, max_retries=1, timeout=10)
        return _extract_data_list(resp)
    except Exception as e:
        get_obs().log("WARN", f"Guosen related_comb {code} failed: {_sanitize_msg(str(e))}", "MarketAPI")
        return []


def _fetch_guosen_hotspots() -> Optional[List[Dict[str, Any]]]:
    """
    通过国信涨幅榜 + 个股关联板块聚合热点板块 TOP10。
    不返回兜底，失败时返回 None 让上层继续走 eastmoney/mootdx fallback。
    """
    client = _get_guosen_client()
    if not client:
        return None
    try:
        resp = client.query_multi_hq(set_domain=6, want_num=20, sort_type=1, max_retries=2, timeout=15)
        gainers = _extract_data_list(resp)[:5]
        if not gainers:
            return None

        boards_map: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=5, thread_name_prefix="guosen_hotspot") as ex:
            futures = {ex.submit(_guosen_related_boards, s): s for s in gainers}
            for fut in futures:
                try:
                    boards = fut.result(timeout=10)
                except Exception:
                    boards = []
                for b in boards:
                    bcode = str(b.get("code", ""))
                    if not bcode:
                        continue
                    existing = boards_map.get(bcode)
                    if existing is None:
                        boards_map[bcode] = b
                    else:
                        cur = abs(_parse_pct(b.get("priceChangePct")) or 0)
                        old = abs(_parse_pct(existing.get("priceChangePct")) or 0)
                        if cur > old:
                            boards_map[bcode] = b

        if not boards_map:
            return None

        sorted_boards = sorted(
            boards_map.values(),
            key=lambda x: _parse_pct(x.get("priceChangePct")) or -9999,
            reverse=True,
        )[:10]
        codes = [b.get("code") for b in sorted_boards]
        count_map = _get_sector_component_counts(codes)
        result = []
        for i, b in enumerate(sorted_boards):
            result.append({
                "block_code": b.get("code", ""),
                "block_name": b.get("name", ""),
                "change_pct": round(_parse_pct(b.get("priceChangePct")) or 0, 2),
                "volume_ratio": None,
                "money_flow": 0.0,
                "rank": i + 1,
                "stock_count": count_map.get(b.get("code"), 0),
                "up_count": 0,
                "limit_up_count": 0,
            })
        return result if _is_valid_hotspots_result(result) else None
    except Exception as e:
        get_obs().log("WARN", f"Guosen hotspots failed: {_sanitize_msg(str(e))}", "MarketAPI")
        return None


def _fetch_hotspots_real() -> List[Dict[str, Any]]:
    """尝试获取真实热点数据（网络 + mootdx），不返回兜底"""
    now = datetime.now()

    # 1. 优先国信：通过领涨股关联板块聚合热点
    try:
        guosen_hotspots = _fetch_guosen_hotspots()
        if guosen_hotspots:
            return guosen_hotspots
    except Exception as e:
        get_obs().log("WARN", f"Guosen hotspots path failed: {_sanitize_msg(str(e))}", "MarketAPI")

    # 2. 东方财富真实板块涨幅榜
    try:
        network_sectors = _fetch_sector_list_from_network()
        if network_sectors is not None and len(network_sectors) > 0:
            df = network_sectors.sort_values("change_pct", ascending=False).head(10)
            codes = df["sector_code"].astype(str).tolist()
            count_map = _get_sector_component_counts(codes)
            up_count_map = _get_sector_up_counts(codes)
            codes_volumes = [
                (code, float(row.get("volume", 0)) if pd.notna(row.get("volume")) else 0.0)
                for code, row in zip(codes, [r for _, r in df.iterrows()])
            ]
            volume_ratio_map = _get_sector_volume_ratios(codes_volumes)
            result = []
            for i, (_, row) in enumerate(df.iterrows()):
                code = str(row.get("sector_code", ""))
                volume_ratio = volume_ratio_map.get(code)
                result.append({
                    "block_code": code,
                    "block_name": row.get("sector_name", ""),
                    "change_pct": round(row.get("change_pct", 0), 2),
                    "volume_ratio": volume_ratio if volume_ratio is not None else 1.0,
                    "money_flow": round(row.get("amount", 0), 2),
                    "rank": i + 1,
                    "stock_count": count_map.get(code, 0),
                    "up_count": up_count_map.get(code, 0),
                    "limit_up_count": 0,
                })
            if _is_valid_hotspots_result(result):
                return result
    except Exception as e:
        get_obs().log("WARN", f"eastmoney hotspots failed: {type(e).__name__}", "MarketAPI")

    # 3. 降级：mootdx 交易所层面数据（带 1.5 秒超时）
    try:
        platform = _get_data_platform()
        future = _sector_count_executor.submit(platform.get_hotspots)
        hotspots = future.result(timeout=1.5)
        if hotspots:
            return [
                {
                    "block_code": "",
                    "block_name": h["block_name"],
                    "change_pct": h["change_pct"],
                    "volume_ratio": None,
                    "money_flow": 0.0,
                    "rank": i + 1,
                    "stock_count": h.get("stock_count", 0),
                    "up_count": h.get("up_count", 0),
                    "limit_up_count": 0,
                }
                for i, h in enumerate(hotspots)
            ]
    except Exception as e:
        get_obs().log("WARN", f"mootdx hotspots fallback failed: {type(e).__name__}", "MarketAPI")

    return []


def _fetch_hotspots() -> List[Dict[str, Any]]:
    """
    获取热点板块 TOP10（5分钟缓存）
    首屏优先快速返回兜底数据，后台异步刷新真实数据，避免响应超时。
    """
    global _hotspots_cache, _hotspots_cache_time
    now = datetime.now()
    if _hotspots_cache is not None and _hotspots_cache_time is not None:
        if (now - _hotspots_cache_time).total_seconds() < _HOTSPOTS_CACHE_TTL:
            return _hotspots_cache

    # 缓存为空时：立即返回兜底，后台刷新真实数据
    if _hotspots_cache is None:
        _hotspots_cache = _default_hotspots()
        _hotspots_cache_time = now
        _sector_count_executor.submit(_fetch_hotspots_real)
        return _hotspots_cache

    # 缓存过期：尝试快速刷新，2 秒超时仍用旧数据兜底
    try:
        future = _sector_count_executor.submit(_fetch_hotspots_real)
        result = future.result(timeout=2)
        if result:
            _hotspots_cache = result
            _hotspots_cache_time = now
            return result
    except Exception as e:
        get_obs().log("WARN", f"hotspots refresh timeout: {type(e).__name__}", "MarketAPI")

    _hotspots_cache = _default_hotspots()
    _hotspots_cache_time = now
    return _hotspots_cache


def _fetch_limit_up_ladder() -> List[Dict[str, Any]]:
    """
    获取涨停梯队

    优先使用国信 query_multi_hq 涨幅榜，失败时降级到东方财富接口，
    最后返回空列表（不返回 mock 数据）。
    """
    # 1. 国信：从沪深A股涨幅榜过滤涨停股
    client = _get_guosen_client()
    if client:
        try:
            resp = client.query_multi_hq(set_domain=6, want_num=80, sort_type=1)
            gainers = _extract_data_list(resp)
            ladder = [
                {
                    "code": item.get("code", ""),
                    "name": item.get("name", ""),
                    "close": _parse_pct(item.get("now")) or 0,
                    "board_amount": 0.0,
                    "board_ratio": round(_parse_pct(item.get("priceChangePct")) or 0, 2),
                    "open_times": 0,
                    "first_time": "",
                    "last_time": "",
                    "consecutive_days": 1,
                }
                for item in gainers
                if _is_limit_up(item)
            ]
            if ladder:
                return ladder[:20]
        except Exception as e:
            get_obs().log("WARN", f"Guosen limit-up ladder failed: {_sanitize_msg(str(e))}", "MarketAPI")

    # 2. 降级：东方财富接口
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

    # 3. 不返回 mock 数据
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


def _fetch_sector_list_raw() -> Optional[pd.DataFrame]:
    """无缓存地从网络获取板块列表，内部函数用于带超时调用"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from utils.data_fetcher import fetch_sector_list
        df = fetch_sector_list()
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass
    return None


def _fetch_sector_list_from_network() -> Optional[pd.DataFrame]:
    """从网络获取板块列表（东方财富），带 5 分钟缓存和 1 秒超时"""
    global _sector_cache, _sector_cache_time, _sector_network_available, _sector_network_probe_time
    now = datetime.now()
    if _sector_cache is not None and _sector_cache_time is not None:
        if (now - _sector_cache_time).total_seconds() < _SECTOR_CACHE_TTL:
            return _sector_cache
    try:
        future = _sector_count_executor.submit(_fetch_sector_list_raw)
        df = future.result(timeout=0.5)
        if df is not None and len(df) > 0:
            _sector_cache = df
            _sector_cache_time = now
            _sector_network_available = True
            _sector_network_probe_time = now
            return df
    except Exception:
        pass
    # 列表接口失败，标记板块网络不可用，避免后续 counts 再探测超时
    _sector_network_available = False
    _sector_network_probe_time = now
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
    count = 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from utils.data_fetcher import em_fetch_sector_component_count
        count = em_fetch_sector_component_count(sector_code)
    except Exception:
        count = 0
    # 轻量接口返回 0 时，降级到成分股列表取实际行数
    if count == 0:
        try:
            df = _fetch_sector_components_from_network(sector_code)
            if df is not None and len(df) > 0:
                count = len(df)
        except Exception:
            pass
    # 仍为空时，再尝试 akshare 概念板块成分股
    if count == 0:
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            import akshare as ak
            df = ak.stock_board_concept_cons_em(symbol=sector_code)
            if df is not None and len(df) > 0:
                count = len(df)
        except Exception:
            pass
    # 网络全部不可用时，使用内置默认数量兜底，避免大面积 0
    if count == 0:
        count = _DEFAULT_SECTOR_COUNTS.get(sector_code, 0)
    _sector_count_cache[sector_code] = (count, now)
    return count


def _get_sector_component_count_network(sector_code: str) -> Optional[int]:
    """仅尝试网络获取板块成分股数量（不含 fallback），用于超时探测"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from utils.data_fetcher import em_fetch_sector_component_count
        count = em_fetch_sector_component_count(sector_code)
        if count and count > 0:
            return count
    except Exception:
        pass
    return None


def _probe_sector_network(codes: List[str]) -> bool:
    """探测板块网络接口是否可用，缓存结果 60 秒"""
    global _sector_network_available, _sector_network_probe_time
    now = datetime.now()
    if _sector_network_available is not None and _sector_network_probe_time is not None:
        if (now - _sector_network_probe_time).total_seconds() < _SECTOR_NETWORK_PROBE_TTL:
            return _sector_network_available
    if not codes:
        _sector_network_available = False
        _sector_network_probe_time = now
        return False
    try:
        future = _sector_count_executor.submit(_get_sector_component_count_network, codes[0])
        count = future.result(timeout=1)
        _sector_network_available = count is not None and count > 0
    except Exception:
        _sector_network_available = False
    _sector_network_probe_time = now
    return _sector_network_available


def _get_sector_component_counts(sector_codes: List[str]) -> Dict[str, int]:
    """并发获取多个板块的成分股数量；网络不可用时快速返回静态兜底"""
    if not sector_codes:
        return {}

    # 1. 先探测网络是否可用；不可用则直接返回静态映射（避免每个板块都等待超时）
    if not _probe_sector_network(sector_codes):
        return {code: _DEFAULT_SECTOR_COUNTS.get(code, 0) for code in sector_codes}

    # 2. 网络可用：每个板块 2 秒超时，失败用静态兜底
    results: Dict[str, int] = {}
    futures = {
        code: _sector_count_executor.submit(_get_sector_component_count_network, code)
        for code in sector_codes
    }
    for code, fut in futures.items():
        try:
            count = fut.result(timeout=2)
            results[code] = count if count is not None and count > 0 else _DEFAULT_SECTOR_COUNTS.get(code, 0)
        except Exception:
            results[code] = _DEFAULT_SECTOR_COUNTS.get(code, 0)
    return results


def _get_sector_up_count_network(sector_code: str) -> Optional[int]:
    """仅尝试网络获取板块上涨家数"""
    try:
        df = _fetch_sector_components_from_network(sector_code)
        if df is not None and len(df) > 0 and "change_pct" in df.columns:
            return int((df["change_pct"] > 0).sum())
    except Exception:
        pass
    return None


def _get_sector_up_counts(sector_codes: List[str]) -> Dict[str, int]:
    """并发获取多个板块的上涨家数；网络不可用时快速返回 0"""
    if not sector_codes:
        return {}
    if not _probe_sector_network(sector_codes):
        return {code: 0 for code in sector_codes}
    results: Dict[str, int] = {}
    futures = {
        code: _sector_count_executor.submit(_get_sector_up_count_network, code)
        for code in sector_codes
    }
    for code, fut in futures.items():
        try:
            count = fut.result(timeout=2)
            results[code] = count if count is not None else 0
        except Exception:
            results[code] = 0
    return results


def _get_sector_volume_ratio_network(code_volume: tuple) -> Optional[float]:
    """基于板块 K 线近 5 日均量计算当前量比"""
    sector_code, current_volume = code_volume
    if not sector_code or current_volume is None or current_volume <= 0:
        return None
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from utils.data_fetcher import fetch_sector_kline
        today = datetime.now()
        end = today.strftime("%Y%m%d")
        start = (today - timedelta(days=60)).strftime("%Y%m%d")
        df = fetch_sector_kline(sector_code, start, end, "daily")
        if df is None or len(df) < 2 or "volume" not in df.columns:
            return None
        prev_avg = df["volume"].iloc[:-1].tail(5).mean()
        if prev_avg is None or prev_avg <= 0:
            return None
        return round(float(current_volume) / float(prev_avg), 2)
    except Exception:
        return None


def _get_sector_volume_ratios(codes_volumes: List[tuple]) -> Dict[str, Optional[float]]:
    """并发获取多个板块的量比；网络不可用时快速返回 None"""
    if not codes_volumes:
        return {}
    codes = [code for code, _ in codes_volumes]
    if not _probe_sector_network(codes):
        return {code: None for code in codes}
    results: Dict[str, Optional[float]] = {}
    futures = {
        code: _sector_count_executor.submit(_get_sector_volume_ratio_network, item)
        for item in codes_volumes
        for code, _ in [item]
    }
    for item, fut in zip(codes_volumes, [futures[item[0]] for item in codes_volumes]):
        code, _ = item
        try:
            results[code] = fut.result(timeout=2)
        except Exception:
            results[code] = None
    return results


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


# akshare 板块成分股数量缓存
_akshare_sector_count_cache: Dict[str, Any] = {}
_AKSHARE_SECTOR_COUNT_TTL = 3600


def _akshare_sector_count(sector_name: str, sector_type: str) -> int:
    """通过 akshare 获取板块成分股数量（带 1 小时缓存）"""
    cache_key = f"{sector_type}:{sector_name}"
    now = datetime.now()
    cached = _akshare_sector_count_cache.get(cache_key)
    if cached and (now - cached[1]).total_seconds() < _AKSHARE_SECTOR_COUNT_TTL:
        return cached[0]
    try:
        import akshare as ak
        if sector_type == "industry":
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
        else:
            df = ak.stock_board_concept_cons_em(symbol=sector_name)
        count = len(df) if df is not None and not df.empty else 0
    except Exception:
        count = 0
    _akshare_sector_count_cache[cache_key] = (count, now)
    return count


def _get_sector_component_count_akshare(sector_name: str, sector_type: str, timeout: float = 3.0) -> int:
    """带超时的 akshare 板块成分股数量查询"""
    try:
        future = _sector_count_executor.submit(_akshare_sector_count, sector_name, sector_type)
        return future.result(timeout=timeout)
    except Exception:
        return 0


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
            name = str(row.get("sector_name", ""))
            stock_count = count_map.get(code, 0)
            data_quality = "real" if stock_count > 0 else "approx"
            if stock_count == 0:
                stock_count = _approx_sector_count(code, name)
            sectors.append({
                "code": code,
                "name": name,
                "type": "industry",
                "level": "一级",
                "change_pct": round(row.get("change_pct", 0), 2),
                "stock_count": stock_count,
                "stocks": [],
                "data_quality": data_quality,
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
        stock_count = len(stocks)
        data_quality = "real" if stock_count > 0 else "approx"
        # 本地未命中时，用 akshare 补成分股数量
        if stock_count == 0:
            stock_count = _get_sector_component_count_akshare(s["name"], s["type"])
        # akshare 也失败时，用近似静态数量兜底
        if stock_count == 0:
            stock_count = _approx_sector_count(s["code"], s["name"])
        sectors.append({
            "code": s["code"],
            "name": s["name"],
            "type": s["type"],
            "level": s["level"],
            "stock_count": stock_count,
            "stocks": stocks[:50],  # 最多返回50只
            "data_quality": data_quality,
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
