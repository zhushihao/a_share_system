from fastapi import APIRouter, HTTPException, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json
from concurrent.futures import ThreadPoolExecutor
import asyncio

import aiosqlite
from backend.models.database import (
    DATABASE_PATH,
    init_db,
    add_watchlist,
    get_watchlist,
    get_watchlist_by_symbol,
    delete_watchlist,
    update_watchlist_group,
    get_watchlist_groups,
    WatchlistRecord,
)
from backend.services.data_provider import get_data_provider_service, DataProviderService
from backend.services.indicators import calculate_all_indicators, get_latest_indicators, calc_tech_score
from backend.models.schemas import StandardQuote
from datetime import datetime

router = APIRouter()

# 线程池用于并行计算指标（IO + CPU 密集型）
_indicator_executor = ThreadPoolExecutor(max_workers=4)


def _offline_quote_to_dict(provider: DataProviderService, symbol: str) -> dict:
    """从离线K线获取最新行情，转为 dict"""
    try:
        df = provider.fetch_ohlcv(symbol, period="daily", adjust="qfq")
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            return {
                "symbol": symbol,
                "name": None,
                "timestamp": datetime.now().isoformat(),
                "open": float(latest["open"]),
                "high": float(latest["high"]),
                "low": float(latest["low"]),
                "close": float(latest["close"]),
                "volume": int(latest["volume"]),
                "amount": float(latest.get("amount", 0)) if "amount" in latest else None,
                "source": "mootdx-offline",
                "freq": "1d",
            }
    except Exception:
        pass
    return {}

async def _get_db_conn() -> aiosqlite.Connection:
    """获取数据库连接（自动初始化表结构）"""
    return await init_db(DATABASE_PATH)


class WatchlistAddRequest(BaseModel):
    """添加自选股请求"""
    symbol: str
    name: str
    group: str = "默认"
    notes: str = ""
    tags: List[str] = []
    alert_price_high: Optional[float] = None
    alert_price_low: Optional[float] = None


class WatchlistUpdateGroupRequest(BaseModel):
    """修改分组请求"""
    group: str


class WatchlistBatchAddRequest(BaseModel):
    """批量添加自选股请求"""
    items: List[WatchlistAddRequest]


class WatchlistBatchGroupRequest(BaseModel):
    """批量修改分组请求"""
    symbols: List[str]
    group: str


@router.get("/watchlist")
async def list_watchlist(group: Optional[str] = None):
    """获取自选股列表"""
    conn = await _get_db_conn()
    try:
        items = await get_watchlist(conn, group=group)
        return {
            "count": len(items),
            "items": [asdict(item) for item in items],
        }
    finally:
        await conn.close()


