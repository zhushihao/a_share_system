# -*- coding: utf-8 -*-
"""
Data Management API - 数据管理接口

功能：
1. 数据概览（通达信目录状态、数据量统计）
2. 数据目录（股票列表、板块列表）
3. 数据诊断（数据完整性、缺失检测）
4. 数据导出（CSV/JSON）
5. 数据更新日志
"""

import os
import json
import logging
import pandas as pd
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.data_provider import get_data_provider_service
from backend.services.data_platform import get_data_platform_service
from backend.config import settings

# 股票列表响应缓存（降低频繁全量读取 DBF 的开销）
_stock_list_cache: Optional[pd.DataFrame] = None
_stock_list_cache_time: Optional[datetime] = None
_STOCK_LIST_CACHE_TTL = 300  # 5 分钟


def _get_cached_stock_list(provider) -> Optional[pd.DataFrame]:
    """带缓存地获取股票列表"""
    global _stock_list_cache, _stock_list_cache_time
    now = datetime.now()
    if _stock_list_cache is not None and _stock_list_cache_time is not None:
        if (now - _stock_list_cache_time).total_seconds() < _STOCK_LIST_CACHE_TTL:
            return _stock_list_cache
    df = provider.fetch_stock_list()
    _stock_list_cache = df
    _stock_list_cache_time = now
    return df

router = APIRouter()


# ───────────────────────────────────────────────
# Pydantic Models
# ───────────────────────────────────────────────

class DataExportRequest(BaseModel):
    """数据导出请求"""
    symbol: str = Field(..., description="股票代码")
    start_date: str = Field("", description="起始日期")
    end_date: str = Field("", description="结束日期")
    period: str = Field("daily", description="周期")
    adjust: str = Field("qfq", description="复权方式")
    format: str = Field("csv", description="导出格式：csv/json")


# ───────────────────────────────────────────────
# API Routes
# ───────────────────────────────────────────────

