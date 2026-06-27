# -*- coding: utf-8 -*-
"""
Dashboard Data Service - 看板数据组装服务

从现有系统获取数据，组装成看板需要的格式。
职责：
1. 市场概览数据（指数、涨跌家数）
2. 板块热点数据
3. 今日信号
4. 关注股状态
5. 系统健康状态

策略：
- 实时数据：调用 mootdx 实时层（Quotes）
- 离线数据：从 D:/TDX 读取
- 缓存：使用 MultiLevelCache 加速
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.mootdx_provider import MootdxDataProvider
from core.resilience import DataSourceResilience
from core.cache import MultiLevelCache
from core.observability import get_obs


class DashboardDataService:
    """
    看板数据服务
    
    Usage:
        service = DashboardDataService()
        
        # 市场概览
        overview = service.get_market_overview()
        
        # 板块热点
        sectors = service.get_top_sectors(limit=10)
        
        # 关注股
        stocks = service.get_watchlist_status(codes=["000001", "600519"])
    """
    
    def __init__(self, tdxdir: str = "D:/TDX"):
        self._obs = get_obs()
        self._provider = MootdxDataProvider(tdxdir=tdxdir)
        self._resilience = DataSourceResilience()
        self._cache = MultiLevelCache()
        self._cache_ttl = 30  # 看板数据缓存30秒
    
    # ── 市场概览 ──
    
    def get_market_overview(self) -> Dict[str, Any]:
        """获取市场概览数据"""
        cache_key = "dashboard:market_overview"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            # 获取主要指数行情
            indices = self._provider.fetch_realtime_quote(["000001", "399001", "399006"])
            
            overview = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "indices": self._format_indices(indices),
                "market_status": self._get_market_status(),
            }
            
            self._cache.set(cache_key, overview, ttl=self._cache_ttl)
            return overview
            
        except Exception as e:
            self._obs.log("ERROR", f"Market overview failed: {str(e)}", "DashboardDataService")
            return {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "error": str(e)}
    
    def _format_indices(self, indices_df) -> List[Dict]:
        """格式化指数数据"""
        if indices_df is None or len(indices_df) == 0:
            return []
        
        index_names = {
            "000001": "上证指数",
            "399001": "深证成指",
            "399006": "创业板指",
        }
        
        result = []
        for _, row in indices_df.iterrows():
            code = str(row.get("code", ""))
            name = index_names.get(code, code)
            price = row.get("price", 0)
            last_close = row.get("last_close", 0) or 1
            change_pct = round((price - last_close) / last_close * 100, 2) if last_close > 0 else 0
            
            result.append({
                "name": name,
                "code": code,
                "price": round(price, 2),
                "change_pct": change_pct,
                "status": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
            })
        
        return result
    
    def _get_market_status(self) -> str:
        """判断当前市场状态"""
        now = datetime.now()
        t = now.time()
        weekday = now.weekday()
        
        if weekday >= 5:  # 周末
            return "closed"
        
        if t < datetime.strptime("09:15", "%H:%M").time():
            return "pre_open"
        elif t < datetime.strptime("09:30", "%H:%M").time():
            return "auction"  # 集合竞价
        elif t < datetime.strptime("11:30", "%H:%M").time():
            return "trading_am"
        elif t < datetime.strptime("13:00", "%H:%M").time():
            return "noon_break"
        elif t < datetime.strptime("15:00", "%H:%M").time():
            return "trading_pm"
        else:
            return "closed"
    
    # ── 板块热点 ──
    
    def get_top_sectors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取板块热点排名"""
        cache_key = f"dashboard:top_sectors:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            # TODO: 从现有板块计算模块获取数据
            # 当前使用模拟数据占位，后续接入 sector_calculation_harness
            sectors = self._mock_sectors()[:limit]
            
            self._cache.set(cache_key, sectors, ttl=self._cache_ttl)
            return sectors
            
        except Exception as e:
            self._obs.log("ERROR", f"Top sectors failed: {str(e)}", "DashboardDataService")
            return []
    
    def _mock_sectors(self) -> List[Dict]:
        """模拟板块数据（后续替换为真实数据）"""
        return [
            {"name": "半导体", "change_pct": 3.52, "leader": "中芯国际", "leader_code": "688981", "momentum": 85},
            {"name": "白酒", "change_pct": 2.18, "leader": "贵州茅台", "leader_code": "600519", "momentum": 78},
            {"name": "新能源", "change_pct": 1.95, "leader": "宁德时代", "leader_code": "300750", "momentum": 72},
            {"name": "银行", "change_pct": 1.23, "leader": "招商银行", "leader_code": "600036", "momentum": 65},
            {"name": "医药", "change_pct": 0.87, "leader": "恒瑞医药", "leader_code": "600276", "momentum": 58},
            {"name": "汽车", "change_pct": 0.56, "leader": "比亚迪", "leader_code": "002594", "momentum": 52},
            {"name": "电力", "change_pct": 0.34, "leader": "长江电力", "leader_code": "600900", "momentum": 48},
            {"name": "房地产", "change_pct": -0.21, "leader": "万科A", "leader_code": "000002", "momentum": 42},
            {"name": "钢铁", "change_pct": -0.45, "leader": "宝钢股份", "leader_code": "600019", "momentum": 38},
            {"name": "煤炭", "change_pct": -0.78, "leader": "中国神华", "leader_code": "601088", "momentum": 35},
        ]
    
    # ── 关注股 ──
    
    def get_watchlist_status(self, codes: List[str]) -> List[Dict[str, Any]]:
        """获取关注股实时状态"""
        if not codes:
            return []
        
        cache_key = f"dashboard:watchlist:{','.join(sorted(codes))}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            quotes = self._provider.fetch_realtime_quote(codes)
            if quotes is None or len(quotes) == 0:
                return []
            
            result = []
            for _, row in quotes.iterrows():
                code = str(row.get("code", ""))
                price = row.get("price", 0)
                last_close = row.get("last_close", 0) or 1
                change_pct = round((price - last_close) / last_close * 100, 2)
                
                result.append({
                    "code": code,
                    "name": self._get_stock_name(code),
                    "price": round(price, 2),
                    "change_pct": change_pct,
                    "status": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
                    "volume": int(row.get("volume", 0)),
                    "amount": round(row.get("amount", 0) / 1e8, 2),  # 亿元
                })
            
            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            return result
            
        except Exception as e:
            self._obs.log("ERROR", f"Watchlist status failed: {str(e)}", "DashboardDataService")
            return []
    
    def _get_stock_name(self, code: str) -> str:
        """获取股票名称（简化版）"""
        # TODO: 从数据获取名称，当前用已知映射
        name_map = {
            "000001": "平安银行",
            "600519": "贵州茅台",
            "300750": "宁德时代",
            "600036": "招商银行",
            "600276": "恒瑞医药",
            "002594": "比亚迪",
            "600900": "长江电力",
            "000002": "万科A",
            "600019": "宝钢股份",
            "601088": "中国神华",
        }
        return name_map.get(code, code)
    
    # ── 今日信号 ──
    
    def get_today_signals(self) -> List[Dict[str, Any]]:
        """获取今日交易信号"""
        # TODO: 从持久化存储读取今日信号
        return []
    
    # ── 系统健康 ──
    
    def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        health = self._provider.health_check()
        
        return {
            "offline_data": health["offline_available"],
            "realtime_data": health["realtime_available"],
            "tdxdir": health["tdxdir_exists"],
            "mootdx": health["mootdx_installed"],
            "stats": health["stats"],
        }
    
    # ── 单股行情 ──
    
    def get_stock_quote(self, code: str) -> Dict[str, Any]:
        """获取单股实时行情"""
        try:
            quotes = self._provider.fetch_realtime_quote([code])
            if quotes is None or len(quotes) == 0:
                return {"error": "No data"}
            
            row = quotes.iloc[0]
            price = row.get("price", 0)
            last_close = row.get("last_close", 0) or 1
            change_pct = round((price - last_close) / last_close * 100, 2)
            
            return {
                "code": code,
                "name": self._get_stock_name(code),
                "price": round(price, 2),
                "open": round(row.get("open", 0), 2),
                "high": round(row.get("high", 0), 2),
                "low": round(row.get("low", 0), 2),
                "last_close": round(last_close, 2),
                "change_pct": change_pct,
                "volume": int(row.get("volume", 0)),
                "amount": round(row.get("amount", 0) / 1e8, 2),
                "bid1": round(row.get("bid1", 0), 2),
                "ask1": round(row.get("ask1", 0), 2),
            }
        except Exception as e:
            return {"error": str(e)}


    # ── Phase 3: 新增方法 ──

    def get_all_sectors(self) -> List[Dict[str, Any]]:
        """获取全部板块数据"""
        from events.sector_trigger import DEFAULT_SECTORS
        sectors = []
        for name, codes in DEFAULT_SECTORS.items():
            sectors.append({
                "name": name,
                "change_pct": 0.0,
                "momentum": 50,
                "leader": codes[0] if codes else "",
                "leader_code": codes[0] if codes else "",
                "leader_change": 0.0,
                "stock_count": len(codes),
            })
        return sectors

    def get_signals_history(self) -> List[Dict[str, Any]]:
        """获取历史信号列表"""
        return []

    def get_stock_kline(self, code: str) -> List[Dict[str, Any]]:
        """获取单股最近30日K线"""
        try:
            df = self._provider.fetch_kline(code, "", "", source="auto")
            if df is None or len(df) == 0:
                return []
            df = df.tail(30)
            return [
                {
                    "date": str(row["date"]),
                    "open": round(float(row["open"]), 2),
                    "high": round(float(row["high"]), 2),
                    "low": round(float(row["low"]), 2),
                    "close": round(float(row["close"]), 2),
                    "volume": int(row["volume"]),
                }
                for _, row in df.iterrows()
            ]
        except Exception as e:
            self._obs.log("WARN", f"Kline failed for {code}: {str(e)}", "DashboardDataService")
            return []

    def get_stock_analysis(self, code: str) -> Dict[str, Any]:
        """获取单股分析指标"""
        return {
            "momentum_score": 0,
            "trend_strength": "--",
            "pattern": "--",
            "overall_score": 0,
        }
