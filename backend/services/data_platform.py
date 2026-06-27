# -*- coding: utf-8 -*-
"""
Data Platform Service - 数据中台核心模块

职责：
1. 统一数据缓存管理（L1/L2/L3）
2. 数据质量自动检查（完整性/一致性/时效性/异常值）
3. 自动更新与按需刷新
4. 定时自检报告（每30分钟）
5. 异常降级（缓存兜底）

参考：Bloomberg / Morningstar 数据更新策略
"""

import sys
import os
import time
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple, Union

import pandas as pd
import numpy as np

# ─────────────────────────────────────────
# 确保项目根目录在 sys.path
# ─────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.core.cache import MultiLevelCache, TTL_PRESETS
from backend.core.observability import get_obs
from backend.services.data_provider import get_data_provider_service, DataProviderService
from backend.services.indicators import calculate_all_indicators, get_latest_indicators
from backend.models.schemas import StandardQuote


# ─────────────────────────────────────────
# 常量配置
# ─────────────────────────────────────────
RT_TTL = 300                    # 实时缓存 5 分钟
MINUTE_TTL = 60                 # 分钟级数据缓存 1 分钟（高频刷新）
DAILY_TTL = 86400               # 日缓存 24 小时
STOCK_LIST_TTL = 86400          # 股票列表 24 小时
SELF_CHECK_INTERVAL = 1800      # 自检间隔 30 分钟

# 周期到 TTL 的映射
PERIOD_TTL_MAP = {
    "minute": MINUTE_TTL,       # 分钟级 1 分钟
    "daily": DAILY_TTL,          # 日线 24 小时
    "weekly": DAILY_TTL,         # 周线 24 小时
    "monthly": DAILY_TTL,        # 月线 24 小时
    "quarterly": DAILY_TTL,      # 季线 24 小时（基于月线聚合）
    "yearly": DAILY_TTL,         # 年线 24 小时（基于月线聚合）
}

# 四大指数
DEFAULT_INDEX_SYMBOLS = ["sh000001", "sz399001", "sz399006", "sh000688"]

# 科创板/创业板/北交所前缀（涨跌停限制更宽）
HIGH_LIMIT_PREFIXES = ("688", "300", "301", "689", "430", "83", "87", "88", "82", "92")

# 价格一致性检查容差（2分钱，覆盖浮点误差）
PRICE_TOL = 0.02


# ─────────────────────────────────────────
# 数据质量结果对象
# ─────────────────────────────────────────

class DataQualityResult:
    """数据质量检查结果——结构化容器"""

    def __init__(self):
        self.completeness_passed = True
        self.consistency_passed = True
        self.timeliness_passed = True
        self.outliers_passed = True
        self.completeness_issues: List[str] = []
        self.consistency_issues: List[str] = []
        self.timeliness_issues: List[str] = []
        self.outliers_issues: List[str] = []
        self.overall_passed = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_passed": self.overall_passed,
            "completeness": {
                "passed": self.completeness_passed,
                "issues": self.completeness_issues,
            },
            "consistency": {
                "passed": self.consistency_passed,
                "issues": self.consistency_issues,
            },
            "timeliness": {
                "passed": self.timeliness_passed,
                "issues": self.timeliness_issues,
            },
            "outliers": {
                "passed": self.outliers_passed,
                "issues": self.outliers_issues,
            },
            "issues": (
                self.completeness_issues
                + self.consistency_issues
                + self.timeliness_issues
                + self.outliers_issues
            ),
        }


# ─────────────────────────────────────────
# 核心服务类
# ─────────────────────────────────────────