@router.post("/watchlist")
async def create_watchlist(request: WatchlistAddRequest):
    """添加自选股"""
    conn = await _get_db_conn()
    try:
        record = await add_watchlist(
            conn,
            symbol=request.symbol,
            name=request.name,
            group=request.group,
            notes=request.notes,
            tags=request.tags,
            alert_price_high=request.alert_price_high,
            alert_price_low=request.alert_price_low,
        )
        return {"status": "ok", "item": asdict(record)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add watchlist: {str(e)}")
    finally:
        await conn.close()


@router.delete("/watchlist/{symbol}")
async def remove_watchlist(symbol: str):
    """删除自选股"""
    conn = await _get_db_conn()
    try:
        ok = await delete_watchlist(conn, symbol)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Watchlist item not found: {symbol}")
        return {"status": "ok", "symbol": symbol}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete watchlist: {str(e)}")
    finally:
        await conn.close()


@router.post("/watchlist/batch")
async def create_watchlist_batch(request: WatchlistBatchAddRequest):
    """批量添加/更新自选股"""
    conn = await _get_db_conn()
    try:
        from backend.models.database import add_watchlist_batch
        raw_items = [item.model_dump() for item in request.items]
        count = await add_watchlist_batch(conn, raw_items)
        return {"status": "ok", "count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to batch add watchlist: {str(e)}")
    finally:
        await conn.close()


@router.put("/watchlist/batch/group")
async def change_watchlist_group_batch(request: WatchlistBatchGroupRequest):
    """批量修改自选股分组"""
    conn = await _get_db_conn()
    try:
        from backend.models.database import update_watchlist_group_batch
        updated = await update_watchlist_group_batch(conn, request.symbols, request.group)
        return {"status": "ok", "updated": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to batch update group: {str(e)}")
    finally:
        await conn.close()


@router.put("/watchlist/{symbol}/group")
async def change_watchlist_group(symbol: str, request: WatchlistUpdateGroupRequest):
    """修改自选股分组"""
    conn = await _get_db_conn()
    try:
        ok = await update_watchlist_group(conn, symbol, request.group)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Watchlist item not found: {symbol}")
        return {"status": "ok", "symbol": symbol, "group": request.group}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update group: {str(e)}")
    finally:
        await conn.close()


@router.get("/watchlist/groups")
async def list_groups():
    """获取所有分组"""
    conn = await _get_db_conn()
    try:
        groups = await get_watchlist_groups(conn)
        return {"groups": groups, "count": len(groups)}
    finally:
        await conn.close()


# ───────────────────────────────────────────────
# 性能优化：with-quotes 并行指标计算
# ───────────────────────────────────────────────

def _compute_single_score(provider: DataProviderService, symbol: str) -> int:
    """在线程池中计算单只股票的评分"""
    try:
        # n=60 确保 MACD(12/26/9) 等指标能完整计算（需要至少 34 个有效数据点）
        df = provider.get_kline_latest(symbol, n=60)
        if df is not None and len(df) >= 20:
            df = calculate_all_indicators(df)
            return calc_tech_score(df)
    except Exception:
        pass
    return 0


@router.get("/watchlist/with-quotes")
async def list_watchlist_with_quotes(group: Optional[str] = None):
    """
    获取自选股列表（含实时行情 + 评分）
    
    性能优化：
    - 实时行情批量获取
    - 评分使用 ThreadPoolExecutor 并行计算
    - 仅获取最近 30 日 K 线（评分足够）
    """
    conn = await _get_db_conn()
    provider = get_data_provider_service()
    
    try:
        items = await get_watchlist(conn, group=group)
        if not items:
            return {"count": 0, "items": []}
        
        symbols = [item.symbol for item in items]
        
        # 1. 批量获取实时行情（一次 IO）
        quotes = provider.fetch_realtime_quotes(symbols)
        quote_map = {q.symbol: q.model_dump() for q in quotes}
        
        # 1.1 如果实时行情为空，逐个用离线数据补充（确保自选股有行情显示）
        missing_symbols = [s for s in symbols if s not in quote_map or not quote_map[s]]
        for symbol in missing_symbols:
            try:
                quote_map[symbol] = _offline_quote_to_dict(provider, symbol)
            except Exception:
                pass
        
        # 2. 并行计算评分（CPU 密集型，使用线程池）
        loop = asyncio.get_event_loop()
        score_tasks = [
            loop.run_in_executor(_indicator_executor, _compute_single_score, provider, item.symbol)
            for item in items
        ]
        scores = await asyncio.gather(*score_tasks)
        
        # 3. 组装结果
        result_items = []
        for item, score in zip(items, scores):
            item_dict = asdict(item)
            item_dict["quote"] = quote_map.get(item.symbol, {})
            item_dict["score"] = score
            item_dict["indicators"] = {}
            result_items.append(item_dict)
        
        return {
            "count": len(result_items),
            "items": result_items,
        }
    finally:
        await conn.close()


@router.get("/watchlist/with-indicators")
async def list_watchlist_with_indicators(group: Optional[str] = None):
    """
    获取自选股完整指标（按需调用，较慢）
    
    此接口计算完整技术指标（MA/KD/MACD/RSI/BOLL），
    建议前端仅对当前可见行或选中股票调用。
    """
    conn = await _get_db_conn()
    provider = get_data_provider_service()
    
    try:
        items = await get_watchlist(conn, group=group)
        if not items:
            return {"count": 0, "items": []}
        
        symbols = [item.symbol for item in items]
        quotes = provider.fetch_realtime_quotes(symbols)
        quote_map = {q.symbol: q.model_dump() for q in quotes}
        
        # 并行计算完整指标
        loop = asyncio.get_event_loop()
        
        def _compute_full(provider: DataProviderService, symbol: str) -> Dict[str, Any]:
            try:
                df = provider.get_kline_latest(symbol, n=60)
                if df is not None and len(df) >= 20:
                    df = calculate_all_indicators(df)
                    return {
                        "indicators": get_latest_indicators(df),
                        "score": calc_tech_score(df),
                    }
            except Exception:
                pass
            return {"indicators": {}, "score": 0}
        
        indicator_tasks = [
            loop.run_in_executor(_indicator_executor, _compute_full, provider, item.symbol)
            for item in items
        ]
        indicator_results = await asyncio.gather(*indicator_tasks)
        
        result_items = []
        for item, ind in zip(items, indicator_results):
            item_dict = asdict(item)
            item_dict["quote"] = quote_map.get(item.symbol, {})
            item_dict.update(ind)
            result_items.append(item_dict)
        
        return {
            "count": len(result_items),
            "items": result_items,
        }
    finally:
        await conn.close()


# ───────────────────────────────────────────────
# 导入导出
# ───────────────────────────────────────────────

class WatchlistImportRequest(BaseModel):
    """导入自选股请求"""
    items: List[Dict[str, Any]]
    overwrite: bool = True


@router.post("/watchlist/import")
async def import_watchlist(request: WatchlistImportRequest):
    """
    批量导入自选股
    
    items 格式: [{"symbol": "000001", "name": "平安银行", "group": "默认"}, ...]
    """
    conn = await _get_db_conn()
    try:
        added = 0
        updated = 0
        failed = []
        
        for item in request.items:
            try:
                symbol = item.get("symbol", "").strip()
                name = item.get("name", "").strip()
                group = item.get("group", "默认").strip() or "默认"
                
                if not symbol or not name:
                    failed.append({"item": item, "reason": "missing symbol or name"})
                    continue
                
                record = await add_watchlist(
                    conn,
                    symbol=symbol,
                    name=name,
                    group=group,
                    notes=item.get("notes", ""),
                    tags=item.get("tags", []),
                )
                added += 1
            except Exception as e:
                failed.append({"item": item, "reason": str(e)})
        
        return {
            "status": "ok",
            "added": added,
            "failed": len(failed),
            "failed_items": failed[:10],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
        await conn.close()


@router.get("/watchlist/export")
async def export_watchlist():
    """导出自选股为 CSV 格式"""
    conn = await _get_db_conn()
    try:
        items = await get_watchlist(conn)
        
        # 生成 CSV
        lines = ["symbol,name,group,added_at,notes,tags,alert_price_high,alert_price_low"]
        for item in items:
            tags = "|".join(item.tags) if item.tags else ""
            lines.append(
                f"{item.symbol},{item.name},{item.group},{item.added_at},{item.notes or ''},{tags},{item.alert_price_high or ''},{item.alert_price_low or ''}"
            )
        
        csv_content = "\n".join(lines)
        
        return {
            "status": "ok",
            "count": len(items),
            "csv": csv_content,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
    finally:
        await conn.close()


def asdict(record: WatchlistRecord) -> Dict[str, Any]:
    """将 WatchlistRecord 转换为字典"""
    return {
        "id": record.id,
        "symbol": record.symbol,
        "name": record.name,
        "group": record.group,
        "added_at": record.added_at,
        "notes": record.notes,
        "tags": record.tags,
        "alert_price_high": record.alert_price_high,
        "alert_price_low": record.alert_price_low,
    }