@router.get("/data/overview")
async def data_overview():
    """
    获取数据概览
    
    返回通达信目录状态、数据量统计等。
    """
    provider = get_data_provider_service()
    health = provider.health_check()
    
    # 统计通达信目录文件
    tdxdir = settings.TDX_DIR if hasattr(settings, "TDX_DIR") else "D:/TDX"
    tdx_files = {"total_files": 0, "total_size_mb": 0}
    
    if os.path.exists(tdxdir):
        try:
            for root, dirs, files in os.walk(tdxdir):
                for f in files:
                    fpath = os.path.join(root, f)
                    try:
                        tdx_files["total_size_mb"] += os.path.getsize(fpath) / (1024 * 1024)
                    except Exception:
                        pass
                tdx_files["total_files"] += len(files)
        except Exception:
            pass
    
    tdx_files["total_size_mb"] = round(tdx_files["total_size_mb"], 2)
    
    # 获取股票列表
    stock_count = 0
    try:
        stock_list = _get_cached_stock_list(provider)
        if stock_list is not None:
            stock_count = len(stock_list)
    except Exception:
        pass
    
    return {
        "status": "ok",
        "tdx_dir": tdxdir,
        "tdx_dir_exists": os.path.exists(tdxdir) if tdxdir else False,
        "health": health,
        "tdx_files": tdx_files,
        "stock_count": stock_count,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/data/stock-list")
async def get_stock_list(
    market: Optional[str] = Query(None, description="市场筛选：sh/sz/bj"),
    limit: int = Query(1000, ge=1, le=20000),
):
    """
    获取全市场股票列表
    """
    provider = get_data_provider_service()

    try:
        df = _get_cached_stock_list(provider)
        if df is None or len(df) == 0:
            return {"status": "ok", "count": 0, "stocks": []}

        # 筛选市场：优先使用 provider 返回的 market 字段，避免把上海指数代码误判为深圳
        if market and "market" in df.columns:
            df = df[df["market"].astype(str).str.lower() == market.lower()]
        elif market and "code" in df.columns:
            if market.lower() == "sh":
                df = df[df["code"].astype(str).str.startswith("6")]
            elif market.lower() == "sz":
                df = df[df["code"].astype(str).str.startswith(("0", "3"))]
            elif market.lower() == "bj":
                df = df[df["code"].astype(str).str.startswith(("4", "8"))]

        # 同一 code 可能同时存在 sh/sz 两条记录，按 code 去重保留第一条
        df = df.drop_duplicates(subset=["code"], keep="first")

        # 按代码排序，避免截断时丢失特定股票（如 300308 中际旭创）
        df = df.sort_values(by="code").reset_index(drop=True).head(limit)

        # 转换为标准格式，按代码前缀强制推断市场（避免 provider 返回错误 market）
        records = []
        for _, row in df.iterrows():
            code = str(row.get("code", ""))
            records.append({
                "code": code,
                "name": str(row.get("name", "")),
                "market": _infer_market(code),
            })

        return {
            "status": "ok",
            "count": len(records),
            "stocks": records,
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to fetch stock list: {str(e)}",
            "count": 0,
            "stocks": [],
        }


@router.get("/stock/search")
async def search_stocks(
    q: str = Query(..., description="搜索关键词（代码/名称）"),
    limit: int = Query(10, ge=1, le=50),
):
    """
    搜索股票（支持代码/名称/拼音首字母匹配）
    
    返回匹配的股票列表，用于前端搜索自动完成。
    """
    provider = get_data_provider_service()
    
    try:
        df = provider.fetch_stock_list()
        if df is None or len(df) == 0:
            return {"status": "ok", "count": 0, "stocks": []}
        
        q = q.strip().lower()
        if not q:
            return {"status": "ok", "count": 0, "stocks": []}

        # 补齐6位代码用于匹配
        code_6 = q.zfill(6) if len(q) <= 6 else q
        matches = []
        seen_codes = set()

        for _, row in df.iterrows():
            row_code = str(row.get("code", "")).strip()
            row_name = str(row.get("name", "")).strip()

            # 匹配条件：代码开头匹配 或 名称包含关键词
            if (row_code.startswith(q) or row_code.startswith(code_6) or
                q in row_name.lower()):
                if row_code in seen_codes:
                    continue
                seen_codes.add(row_code)
                matches.append({
                    "code": row_code,
                    "name": row_name,
                    "market": _infer_market(row_code),
                })

            if len(matches) >= limit:
                break

        return {
            "status": "ok",
            "count": len(matches),
            "stocks": matches,
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Search failed: {str(e)}",
            "count": 0,
            "stocks": [],
        }


def _infer_market(code: str) -> str:
    """根据代码推断市场"""
    if code.startswith("6"):
        return "sh"
    elif code.startswith(("0", "3")):
        return "sz"
    elif code.startswith(("4", "8")):
        return "bj"
    return "unknown"


@router.get("/data/diagnose")
async def diagnose_data(
    symbol: str = Query(..., description="股票代码，如 000001"),
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
):
    """
    数据诊断（兼容旧版 query 参数）
    """
    return await _diagnose_symbol(symbol, period)


@router.get("/data/diagnose/{symbol}")
async def diagnose_data_v2(
    symbol: str,
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
):
    """
    数据诊断 V2（路径参数）

    四维度数据质量检查：
    1. 完整性 — 数据缺失、日期断层
    2. 一致性 — 价格逻辑（high>=low, close在范围内）
    3. 时效性 — 最新数据日期距今天数
    4. 异常值 — 价格=0、成交量=0、涨跌停异常
    """
    return await _diagnose_symbol(symbol, period)


async def _diagnose_symbol(symbol: str, period: str) -> Dict[str, Any]:
    """内部诊断逻辑"""
    provider = get_data_provider_service()

    try:
        df = provider.fetch_ohlcv(symbol=symbol, period=period, adjust="qfq")
        if df is None or len(df) == 0:
            return {
                "status": "ok",
                "symbol": symbol,
                "period": period,
                "available": False,
                "message": "无数据",
                "diagnosis": {},
            }

        diagnosis = {
            # 完整性
            "total_rows": len(df),
            "date_range": {
                "start": str(df.iloc[0].get("date", "")),
                "end": str(df.iloc[-1].get("date", "")),
            },
            "missing_values": {},
            # 一致性
            "consistency_issues": [],
            # 时效性
            "timeliness": {},
            # 异常值
            "zero_volume_days": 0,
            "price_anomalies": 0,
            "zero_price_days": 0,
            "gaps": [],
        }

        # 检查缺失值
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                missing = df[col].isna().sum()
                if missing > 0:
                    diagnosis["missing_values"][col] = int(missing)

        # 检查一致性（价格逻辑）
        if all(c in df.columns for c in ["open", "high", "low", "close"]):
            invalid_high_low = (df["high"] < df["low"]).sum()
            invalid_close = ((df["close"] > df["high"]) | (df["close"] < df["low"])).sum()
            invalid_open = ((df["open"] > df["high"]) | (df["open"] < df["low"])).sum()
            if invalid_high_low > 0:
                diagnosis["consistency_issues"].append(f"high<low 记录 {invalid_high_low} 条")
            if invalid_close > 0:
                diagnosis["consistency_issues"].append(f"close 超出 high/low 范围 {invalid_close} 条")
            if invalid_open > 0:
                diagnosis["consistency_issues"].append(f"open 超出 high/low 范围 {invalid_open} 条")

        # 检查时效性
        if "date" in df.columns and len(df) > 0:
            try:
                latest_date = pd.to_datetime(df.iloc[-1]["date"])
                today = pd.to_datetime(datetime.now().date())
                days_gap = (today - latest_date).days
                diagnosis["timeliness"] = {
                    "latest_date": str(df.iloc[-1].get("date", "")),
                    "days_behind": days_gap,
                    "status": "current" if days_gap <= 1 else "delayed" if days_gap <= 3 else "stale",
                }
            except Exception:
                pass

        # 检查零成交量
        if "volume" in df.columns:
            diagnosis["zero_volume_days"] = int((df["volume"] == 0).sum())

        # 检查零价格
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                zero_count = (df[col] == 0).sum()
                if zero_count > 0:
                    diagnosis["zero_price_days"] += int(zero_count)

        # 检查价格异常（涨停/跌停或价格突变）
        if "close" in df.columns and len(df) > 1:
            close_pct = df["close"].pct_change().abs()
            # A股涨停约 10%，ST 约 5%
            anomalies = (close_pct > 0.11).sum()
            diagnosis["price_anomalies"] = int(anomalies)

        # 检查日期断层（交易日间隔 > 5 天，排除正常节假日）
        HOLIDAY_GAPS = {8, 9, 10, 11}
        NORMAL_GAP_THRESHOLD = 5

        if "date" in df.columns and len(df) > 1:
            try:
                dates = pd.to_datetime(df["date"])
                gaps = []
                for i in range(1, len(dates)):
                    gap = (dates.iloc[i] - dates.iloc[i-1]).days
                    if gap > NORMAL_GAP_THRESHOLD and gap not in HOLIDAY_GAPS:
                        gaps.append({
                            "from": str(dates.iloc[i-1]),
                            "to": str(dates.iloc[i]),
                            "gap_days": gap,
                        })
                diagnosis["gaps"] = gaps[:10]
                diagnosis["gap_count"] = len(gaps)
            except Exception:
                pass

        # 综合质量评分
        quality_score = 100
        if diagnosis["missing_values"]:
            quality_score -= sum(diagnosis["missing_values"].values()) * 2
        if diagnosis["consistency_issues"]:
            quality_score -= len(diagnosis["consistency_issues"]) * 5
        if diagnosis.get("timeliness", {}).get("status") == "delayed":
            quality_score -= 10
        elif diagnosis.get("timeliness", {}).get("status") == "stale":
            quality_score -= 30
        quality_score -= diagnosis["zero_volume_days"] * 2
        quality_score -= diagnosis["zero_price_days"] * 5
        quality_score -= diagnosis["price_anomalies"] * 1
        quality_score -= diagnosis.get("gap_count", 0) * 2
        diagnosis["quality_score"] = max(0, min(100, int(quality_score)))

        return {
            "status": "ok",
            "symbol": symbol,
            "period": period,
            "available": True,
            "diagnosis": diagnosis,
        }

    except Exception as e:
        return {
            "status": "error",
            "symbol": symbol,
            "period": period,
            "message": str(e),
        }


@router.get("/data/quality")
async def data_quality_scan(
    sample_size: int = Query(50, ge=1, le=200, description="抽样检查股票数量"),
):
    """
    数据质量扫描
    
    对全市场数据抽样检查，返回数据质量报告。
    检查项：
    1. 价格=0 / 成交量=0
    2. 日期不连续
    3. 价格逻辑不一致（high<low, close超出范围）
    4. 数据时效性（延迟>1天）
    """
    provider = get_data_provider_service()
    
    try:
        stock_list = provider.fetch_stock_list()
        if stock_list is None or len(stock_list) == 0:
            return {
                "status": "ok",
                "sample_size": 0,
                "quality_score": 0,
                "issues": [],
                "summary": {},
            }
        
        # 抽样
        import random
        random.seed(42)  # 可复现
        sample = stock_list.head(sample_size) if len(stock_list) > sample_size else stock_list
        codes = sample["code"].astype(str).tolist()
        
        issues = []
        total_checked = 0
        total_rows = 0
        zero_price_count = 0
        zero_volume_count = 0
        consistency_issues = 0
        timeliness_issues = 0
        
        for code in codes:
            try:
                df = provider.fetch_ohlcv(symbol=code, period="daily", adjust="qfq")
                if df is None or len(df) == 0:
                    continue
                
                total_checked += 1
                total_rows += len(df)
                
                # 检查零价格
                for col in ["open", "high", "low", "close"]:
                    if col in df.columns:
                        zero_price_count += int((df[col] == 0).sum())
                
                # 检查零成交量
                if "volume" in df.columns:
                    zero_volume_count += int((df["volume"] == 0).sum())
                
                # 检查一致性
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    consistency_issues += int((df["high"] < df["low"]).sum())
                    consistency_issues += int(((df["close"] > df["high"]) | (df["close"] < df["low"])).sum())
                
                # 检查时效性
                if "date" in df.columns and len(df) > 0:
                    latest_date = pd.to_datetime(df.iloc[-1]["date"])
                    today = pd.to_datetime(datetime.now().date())
                    if (today - latest_date).days > 1:
                        timeliness_issues += 1
            except Exception:
                continue
        
        # 计算质量评分
        quality_score = 100
        if total_rows > 0:
            quality_score -= (zero_price_count / total_rows) * 500
            quality_score -= (zero_volume_count / total_rows) * 200
            quality_score -= (consistency_issues / total_rows) * 300
        quality_score -= timeliness_issues * 2
        quality_score = max(0, min(100, int(quality_score)))
        
        summary = {
            "total_checked": total_checked,
            "total_rows": total_rows,
            "zero_price_count": zero_price_count,
            "zero_volume_count": zero_volume_count,
            "consistency_issues": consistency_issues,
            "timeliness_issues": timeliness_issues,
            "quality_score": quality_score,
        }
        
        return {
            "status": "ok",
            "sample_size": sample_size,
            "quality_score": quality_score,
            "issues": issues[:20],
            "summary": summary,
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }



@router.get("/data/export")
async def export_data(
    symbol: str = Query(..., description="股票代码"),
    start_date: str = Query("", description="起始日期"),
    end_date: str = Query("", description="结束日期"),
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
    format: str = Query("csv", enum=["csv", "json"]),
):
    """
    导出数据
    
    返回 CSV 或 JSON 格式的 K 线数据。
    """
    provider = get_data_provider_service()
    
    try:
        df = provider.fetch_ohlcv(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
            adjust=adjust,
        )
        
        if df is None or len(df) == 0:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
        
        if format == "csv":
            # 返回 CSV 文本
            csv_content = df.to_csv(index=False)
            return {
                "status": "ok",
                "format": "csv",
                "symbol": symbol,
                "count": len(df),
                "data": csv_content,
            }
        else:
            # 返回 JSON
            records = df.to_dict("records")
            return {
                "status": "ok",
                "format": "json",
                "symbol": symbol,
                "count": len(records),
                "data": records,
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/data/health")
async def data_health():
    """
    数据源健康检查（含数据中台自检结果）
    """
    provider = get_data_provider_service()
    health = provider.health_check()

    status = "ok"
    quality_issues = []
    if not health.get("offline_available") and not health.get("realtime_available"):
        status = "degraded"

    # 聚合数据中台自检告警
    try:
        platform = get_data_platform_service()
        sc = getattr(platform, "_last_self_check", None) or {}
        if sc:
            qc = sc.get("quality_checks", {})
            failed = sum(v.get("failed", 0) for v in qc.values())
            if failed > 0:
                status = "warning" if status == "ok" else status
                quality_issues.append(f"数据质量检查失败 {failed} 项")
            for name, info in sc.get("data_sources", {}).items():
                if info.get("status") not in ("ok", None):
                    quality_issues.append(f"{name}: {info['status']}")
    except Exception as e:
        logger = logging.getLogger("data")
        logger.warning(f"聚合数据中台自检失败: {type(e).__name__}: {e}")

    return {
        "status": status,
        "health": health,
        "quality_issues": quality_issues,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/data/compare")
async def compare_data(
    symbol: str = Query(..., description="股票代码"),
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
    adjust: str = Query("qfq", enum=["qfq", "hfq", "none"]),
):
    """
    实时数据 vs TDX 离线数据比对

    返回差异报告：缺失日期、价格差异、成交量差异。
    """
    provider = get_data_provider_service()
    result = provider.compare_realtime_vs_offline(symbol, period=period, adjust=adjust)
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        **result,
    }