class DataPlatformService:
    """
    数据中台服务 - 统一数据缓存、质量检查与自动更新

    缓存策略：
    - 实时数据（5分钟TTL）：market_overview, index_quotes, stock_quotes, hotspots
    - 日数据（24小时TTL）：stock_list, ohlcv, indicators

    线程安全：所有状态变更均通过 threading.Lock 保护
    """

    def __init__(self, tdxdir: str = "D:/TDX"):
        # 核心组件
        self._cache = MultiLevelCache()
        self._provider = get_data_provider_service(tdxdir=tdxdir)
        self._obs = get_obs()

        # 线程安全
        self._lock = threading.Lock()

        # 状态追踪
        self._last_update: Dict[str, datetime] = {}
        self._quality_history: List[Dict] = []
        self._update_counts = {
            "hit": 0,
            "miss": 0,
            "refresh": 0,
            "fail": 0,
            "stale_fallback": 0,
            "quality_fail": 0,
        }
        self._last_self_check: Optional[Dict] = None

        # 生命周期
        self._self_check_timer: Optional[threading.Timer] = None
        self._shutdown = False

        # 启动定时自检
        self._schedule_self_check()

        self._obs.log("INFO", "DataPlatformService initialized", "DataPlatformService")

    # ═══════════════════════════════════════
    # 生命周期管理
    # ═══════════════════════════════════════

    def _schedule_self_check(self):
        """调度下次自检（30分钟后）"""
        if self._shutdown:
            return
        self._self_check_timer = threading.Timer(
            SELF_CHECK_INTERVAL, self._run_self_check
        )
        self._self_check_timer.daemon = True
        self._self_check_timer.start()

    def _run_self_check(self):
        """运行自检并生成报告"""
        try:
            report = self.run_self_check()
            self._last_self_check = report
            self._obs.log(
                "INFO",
                f"Self-check completed: {report['quality_checks']}",
                "DataPlatformService",
            )
        except Exception as e:
            self._obs.log("ERROR", f"Self-check failed: {e}", "DataPlatformService")
        finally:
            self._schedule_self_check()

    def shutdown(self):
        """关闭服务，取消定时器"""
        self._shutdown = True
        if self._self_check_timer is not None:
            self._self_check_timer.cancel()
        self._obs.log("INFO", "DataPlatformService shutdown", "DataPlatformService")

    # ═══════════════════════════════════════
    # 缓存辅助（最小锁临界区）
    # ═══════════════════════════════════════

    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """从缓存获取，命中时记录统计"""
        value = self._cache.get(cache_key)
        if value is not None:
            with self._lock:
                self._update_counts["hit"] += 1
            self._obs.record_counter(
                "data_platform_cache_hit", 1, {"key": cache_key.split(":")[0]}
            )
        return value

    def _set_cache(self, cache_key: str, value: Any, ttl: int) -> None:
        """写入缓存，记录更新时间（锁保护计数器）"""
        self._cache.set(cache_key, value, ttl_seconds=ttl)
        with self._lock:
            self._last_update[cache_key] = datetime.now()
            self._update_counts["refresh"] += 1

    def _fetch_with_cache(
        self,
        cache_key: str,
        fetch_func,
        ttl: int,
        data_type: str,
        symbol: str = "",
        force_refresh: bool = False,
        max_retries: int = 1,
    ) -> Tuple[Optional[Any], Optional[Dict], bool]:
        """
        带缓存、质量检查和重试的获取逻辑

        Returns:
            (data, quality_result, is_stale)
            is_stale=True 表示返回的是降级后的过期缓存数据
        """
        # ── 1. 尝试缓存 ──
        if not force_refresh:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                quality = self.check_data_quality(data_type, cached, symbol, cache_key)
                if quality["overall_passed"]:
                    return cached, quality, False
                self._obs.log(
                    "WARN",
                    f"Cached data quality failed: {cache_key}",
                    "DataPlatformService",
                )
                with self._lock:
                    self._update_counts["quality_fail"] += 1

        # ── 2. 获取新数据（无锁，允许慢 IO）──
        with self._lock:
            self._update_counts["miss"] += 1
        self._obs.record_counter(
            "data_platform_cache_miss", 1, {"key": cache_key.split(":")[0]}
        )

        data: Optional[Any] = None
        for attempt in range(max_retries + 1):
            try:
                data = fetch_func()
                if data is not None:
                    break
            except Exception as e:
                self._obs.log(
                    "ERROR",
                    f"Fetch failed [{attempt + 1}/{max_retries + 1}] {cache_key}: {e}",
                    "DataPlatformService",
                )
                if attempt < max_retries:
                    time.sleep(0.3)

        # ── 3. 质量检查并写入缓存 ──
        if data is not None:
            quality = self.check_data_quality(data_type, data, symbol, cache_key)
            if quality["overall_passed"]:
                self._set_cache(cache_key, data, ttl)
                return data, quality, False
            else:
                self._obs.log(
                    "WARN",
                    f"Quality failed for {cache_key}: {quality['issues']}",
                    "DataPlatformService",
                )
                with self._lock:
                    self._update_counts["quality_fail"] += 1
                # 降级：没有过期缓存时，仍然返回当前数据（总比没有数据好）
                if not force_refresh:
                    cached = self._get_from_cache(cache_key)
                    if cached is None:
                        self._obs.log(
                            "INFO",
                            f"Returning fresh data despite quality issues for {cache_key}",
                            "DataPlatformService",
                        )
                        return data, quality, True

        # ── 4. 降级到过期缓存 ──
        if not force_refresh:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                self._obs.log(
                    "INFO",
                    f"Stale fallback for {cache_key}",
                    "DataPlatformService",
                )
                with self._lock:
                    self._update_counts["stale_fallback"] += 1
                self._obs.record_counter(
                    "data_platform_stale_fallback", 1, {"key": cache_key.split(":")[0]}
                )
                quality = self.check_data_quality(data_type, cached, symbol, cache_key)
                return cached, quality, True

        # ── 5. 彻底失败 ──
        with self._lock:
            self._update_counts["fail"] += 1
        self._obs.record_counter(
            "data_platform_fetch_fail", 1, {"key": cache_key.split(":")[0]}
        )
        return None, None, False

    # ═══════════════════════════════════════
    # 数据质量检查（四大维度）
    # ═══════════════════════════════════════

    def _check_completeness(self, data_type: str, data: Any) -> Tuple[bool, List[str]]:
        """完整性检查：空值率、必要字段缺失"""
        issues: List[str] = []

        if data is None:
            return False, ["Data is None"]

        if data_type in ("ohlcv", "indicators"):
            if not isinstance(data, pd.DataFrame):
                return False, ["Expected DataFrame"]
            if len(data) == 0:
                return False, ["Empty DataFrame"]
            required = {"date", "code", "open", "high", "low", "close", "volume"}
            missing = required - set(data.columns)
            if missing:
                issues.append(f"Missing columns: {missing}")
            total_cells = data.shape[0] * data.shape[1]
            if total_cells > 0:
                null_rate = data.isnull().sum().sum() / total_cells
                if null_rate > 0.30:
                    issues.append(f"Null rate too high: {null_rate:.2%}")

        elif data_type == "stock_list":
            if not isinstance(data, pd.DataFrame):
                return False, ["Expected DataFrame"]
            if len(data) == 0:
                return False, ["Empty stock list"]
            required = {"code", "name"}
            missing = required - set(data.columns)
            if missing:
                issues.append(f"Missing columns: {missing}")

        elif data_type == "market_overview":
            if not isinstance(data, dict):
                return False, ["Expected dict"]
            if not data:
                return False, ["Empty dict"]
            required = {"advancing", "declining", "total_valid"}
            missing = required - set(data.keys())
            if missing:
                issues.append(f"Missing keys: {missing}")

        elif data_type in ("quote", "index"):
            if isinstance(data, list):
                if len(data) == 0:
                    issues.append("Empty quote list")
            elif data is None:
                issues.append("Quote is None")
            elif isinstance(data, StandardQuote):
                if data.close <= 0:
                    issues.append("Invalid close price")

        return len(issues) == 0, issues

    def _check_consistency(self, data_type: str, data: Any, symbol: str = "") -> Tuple[bool, List[str]]:
        """一致性检查：价格范围、时间连续性、涨跌一致性"""
        issues: List[str] = []

        if data_type in ("ohlcv", "indicators"):
            if not isinstance(data, pd.DataFrame) or len(data) == 0:
                return True, []
            df = data.copy()
            for col in ("open", "high", "low", "close"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 收盘价在 [low, high] 范围内
            if all(c in df.columns for c in ("close", "low", "high")):
                invalid = ~(
                    (df["close"] >= df["low"] - PRICE_TOL)
                    & (df["close"] <= df["high"] + PRICE_TOL)
                )
                if invalid.any():
                    issues.append(f"Close out of [low, high] in {invalid.sum()} rows")

            # 开盘价在 [low, high] 范围内
            if all(c in df.columns for c in ("open", "low", "high")):
                invalid = ~(
                    (df["open"] >= df["low"] - PRICE_TOL)
                    & (df["open"] <= df["high"] + PRICE_TOL)
                )
                if invalid.any():
                    issues.append(f"Open out of [low, high] in {invalid.sum()} rows")

            # low <= high
            if all(c in df.columns for c in ("low", "high")):
                invalid = ~(df["low"] <= df["high"] + PRICE_TOL)
                if invalid.any():
                    issues.append(f"low > high in {invalid.sum()} rows")

            # 时间连续性：检查是否有超过 7 天的断档（根据数据中位数间隔动态调整阈值）
            if "date" in df.columns and len(df) > 1:
                try:
                    dates = pd.to_datetime(df["date"]).sort_values()
                    gaps = dates.diff().dt.days.dropna()
                    if len(gaps) > 0:
                        median_gap = gaps.median()
                        # 动态阈值：中位数间隔的 3 倍，但至少 7 天
                        threshold = max(median_gap * 3, 7)
                        large_gaps = gaps[gaps > threshold]
                        if len(large_gaps) > 0:
                            issues.append(f"Large date gaps (>{threshold:.0f}d): {len(large_gaps)}")
                except Exception:
                    pass

            # 涨跌一致性（change_pct 与 (close-open)/open 对比）
            if all(c in df.columns for c in ("change_pct", "open", "close")):
                try:
                    calculated = (df["close"] - df["open"]) / df["open"] * 100
                    diff = (df["change_pct"] - calculated).abs()
                    inconsistent = diff > 0.5
                    if inconsistent.any():
                        issues.append(f"change_pct inconsistent in {inconsistent.sum()} rows")
                except Exception:
                    pass

        elif data_type == "market_overview":
            if isinstance(data, dict):
                adv = data.get("advancing", 0)
                dec = data.get("declining", 0)
                flat = data.get("flat", 0)
                total = data.get("total_valid", 0)
                if total > 0 and adv + dec + flat != total:
                    issues.append(f"Sum mismatch: {adv}+{dec}+{flat} != {total}")

        elif data_type in ("quote", "index"):
            items = data if isinstance(data, list) else [data] if data is not None else []
            for item in items:
                if isinstance(item, StandardQuote):
                    if item.low > item.high + PRICE_TOL:
                        issues.append(
                            f"Quote low({item.low}) > high({item.high}) for {item.symbol}"
                        )
                    if item.close < item.low - PRICE_TOL or item.close > item.high + PRICE_TOL:
                        issues.append(f"Quote close out of range for {item.symbol}")
                    if item.open < item.low - PRICE_TOL or item.open > item.high + PRICE_TOL:
                        issues.append(f"Quote open out of range for {item.symbol}")

        return len(issues) == 0, issues

    def _check_timeliness(self, data_type: str, data: Any, cache_key: str = "") -> Tuple[bool, List[str]]:
        """时效性检查：实时数据5分钟内，分钟数据1分钟内，日数据3天内"""
        issues: List[str] = []
        now = datetime.now()

        # 根据缓存键判断数据类型
        is_minute = False
        is_daily = False
        if cache_key and "minute" in cache_key:
            is_minute = True
        elif cache_key and any(p in cache_key for p in (":daily", ":weekly", ":monthly", ":quarterly", ":yearly")):
            is_daily = True

        if data_type in ("market_overview", "quote", "index", "hotspot"):
            # 实时行情：5分钟内有效
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, StandardQuote) and first.timestamp:
                    age_seconds = (now - first.timestamp).total_seconds()
                    if age_seconds > 300:
                        issues.append(f"Quote data too old: {age_seconds:.0f}s")
            elif isinstance(data, StandardQuote) and data.timestamp:
                age_seconds = (now - data.timestamp).total_seconds()
                if age_seconds > 300:
                    issues.append(f"Quote data too old: {age_seconds:.0f}s")

        elif data_type == "ohlcv":
            if isinstance(data, pd.DataFrame) and len(data) > 0 and "date" in data.columns:
                latest_date = data["date"].iloc[-1]
                try:
                    latest = pd.to_datetime(str(latest_date))
                    if is_minute:
                        # 分钟数据：最新行在 1 分钟内
                        if (now - latest).total_seconds() > 120:
                            issues.append(f"Minute data too old: {latest_date}")
                    else:
                        # 日/周/月线：最新行在 3 天内（非交易日考虑）
                        if (now - latest).days > 3:
                            issues.append(f"Daily/Weekly/Monthly data too old: {latest_date}")
                except Exception:
                    pass

        return len(issues) == 0, issues

    def _check_outliers(self, data_type: str, data: Any, symbol: str = "") -> Tuple[bool, List[str]]:
        """异常值检查：涨跌停、负价格、成交量异常"""
        issues: List[str] = []
        failed = False

        if data_type in ("ohlcv", "indicators"):
            if not isinstance(data, pd.DataFrame) or len(data) == 0:
                return True, []
            df = data.copy()
            for col in ("open", "high", "low", "close"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 负价格 → 严重失败
            for col in ("open", "high", "low", "close"):
                if col in df.columns:
                    neg = df[col] < 0
                    if neg.any():
                        issues.append(f"Negative {col} in {neg.sum()} rows")
                        failed = True

            # 单日涨跌幅极端值
            if "close" in df.columns and len(df) > 1:
                try:
                    df_sorted = df.sort_values("date") if "date" in df.columns else df
                    prev_close = df_sorted["close"].shift(1)
                    change_pct = (df_sorted["close"] - prev_close) / prev_close * 100

                    # 科创板/创业板/北交所 40%，其他主板 20%
                    limit = (
                        40.0
                        if symbol and symbol.startswith(HIGH_LIMIT_PREFIXES)
                        else 20.0
                    )
                    extreme = change_pct.abs() > limit
                    if extreme.any():
                        issues.append(f"Extreme change > {limit}% in {extreme.sum()} rows")
                except Exception:
                    pass

            # 成交量 = 0 但价格变化
            if "volume" in df.columns and "close" in df.columns and len(df) > 1:
                try:
                    df_sorted = df.sort_values("date") if "date" in df.columns else df
                    vol_zero = df_sorted["volume"].fillna(0) == 0
                    price_changed = df_sorted["close"].diff().abs() > 0
                    if (vol_zero & price_changed).any():
                        issues.append(
                            f"Volume=0 but price changed in {(vol_zero & price_changed).sum()} rows"
                        )
                except Exception:
                    pass

        elif data_type in ("quote", "index"):
            items = data if isinstance(data, list) else [data] if data is not None else []
            for item in items:
                if isinstance(item, StandardQuote):
                    if (
                        item.close < 0
                        or item.open < 0
                        or item.high < 0
                        or item.low < 0
                    ):
                        issues.append(f"Negative price for {item.symbol}")
                        failed = True

        return not failed, issues

    def check_data_quality(
        self,
        data_type: str,
        data: Any,
        symbol: str = "",
        cache_key: str = "",
    ) -> Dict[str, Any]:
        """
        数据质量检查 - 公共接口

        四大维度：
        1. 完整性（Completeness）
        2. 一致性（Consistency）
        3. 时效性（Timeliness）
        4. 异常值（Outliers）

        Args:
            data_type: 数据类型 (ohlcv / indicators / stock_list / market_overview / quote / index)
            data: 待检查数据
            symbol: 股票代码（用于判断涨跌停限制）
            cache_key: 缓存键（用于时效性检查）

        Returns:
            结构化质量检查结果字典
        """
        result = DataQualityResult()

        result.completeness_passed, result.completeness_issues = self._check_completeness(
            data_type, data
        )
        result.consistency_passed, result.consistency_issues = self._check_consistency(
            data_type, data, symbol
        )
        result.timeliness_passed, result.timeliness_issues = self._check_timeliness(
            data_type, data, cache_key
        )
        result.outliers_passed, result.outliers_issues = self._check_outliers(
            data_type, data, symbol
        )

        result.overall_passed = (
            result.completeness_passed
            and result.consistency_passed
            and result.timeliness_passed
            and result.outliers_passed
        )

        # 记录到历史（保留最近 1000 条）
        quality_record = {
            "timestamp": datetime.now().isoformat(),
            "data_type": data_type,
            "symbol": symbol,
            "passed": result.overall_passed,
            "issues": result.to_dict()["issues"],
        }
        with self._lock:
            self._quality_history.append(quality_record)
            if len(self._quality_history) > 1000:
                self._quality_history = self._quality_history[-1000:]

        # 记录可观测性指标
        self._obs.record_counter(
            "data_platform_quality_check",
            1,
            {"type": data_type, "result": "pass" if result.overall_passed else "fail"},
        )

        return result.to_dict()

    # ═══════════════════════════════════════
    # 数据获取接口（按缓存策略分类）
    # ═══════════════════════════════════════

    # ── 实时缓存（5分钟 TTL）──

    def get_market_overview(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取市场概览（5分钟缓存）

        Returns:
            含上涨/下跌家数、涨停/跌停、热点板块等的字典
        """
        cache_key = "rt:market_overview"

        def _fetch():
            return self._provider.fetch_market_overview()

        data, quality, stale = self._fetch_with_cache(
            cache_key, _fetch, RT_TTL, "market_overview", force_refresh=force_refresh
        )

        if data is not None:
            self._obs.log(
                "INFO",
                f"Market overview fetched (stale={stale})",
                "DataPlatformService",
            )
        return data

    def get_hotspots(self, force_refresh: bool = False) -> Optional[List[Dict]]:
        """
        获取热点板块数据（从市场概览中提取，5分钟缓存）

        Returns:
            热点板块列表
        """
        overview = self.get_market_overview(force_refresh=force_refresh)
        if overview is not None and isinstance(overview, dict):
            return overview.get("hotspots")
        return None

    def get_index_quotes(
        self,
        symbols: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> List[StandardQuote]:
        """
        获取指数实时行情（5分钟缓存）

        Args:
            symbols: 指数代码列表，默认四大指数
            force_refresh: 强制刷新

        Returns:
            StandardQuote 列表
        """
        if symbols is None:
            symbols = DEFAULT_INDEX_SYMBOLS

        results: List[StandardQuote] = []
        for sym in symbols:
            cache_key = f"rt:index:{sym.lower()}"

            def _fetch(s: str = sym):
                quotes = self._provider.fetch_realtime_quotes([s])
                if quotes:
                    return [q for q in quotes if q.symbol.lower() == s.lower()]
                return []

            data, quality, stale = self._fetch_with_cache(
                cache_key,
                lambda s=sym: _fetch(s),
                RT_TTL,
                "index",
                symbol=sym,
                force_refresh=force_refresh,
            )

            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, StandardQuote):
                results.append(data)

        return results

    def get_stock_quote(self, symbol: str, force_refresh: bool = False) -> Optional[StandardQuote]:
        """
        获取个股实时行情（5分钟缓存）

        降级策略：实时接口失败 → 使用最新日 K 数据构造 Quote

        Args:
            symbol: 股票代码（如 000001、600519）
            force_refresh: 强制刷新

        Returns:
            StandardQuote 或 None
        """
        cache_key = f"rt:quote:{symbol}"

        def _fetch():
            quotes = self._provider.fetch_realtime_quotes([symbol])
            if quotes:
                for q in quotes:
                    if q.symbol == symbol:
                        return q
            return None

        data, quality, stale = self._fetch_with_cache(
            cache_key, _fetch, RT_TTL, "quote", symbol=symbol, force_refresh=force_refresh
        )

        if data is not None and isinstance(data, StandardQuote):
            return data

        # ── 降级：使用日 K 最新数据 ──
        self._obs.log(
            "INFO",
            f"Fallback to OHLCV for quote {symbol}",
            "DataPlatformService",
        )
        df = self.get_ohlcv(symbol, period="daily", adjust="qfq")
        if df is not None and len(df) > 0:
            try:
                latest = df.iloc[-1]
                quote = StandardQuote(
                    symbol=symbol,
                    name=None,
                    timestamp=datetime.now(),
                    open=float(latest["open"]),
                    high=float(latest["high"]),
                    low=float(latest["low"]),
                    close=float(latest["close"]),
                    volume=int(latest["volume"]),
                    amount=float(latest.get("amount", 0)) if "amount" in latest else None,
                    source="mootdx-offline",
                    freq="1d",
                )
                return quote
            except Exception as e:
                self._obs.log(
                    "WARN",
                    f"Quote fallback failed for {symbol}: {e}",
                    "DataPlatformService",
                )

        return None

    # ── 日更新缓存（24小时 TTL）──

    def get_stock_list(self, force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        获取全市场股票列表（24小时缓存）

        Args:
            force_refresh: 强制刷新

        Returns:
            DataFrame[code, name, ...] 或 None
        """
        cache_key = "daily:stock_list"

        def _fetch():
            return self._provider.fetch_stock_list()

        data, quality, stale = self._fetch_with_cache(
            cache_key, _fetch, STOCK_LIST_TTL, "stock_list", force_refresh=force_refresh
        )
        return data

    def get_ohlcv(
        self,
        symbol: str,
        start_date: str = "",
        end_date: str = "",
        period: str = "daily",
        adjust: str = "qfq",
        force_refresh: bool = False,
    ) -> Optional[pd.DataFrame]:
        """
        获取 K 线数据（按周期自动选择 TTL 缓存）

        Args:
            symbol: 股票代码（如 600519、000001）或指数代码（sh000001）
            start_date: 起始日期（YYYYMMDD），默认全量
            end_date: 结束日期
            period: minute / daily / weekly / monthly / quarterly / yearly
            adjust: qfq(前复权) / hfq(后复权) / none(不复权)
            force_refresh: 强制刷新

        Returns:
            DataFrame[date, code, open, high, low, close, volume, amount]
        """
        # 根据周期选择 TTL
        ttl = PERIOD_TTL_MAP.get(period, DAILY_TTL)
        cache_key = f"ohlcv:{period}:{symbol}:{adjust}"

        def _fetch():
            # 周/月/季/年 基于日数据聚合（mootdx StdReader 不支持 weekly/monthly）
            if period in ("weekly", "monthly", "quarterly", "yearly"):
                df = self._provider.fetch_ohlcv(
                    symbol, start_date, end_date, "daily", adjust
                )
                if df is None or len(df) == 0:
                    return None
                return self._aggregate_period(df, period)
            return self._provider.fetch_ohlcv(
                symbol, start_date, end_date, period, adjust
            )

        data, quality, stale = self._fetch_with_cache(
            cache_key,
            _fetch,
            ttl,
            "ohlcv",
            symbol=symbol,
            force_refresh=force_refresh,
        )

        if isinstance(data, list):
            return pd.DataFrame(data)
        return data

    def _aggregate_period(
        self, df: pd.DataFrame, period: str
    ) -> pd.DataFrame:
        """
        将日K线数据聚合为周/月/季/年K线

        聚合规则：
          - open: 周期第一根K线的 open
          - high: 周期内 high 的最大值
          - low: 周期内 low 的最小值
          - close: 周期最后一根K线的 close
          - volume: 周期内 volume 的总和
          - amount: 周期内 amount 的总和
        """
        df = df.copy()
        # 确保 date 列是 datetime 类型
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df[df["date"].notna()].sort_values("date").reset_index(drop=True)

        if period == "weekly":
            # 按周一到周日分组（以每周一作为该周标识）
            df["period"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
        elif period == "monthly":
            df["period"] = df["date"].dt.to_period("M").apply(lambda r: r.start_time)
        elif period == "quarterly":
            df["period"] = df["date"].dt.to_period("Q").apply(lambda r: r.start_time)
        elif period == "yearly":
            df["period"] = df["date"].dt.to_period("Y").apply(lambda r: r.start_time)
        else:
            return df

        agg_df = df.groupby("period").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            amount=("amount", "sum"),
        ).reset_index()

        agg_df = agg_df.rename(columns={"period": "date"})
        agg_df["date"] = agg_df["date"].dt.strftime("%Y%m%d")

        # 保留 code 列（取第一个值）
        if "code" in df.columns:
            code_map = df.groupby("period")["code"].first().reset_index()
            code_map = code_map.rename(columns={"period": "date"})
            code_map["date"] = code_map["date"].dt.strftime("%Y%m%d")
            agg_df = agg_df.merge(code_map, on="date", how="left")

        # 确保列顺序和原始一致
        cols = ["date", "code", "open", "high", "low", "close", "volume", "amount"]
        available = [c for c in cols if c in agg_df.columns]
        return agg_df[available].sort_values("date").reset_index(drop=True)

    def get_ohlcv_multi_period(
        self,
        symbol: str,
        periods: List[str],
        adjust: str = "qfq",
    ) -> Dict[str, Optional[pd.DataFrame]]:
        """
        批量获取多周期 K 线数据（用于对比分析）

        Returns:
            {period: DataFrame} 字典
        """
        results = {}
        for period in periods:
            results[period] = self.get_ohlcv(symbol, period=period, adjust=adjust)
        return results

    def get_indicators(
        self,
        symbol: str,
        period: str = "daily",
        adjust: str = "qfq",
        force_refresh: bool = False,
    ) -> Optional[pd.DataFrame]:
        """
        获取技术指标（按周期自动选择 TTL 缓存）

        计算 MA / KDJ / MACD / RSI / BOLL / OBV / DMI

        Args:
            symbol: 股票代码
            period: minute / daily / weekly / monthly / quarterly / yearly
            adjust: qfq / hfq / none
            force_refresh: 强制刷新

        Returns:
            含指标列的 DataFrame
        """
        # 根据周期选择 TTL
        ttl = PERIOD_TTL_MAP.get(period, DAILY_TTL)
        cache_key = f"indicators:{period}:{symbol}:{adjust}"

        # 直接检查缓存（不走 _fetch_with_cache，因为指标计算是二次加工）
        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                if isinstance(cached, pd.DataFrame):
                    cached_df = cached
                elif isinstance(cached, list):
                    cached_df = pd.DataFrame(cached)
                else:
                    cached_df = None
                
                # 列完整性检查：确保包含所有指标列（OBV、DMI等）
                if cached_df is not None:
                    required_indicator_cols = {"obv", "dmi_pdi", "dmi_mdi", "dmi_adx"}
                    if required_indicator_cols.issubset(set(cached_df.columns)):
                        return cached_df
                    else:
                        # 缓存数据不完整（旧版本缺少新指标列），删除旧缓存
                        self._cache.delete(cache_key)
                        self._obs.log(
                            "INFO",
                            f"Cached indicators missing required columns for {symbol}, recalculating",
                            "DataPlatformService",
                        )

        # 获取底层 OHLCV
        df = self.get_ohlcv(symbol, period=period, adjust=adjust, force_refresh=force_refresh)
        if df is None or len(df) == 0:
            return None

        # 计算指标
        try:
            indicators_df = calculate_all_indicators(df, period=period)
        except Exception as e:
            self._obs.log(
                "ERROR",
                f"Indicator calculation failed for {symbol} ({period}): {e}",
                "DataPlatformService",
            )
            return None

        # 写入缓存
        self._cache.set(cache_key, indicators_df.to_dict("records"), ttl_seconds=ttl)
        return indicators_df

    def get_latest_indicators(
        self, symbol: str, period: str = "daily", adjust: str = "qfq"
    ) -> Optional[Dict[str, Any]]:
        """
        获取最新一行的技术指标值

        Args:
            symbol: 股票代码
            period: minute / daily / weekly / monthly
            adjust: qfq / hfq / none

        Returns:
            最新指标字典或 None
        """
        df = self.get_indicators(symbol, period=period, adjust=adjust)
        if df is None or len(df) == 0:
            return None
        try:
            from backend.services.indicators import get_latest_indicators
            return get_latest_indicators(df)
        except Exception:
            return None

    def get_quarterly_kline(
        self, symbol: str, adjust: str = "qfq"
    ) -> Optional[pd.DataFrame]:
        """
        获取季度 K 线（基于月数据聚合）

        Args:
            symbol: 股票代码
            adjust: qfq / hfq / none

        Returns:
            DataFrame[quarter, code, open, high, low, close, volume, amount]
        """
        cache_key = f"ohlcv:quarterly:{symbol}:{adjust}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return pd.DataFrame(cached) if isinstance(cached, list) else cached

        # 从月数据聚合
        monthly_df = self.get_ohlcv(symbol, period="monthly", adjust=adjust)
        if monthly_df is None or len(monthly_df) == 0:
            return None

        # 添加季度列
        monthly_df["date"] = pd.to_datetime(monthly_df["date"], errors="coerce")
        monthly_df["quarter"] = monthly_df["date"].dt.to_period("Q")

        # 按季度聚合
        quarterly = monthly_df.groupby("quarter").agg({
            "code": "first",
            "open": "first",      # 季度第一月开盘价
            "high": "max",        # 季度最高
            "low": "min",         # 季度最低
            "close": "last",      # 季度最后一月收盘价
            "volume": "sum",      # 季度总成交量
            "amount": "sum",      # 季度总成交额
        }).reset_index()
        quarterly["date"] = quarterly["quarter"].astype(str)
        quarterly = quarterly.drop(columns=["quarter"])

        # 缓存
        self._cache.set(cache_key, quarterly.to_dict("records"), ttl_seconds=DAILY_TTL)
        return quarterly

    def get_yearly_kline(
        self, symbol: str, adjust: str = "qfq"
    ) -> Optional[pd.DataFrame]:
        """
        获取年度 K 线（基于月数据聚合）

        Args:
            symbol: 股票代码
            adjust: qfq / hfq / none

        Returns:
            DataFrame[year, code, open, high, low, close, volume, amount]
        """
        cache_key = f"ohlcv:yearly:{symbol}:{adjust}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return pd.DataFrame(cached) if isinstance(cached, list) else cached

        # 从月数据聚合
        monthly_df = self.get_ohlcv(symbol, period="monthly", adjust=adjust)
        if monthly_df is None or len(monthly_df) == 0:
            return None

        # 添加年度列
        monthly_df["date"] = pd.to_datetime(monthly_df["date"], errors="coerce")
        monthly_df["year"] = monthly_df["date"].dt.to_period("Y")

        # 按年度聚合
        yearly = monthly_df.groupby("year").agg({
            "code": "first",
            "open": "first",      # 年度第一月开盘价
            "high": "max",        # 年度最高
            "low": "min",         # 年度最低
            "close": "last",      # 年度最后一月收盘价
            "volume": "sum",      # 年度总成交量
            "amount": "sum",      # 年度总成交额
        }).reset_index()
        yearly["date"] = yearly["year"].astype(str)
        yearly = yearly.drop(columns=["year"])

        # 缓存
        self._cache.set(cache_key, yearly.to_dict("records"), ttl_seconds=DAILY_TTL)
        return yearly

    def get_latest_indicators(
        self, symbol: str, period: str = "daily", adjust: str = "qfq"
    ) -> Dict[str, Any]:
        """
        获取最新一行的指标值（便捷接口）

        Returns:
            指标字典（如 {"ma5": 10.5, "kdj_k": 45.2, ...}）
        """
        df = self.get_indicators(symbol, period, adjust)
        if df is None or len(df) == 0:
            return {}
        return get_latest_indicators(df)

    # ═══════════════════════════════════════
    # 自检与统计
    # ═══════════════════════════════════════

    def run_self_check(self) -> Dict[str, Any]:
        """
        运行数据质量自检并生成报告

        报告格式：
        {
          "timestamp": "2026-06-23T23:00:00",
          "data_sources": {
            "market_overview": {"status": "ok", "last_update": "...", "records": 4130},
            ...
          },
          "quality_checks": {
            "completeness": {"passed": 10, "failed": 0},
            ...
          },
          "cache_stats": {"hit_rate": 0.85, "l1_size": 50, "l3_count": 200}
        }

        Returns:
            JSON 格式的自检报告字典
        """
        now = datetime.now()
        report: Dict[str, Any] = {
            "timestamp": now.isoformat(),
            "data_sources": {},
            "quality_checks": {
                "completeness": {"passed": 0, "failed": 0},
                "consistency": {"passed": 0, "failed": 0},
                "timeliness": {"passed": 0, "failed": 0},
                "outliers": {"passed": 0, "failed": 0},
            },
            "cache_stats": self._cache.get_stats(),
        }

        def _check_source(name: str, cache_key: str, data_type: str, symbol: str = ""):
            """检查单个数据源并更新报告"""
            cached = self._cache.get(cache_key)
            status = "ok"
            last_update = self._last_update.get(cache_key)
            records = 0

            if cached is None:
                status = "missing"
            else:
                quality = self.check_data_quality(data_type, cached, symbol, cache_key)
                for check in ("completeness", "consistency", "timeliness", "outliers"):
                    if quality[check]["passed"]:
                        report["quality_checks"][check]["passed"] += 1
                    else:
                        report["quality_checks"][check]["failed"] += 1

                if not quality["overall_passed"]:
                    status = "quality_fail"
                elif last_update and (now - last_update).total_seconds() > DAILY_TTL:
                    status = "stale"

                if isinstance(cached, pd.DataFrame):
                    records = len(cached)
                elif isinstance(cached, dict):
                    records = cached.get("total_valid", len(cached))
                elif isinstance(cached, list):
                    records = len(cached)

            report["data_sources"][name] = {
                "status": status,
                "last_update": last_update.isoformat() if last_update else None,
                "records": records,
            }

        # 检查已知数据源
        _check_source("market_overview", "rt:market_overview", "market_overview")
        _check_source("stock_list", "daily:stock_list", "stock_list")

        # 指数行情合并检查
        index_items: List[Any] = []
        oldest_update: Optional[datetime] = None
        for idx in DEFAULT_INDEX_SYMBOLS:
            ck = f"rt:index:{idx}"
            cached = self._cache.get(ck)
            if cached:
                if isinstance(cached, list):
                    index_items.extend(cached)
                else:
                    index_items.append(cached)
            lu = self._last_update.get(ck)
            if lu and (oldest_update is None or lu < oldest_update):
                oldest_update = lu

        if index_items:
            quality = self.check_data_quality("index", index_items, "", "rt:index")
            for check in ("completeness", "consistency", "timeliness", "outliers"):
                if quality[check]["passed"]:
                    report["quality_checks"][check]["passed"] += 1
                else:
                    report["quality_checks"][check]["failed"] += 1

            status = "ok" if quality["overall_passed"] else "quality_fail"
            if oldest_update and (now - oldest_update).total_seconds() > RT_TTL:
                status = "stale"

            report["data_sources"]["index_quotes"] = {
                "status": status,
                "last_update": oldest_update.isoformat() if oldest_update else None,
                "records": len(index_items),
            }
        else:
            report["data_sources"]["index_quotes"] = {
                "status": "missing",
                "last_update": None,
                "records": 0,
            }

        self._last_self_check = report
        self._obs.log("INFO", "Self-check report generated", "DataPlatformService")
        return report

    def get_stats(self) -> Dict[str, Any]:
        """
        获取数据中台统计信息

        Returns:
            统计字典，含缓存命中率、质量历史、更新计数等
        """
        cache_stats = self._cache.get_stats()

        total_requests = (
            self._update_counts["hit"]
            + self._update_counts["miss"]
            + self._update_counts["fail"]
        )
        hit_rate = self._update_counts["hit"] / max(total_requests, 1)

        # 最近 100 次质量检查统计
        recent_quality = {"total": 0, "passed": 0, "failed": 0}
        with self._lock:
            for q in self._quality_history[-100:]:
                recent_quality["total"] += 1
                if q["passed"]:
                    recent_quality["passed"] += 1
                else:
                    recent_quality["failed"] += 1

        return {
            "timestamp": datetime.now().isoformat(),
            "cache_stats": cache_stats,
            "update_counts": self._update_counts.copy(),
            "hit_rate": round(hit_rate, 4),
            "quality_history": recent_quality,
            "last_self_check": self._last_self_check,
            "data_sources_tracked": len(self._last_update),
        }

    def clear_cache(self, pattern: Optional[str] = None):
        """
        清空缓存

        Args:
            pattern: 可选的 key 前缀过滤，None 表示全部清空
        """
        if pattern is None:
            self._cache.clear()
            with self._lock:
                self._last_update.clear()
            self._obs.log("INFO", "Cache cleared (all)", "DataPlatformService")
        else:
            with self._lock:
                keys_to_delete = [k for k in self._last_update if k.startswith(pattern)]
                for k in keys_to_delete:
                    self._cache.delete(k)
                    self._last_update.pop(k, None)
            self._obs.log(
                "INFO", f"Cache cleared (pattern={pattern})", "DataPlatformService"
            )

    def refresh_all(self):
        """强制刷新所有核心数据源"""
        self._obs.log("INFO", "Refreshing all data sources...", "DataPlatformService")
        self.get_market_overview(force_refresh=True)
        self.get_stock_list(force_refresh=True)
        self.get_index_quotes(DEFAULT_INDEX_SYMBOLS, force_refresh=True)
        self._obs.log("INFO", "All data sources refreshed", "DataPlatformService")


# ═══════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════

_data_platform_instance: Optional[DataPlatformService] = None
_data_platform_lock = threading.Lock()


def get_data_platform_service(tdxdir: str = "D:/TDX") -> DataPlatformService:
    """获取全局 DataPlatformService 实例（线程安全单例）"""
    global _data_platform_instance
    if _data_platform_instance is None:
        with _data_platform_lock:
            if _data_platform_instance is None:
                _data_platform_instance = DataPlatformService(tdxdir=tdxdir)
    return _data_platform_instance


# ═══════════════════════════════════════
# 独立测试
# ═══════════════════════════════════════

if __name__ == "__main__":
    _project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    print("=" * 60)
    print("DataPlatformService 独立测试")
    print("=" * 60)

    platform = DataPlatformService()

    # 1. 股票列表
    print("\n[1] get_stock_list")
    stock_list = platform.get_stock_list()
    if stock_list is not None:
        print(f"  Records: {len(stock_list)}")
        print(f"  Columns: {list(stock_list.columns)}")
    else:
        print("  No stock list available (data source may be offline)")

    # 2. 市场概览
    print("\n[2] get_market_overview")
    overview = platform.get_market_overview()
    if overview is not None:
        print(f"  Keys: {list(overview.keys())}")
        print(f"  Total valid: {overview.get('total_valid')}")
        hotspots = overview.get("hotspots", [])
        print(f"  Hotspots count: {len(hotspots)}")
    else:
        print("  No market overview available (data source may be offline)")

    # 3. 热点板块
    print("\n[3] get_hotspots")
    hotspots = platform.get_hotspots()
    if hotspots is not None:
        print(f"  Count: {len(hotspots)}")
        if hotspots:
            print(f"  Top: {hotspots[0]}")
    else:
        print("  No hotspots available")

    # 4. 指数行情
    print("\n[4] get_index_quotes")
    index_quotes = platform.get_index_quotes()
    print(f"  Count: {len(index_quotes)}")
    for q in index_quotes:
        print(f"  {q.symbol}: {q.close} (vol={q.volume})")

    # 5. 个股行情
    print("\n[5] get_stock_quote")
    quote = platform.get_stock_quote("000001")
    if quote:
        print(f"  {quote.symbol}: {quote.close} (vol={quote.volume})")
    else:
        print("  No quote available")

    # 6. K 线
    print("\n[6] get_ohlcv")
    ohlcv = platform.get_ohlcv("000001", period="daily", adjust="qfq")
    if ohlcv is not None:
        print(f"  Shape: {ohlcv.shape}")
        print(f"  Columns: {list(ohlcv.columns)}")
        print(f"  Tail(3):\n{ohlcv.tail(3)}")
    else:
        print("  No OHLCV available")

    # 7. 指标
    print("\n[7] get_indicators")
    indicators = platform.get_indicators("000001", period="daily", adjust="qfq")
    if indicators is not None:
        print(f"  Shape: {indicators.shape}")
        indicator_cols = [
            c
            for c in indicators.columns
            if c not in ("date", "code", "open", "high", "low", "close", "volume", "amount")
        ]
        print(f"  Indicator columns: {indicator_cols}")
        print(f"  Latest indicators: {platform.get_latest_indicators('000001')}")
    else:
        print("  No indicators available")

    # 8. 数据质量检查
    print("\n[8] check_data_quality")
    if ohlcv is not None:
        quality = platform.check_data_quality("ohlcv", ohlcv, "000001")
        print(f"  Overall passed: {quality['overall_passed']}")
        print(f"  Issues: {quality['issues']}")
    else:
        print("  Skipped (no OHLCV data)")

    # 9. 自检报告
    print("\n[9] run_self_check")
    report = platform.run_self_check()
    print(f"  Report keys: {list(report.keys())}")
    print(f"  Quality checks: {report['quality_checks']}")
    print(f"  Data sources: {list(report['data_sources'].keys())}")

    # 10. 统计
    print("\n[10] get_stats")
    stats = platform.get_stats()
    print(f"  Hit rate: {stats['hit_rate']}")
    print(f"  Update counts: {stats['update_counts']}")
    print(f"  Quality history: {stats['quality_history']}")
    print(f"  Cache stats: {stats['cache_stats']}")

    # 11. 强制刷新
    print("\n[11] refresh_all")
    platform.refresh_all()
    print("  All sources refreshed")

    # 12. 清理
    print("\n[12] clear_cache")
    platform.clear_cache()
    print("  Cache cleared")

    # 关闭
    platform.shutdown()

    print("\n" + "=" * 60)
    print("所有测试完成")
    print("=" * 60)
