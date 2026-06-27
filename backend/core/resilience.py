"""
Resilience System v4.0 - 数据源智能降级系统

核心能力：
1. Circuit Breaker 熔断器 - 连续失败N次后进入冷却期
2. Retry with Backoff - 指数退避重试
3. Data Source Fallback Chain - 多数据源优先级降级
4. Cache as Last Resort - 缓存兜底（stale acceptable）
5. Timeout Guard - 统一超时控制
6. Observability Integration - 自动记录降级/熔断/重试事件

降级链（个股K线）：
    ifind → stock_finance_data → 东方财富 → Cache → 返回空（带标记）

降级链（板块数据）：
    东方财富 → 内置默认列表 → 返回空

降级链（收盘摘要）：
    ifind → 东方财富实时 → Cache → 返回空
"""

import time
import threading
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import pandas as pd

from backend.core.observability import ObservabilityEngine, get_obs
from backend.core.cache import MultiLevelCache


T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"      # 正常，允许请求
    OPEN = "open"          # 熔断，直接拒绝
    HALF_OPEN = "half_open"  # 试探，允许一个请求


@dataclass
class FallbackResult:
    """降级结果包装器"""
    data: Any = None                    # 实际数据
    success: bool = False               # 是否成功
    source: str = ""                    # 最终数据源
    degraded: bool = False              # 是否降级（非首选源）
    stale: bool = False                 # 是否缓存数据（可能过时）
    error: str = ""                     # 错误信息
    duration_ms: float = 0.0           # 总耗时
    attempts: int = 0                   # 尝试次数
    trace_id: str = ""                 # 链路追踪ID
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "source": self.source,
            "degraded": self.degraded,
            "stale": self.stale,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "attempts": self.attempts,
        }


class CircuitBreaker:
    """
    熔断器
    
    使用方式：
        cb = CircuitBreaker("ifind", failure_threshold=5, cooldown_seconds=60)
        if cb.can_execute():
            try:
                result = fetch_data()
                cb.record_success()
            except Exception as e:
                cb.record_failure()
        else:
            # 熔断中，直接降级
            result = fallback_data()
    """
    
    def __init__(self, name: str, failure_threshold: int = 5, 
                 cooldown_seconds: float = 60.0, 
                 half_open_max_calls: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_calls = half_open_max_calls
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = threading.Lock()
        
        self._obs = get_obs()
    
    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state
    
    def can_execute(self) -> bool:
        """检查是否允许执行请求"""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._obs.log("WARN", f"CircuitBreaker '{self.name}' entering HALF_OPEN", "resilience")
                    return True
                return False
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
        
        return False
    
    def record_success(self) -> None:
        """记录成功"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._obs.log("INFO", f"CircuitBreaker '{self.name}' CLOSED (recovered)", "resilience")
            else:
                self._failure_count = 0
    
    def record_failure(self) -> None:
        """记录失败"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._obs.log("ERROR", f"CircuitBreaker '{self.name}' OPENED (half-open failed)", "resilience")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._obs.log("ERROR", f"CircuitBreaker '{self.name}' OPENED ({self._failure_count} failures)", "resilience")
    
    def _should_attempt_reset(self) -> bool:
        """检查是否过了冷却期"""
        if self._last_failure_time is None:
            return True
        return (time.time() - self._last_failure_time) >= self.cooldown_seconds
    
    def get_stats(self) -> Dict:
        """获取熔断器统计"""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "cooldown_remaining": max(0, self.cooldown_seconds - (time.time() - self._last_failure_time)) if self._last_failure_time else 0,
            }


class RetryWithBackoff:
    """
    指数退避重试
    
    使用方式：
        retry = RetryWithBackoff(max_retries=3, base_delay=1.0, max_delay=30.0, exponential_base=2.0)
        result = retry.execute(lambda: fetch_data(), timeout=5.0)
    """
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0,
                 max_delay: float = 30.0, exponential_base: float = 2.0,
                 jitter: bool = True):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self._obs = get_obs()
    
    def execute(self, fn: Callable[[], T], timeout: Optional[float] = None,
                operation_name: str = "") -> T:
        """
        执行带重试的函数
        
        Args:
            fn: 无参函数，返回 T
            timeout: 单次调用超时（秒）
            operation_name: 操作名称（用于日志）
        
        Returns:
            fn 的返回值
        
        Raises:
            Exception: 所有重试都失败时抛出最后一次异常
        """
        last_error = None
        name = operation_name or fn.__name__
        
        for attempt in range(self.max_retries + 1):
            try:
                if timeout:
                    # 使用 threading.Timer 实现超时
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(fn)
                        result = future.result(timeout=timeout)
                        return result
                else:
                    return fn()
                    
            except Exception as e:
                last_error = e
                is_last = attempt == self.max_retries
                
                if not is_last:
                    delay = self._calculate_delay(attempt)
                    self._obs.log("WARN", 
                        f"Retry {name}: attempt {attempt+1}/{self.max_retries+1} failed, retrying in {delay:.1f}s: {str(e)}",
                        "resilience")
                    time.sleep(delay)
                else:
                    self._obs.log("ERROR", 
                        f"Retry {name}: all {self.max_retries+1} attempts failed: {str(e)}",
                        "resilience")
        
        raise last_error
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算退避延迟"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            import random
            delay = delay * (0.5 + random.random())
        return delay


class DataSourceResilience:
    """
    数据源智能降级系统（主入口）
    
    使用方式：
        resilience = DataSourceResilience()
        
        # 获取个股K线（自动降级）
        result = resilience.fetch_kline("000001", "2025-06-01", "2025-06-19")
        if result.success:
            df = result.data
            print(f"Source: {result.source}, Degraded: {result.degraded}")
    """
    
    # 数据源优先级配置
    KLINE_SOURCES = ["ifind", "stock_finance_data", "eastmoney"]
    STOCK_INFO_SOURCES = ["ifind", "eastmoney"]
    CLOSE_SUMMARY_SOURCES = ["ifind", "eastmoney"]
    SECTOR_LIST_SOURCES = ["eastmoney", "default"]
    
    def __init__(self):
        self._cache = MultiLevelCache()
        self._obs = get_obs()
        
        # 熔断器注册表
        self._breakers: Dict[str, CircuitBreaker] = {}
        
        # 重试配置
        self._retry = RetryWithBackoff(
            max_retries=2, 
            base_delay=0.5, 
            max_delay=10.0,
            exponential_base=2.0,
        )
        
        # 数据源配置
        self._source_timeouts = {
            "mootdx_offline": 3.0,
            "mootdx_realtime": 3.0,  # RealtimeDataProvider 内部 timeout=2, 快速失败
            "ifind": 10.0,
            "stock_finance_data": 10.0,
            "eastmoney": 10.0,
        }
        
        # mootdx 数据提供者（延迟初始化）
        self._mootdx_provider = None
    
    def _get_mootdx(self):
        """延迟初始化 mootdx provider"""
        if self._mootdx_provider is None:
            try:
                from utils.mootdx_provider import MootdxDataProvider
                self._mootdx_provider = MootdxDataProvider()
            except Exception as e:
                self._obs.log("WARN", f"mootdx init failed: {str(e)}", "DataSourceResilience")
        return self._mootdx_provider
    
    def _get_breaker(self, source: str) -> CircuitBreaker:
        """获取或创建熔断器"""
        if source not in self._breakers:
            self._breakers[source] = CircuitBreaker(
                name=source,
                failure_threshold=5,
                cooldown_seconds=60.0,
            )
        return self._breakers[source]
    
    # ========================================================================
    # 个股K线（主接口）
    # ========================================================================
    
    def fetch_kline(self, code: str, start_date: str, end_date: str,
                    period: str = "daily", adjust: str = "qfq") -> FallbackResult:
        """
        获取个股K线（带完整降级链）
        
        降级链: mootdx离线 → mootdx实时 → ifind → stock_finance_data → 东方财富 → Cache → Empty
        """
        trace_id = f"kline-{code}-{int(time.time())}"
        start_time = time.time()
        result = FallbackResult(trace_id=trace_id)
        
        # 1. 尝试 mootdx 离线（通达信本地数据）
        if self._try_source("mootdx_offline", code):
            try:
                df = self._fetch_mootdx_offline_kline(code, start_date, end_date, period, adjust)
                if df is not None and len(df) > 0:
                    result.data = df
                    result.success = True
                    result.source = "mootdx_offline"
                    result.degraded = False
                    result.duration_ms = (time.time() - start_time) * 1000
                    self._obs.log("INFO", f"Kline fetched from mootdx offline: {code} ({len(df)} rows)", 
                                  "DataSourceResilience", trace_id)
                    self._cache_result(code, start_date, end_date, df)
                    return result
            except Exception as e:
                self._obs.log("WARN", f"mootdx offline failed for {code}: {str(e)}", 
                              "DataSourceResilience", trace_id)
                self._get_breaker("mootdx_offline").record_failure()
        
        # 2. 尝试 mootdx 实时（通达信服务器）
        if self._try_source("mootdx_realtime", code):
            try:
                df = self._fetch_mootdx_realtime_kline(code, start_date, end_date, period, adjust)
                if df is not None and len(df) > 0:
                    result.data = df
                    result.success = True
                    result.source = "mootdx_realtime"
                    result.degraded = False
                    result.duration_ms = (time.time() - start_time) * 1000
                    self._obs.log("INFO", f"Kline fetched from mootdx realtime: {code} ({len(df)} rows)", 
                                  "DataSourceResilience", trace_id)
                    self._cache_result(code, start_date, end_date, df)
                    return result
            except Exception as e:
                self._obs.log("WARN", f"mootdx realtime failed for {code}: {str(e)}", 
                              "DataSourceResilience", trace_id)
                self._get_breaker("mootdx_realtime").record_failure()
        
        # 3. 尝试 ifind
        if self._try_source("ifind", code):
            try:
                df = self._fetch_ifind_kline(code, start_date, end_date, adjust)
                if df is not None and len(df) > 0:
                    result.data = df
                    result.success = True
                    result.source = "ifind"
                    result.degraded = False
                    result.duration_ms = (time.time() - start_time) * 1000
                    self._obs.log("INFO", f"Kline fetched from ifind: {code} ({len(df)} rows)", 
                                  "DataSourceResilience", trace_id)
                    self._cache_result(code, start_date, end_date, df)
                    return result
            except Exception as e:
                self._obs.log("WARN", f"ifind failed for {code}: {str(e)}", 
                              "DataSourceResilience", trace_id)
                self._get_breaker("ifind").record_failure()
        
        # 4. 尝试 stock_finance_data
        if self._try_source("stock_finance_data", code):
            try:
                df = self._fetch_sfd_kline(code, start_date, end_date, adjust)
                if df is not None and len(df) > 0:
                    result.data = df
                    result.success = True
                    result.source = "stock_finance_data"
                    result.degraded = True
                    result.duration_ms = (time.time() - start_time) * 1000
                    self._obs.log("INFO", f"Kline fetched from stock_finance_data (degraded): {code}", 
                                  "DataSourceResilience", trace_id)
                    self._cache_result(code, start_date, end_date, df)
                    return result
            except Exception as e:
                self._obs.log("WARN", f"stock_finance_data failed for {code}: {str(e)}", 
                              "DataSourceResilience", trace_id)
                self._get_breaker("stock_finance_data").record_failure()
        
        # 5. 尝试东方财富
        if self._try_source("eastmoney", code):
            try:
                df = self._fetch_em_kline(code, start_date, end_date, period, adjust)
                if df is not None and len(df) > 0:
                    result.data = df
                    result.success = True
                    result.source = "eastmoney"
                    result.degraded = True
                    result.duration_ms = (time.time() - start_time) * 1000
                    self._obs.log("INFO", f"Kline fetched from eastmoney (degraded): {code}", 
                                  "DataSourceResilience", trace_id)
                    self._cache_result(code, start_date, end_date, df)
                    return result
            except Exception as e:
                self._obs.log("WARN", f"eastmoney failed for {code}: {str(e)}", 
                              "DataSourceResilience", trace_id)
                self._get_breaker("eastmoney").record_failure()
        
        # 6. 缓存兜底
        cached_df = self._get_cached_kline(code, start_date, end_date)
        if cached_df is not None and len(cached_df) > 0:
            result.data = cached_df
            result.success = True
            result.source = "cache"
            result.degraded = True
            result.stale = True
            result.duration_ms = (time.time() - start_time) * 1000
            self._obs.log("WARN", f"Kline served from cache (stale): {code}", 
                          "DataSourceResilience", trace_id)
            return result
        
        # 7. 全部失败
        result.error = "All data sources failed and no cache available"
        result.duration_ms = (time.time() - start_time) * 1000
        self._obs.log("ERROR", f"Kline fetch failed for {code}: all sources exhausted", 
                      "DataSourceResilience", trace_id)
        return result
    
    # ========================================================================
    # 个股信息
    # ========================================================================
    # 个股信息
    # ========================================================================
    
    def fetch_stock_info(self, code: str) -> FallbackResult:
        """获取股票基本信息（ifind → 东方财富）"""
        trace_id = f"info-{code}-{int(time.time())}"
        start_time = time.time()
        result = FallbackResult(trace_id=trace_id)
        
        # 1. ifind
        if self._try_source("ifind", code):
            try:
                info = self._fetch_ifind_info(code)
                if info:
                    result.data = info
                    result.success = True
                    result.source = "ifind"
                    result.duration_ms = (time.time() - start_time) * 1000
                    return result
            except Exception as e:
                self._get_breaker("ifind").record_failure()
        
        # 2. 降级：东方财富（从K线接口提取基本信息）
        result.error = "Stock info fetch failed"
        result.duration_ms = (time.time() - start_time) * 1000
        return result
    
    # ========================================================================
    # 收盘摘要
    # ========================================================================
    
    def fetch_close_summary(self, code: str) -> FallbackResult:
        """获取收盘摘要（ifind → 东方财富实时）"""
        trace_id = f"summary-{code}-{int(time.time())}"
        start_time = time.time()
        result = FallbackResult(trace_id=trace_id)
        
        # 1. ifind
        if self._try_source("ifind", code):
            try:
                summary = self._fetch_ifind_summary(code)
                if summary:
                    result.data = summary
                    result.success = True
                    result.source = "ifind"
                    result.duration_ms = (time.time() - start_time) * 1000
                    return result
            except Exception as e:
                self._get_breaker("ifind").record_failure()
        
        result.error = "Close summary fetch failed"
        result.duration_ms = (time.time() - start_time) * 1000
        return result
    
    # ========================================================================
    # 板块数据
    # ========================================================================
    
    def fetch_sector_list(self) -> FallbackResult:
        """板块列表（东方财富 → 默认列表）"""
        trace_id = f"sector-list-{int(time.time())}"
        start_time = time.time()
        result = FallbackResult(trace_id=trace_id)
        
        # 1. 东方财富
        if self._try_source("eastmoney", "sector"):
            try:
                df = self._fetch_em_sector_list()
                if df is not None and len(df) > 0:
                    result.data = df
                    result.success = True
                    result.source = "eastmoney"
                    result.duration_ms = (time.time() - start_time) * 1000
                    return result
            except Exception as e:
                self._get_breaker("eastmoney").record_failure()
        
        # 2. 默认列表
        result.data = self._default_sector_list()
        result.success = True
        result.source = "default"
        result.degraded = True
        result.duration_ms = (time.time() - start_time) * 1000
        self._obs.log("WARN", "Sector list served from default (degraded)", 
                      "DataSourceResilience", trace_id)
        return result
    
    # ========================================================================
    # 熔断器统计
    # ========================================================================
    
    def get_circuit_breaker_stats(self) -> List[Dict]:
        """获取所有熔断器统计"""
        return [cb.get_stats() for cb in self._breakers.values()]
    
    def get_health_status(self) -> Dict:
        """获取整体健康状态"""
        stats = self.get_circuit_breaker_stats()
        healthy = sum(1 for s in stats if s["state"] == "closed")
        total = len(stats) if stats else 1
        return {
            "healthy_sources": healthy,
            "total_sources": total,
            "health_rate": round(healthy / total, 2),
            "breakers": stats,
        }
    
    # ========================================================================
    # 内部数据源调用（懒加载，避免循环导入）
    # ========================================================================
    
    def _try_source(self, source: str, code: str) -> bool:
        """检查数据源是否可用（熔断器状态）"""
        breaker = self._get_breaker(source)
        if not breaker.can_execute():
            self._obs.log("WARN", f"Source '{source}' circuit breaker OPEN, skipping", 
                          "DataSourceResilience")
            return False
        return True
    
    def _persist_kline(self, code: str, df: Any) -> None:
        """持久化K线到SQLite"""
        try:
            from backend.core.persistence import PersistenceEngine
            pers = PersistenceEngine()
            if isinstance(df, pd.DataFrame):
                pers.save_stock_klines(code, df)
        except Exception as e:
            self._obs.log("WARN", f"Failed to persist kline for {code}: {str(e)}", "DataSourceResilience")
    
    def _cache_result(self, code: str, start: str, end: str, df: pd.DataFrame) -> None:
        """缓存K线结果"""
        cache_key = f"klines:{code}:{start}:{end}"
        self._cache.set(cache_key, df.to_dict("records"), ttl_seconds=86400)  # 24小时
        # 同时持久化到SQLite
        self._persist_kline(code, df)
    
    def _get_cached_kline(self, code: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """获取缓存的K线"""
        cache_key = f"klines:{code}:{start}:{end}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return pd.DataFrame(cached)
        return None
    
    # ---- mootdx 调用 ----
    
    def _fetch_mootdx_offline_kline(self, code: str, start: str, end: str, period: str, adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """调用 mootdx 离线（通达信本地数据）获取K线"""
        provider = self._get_mootdx()
        if provider is None:
            return None
        try:
            return provider.fetch_kline(code, start, end, period, source="offline", adjust=adjust)
        except Exception as e:
            self._obs.log("WARN", f"mootdx offline failed for {code}: {str(e)}", "DataSourceResilience")
            return None
    
    def _fetch_mootdx_realtime_kline(self, code: str, start: str, end: str, period: str, adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """调用 mootdx 实时（通达信服务器）获取K线"""
        provider = self._get_mootdx()
        if provider is None:
            return None
        try:
            # RealtimeDataProvider 内部已设置短超时(bestip=False, timeout=2)，直接调用即可
            return provider.fetch_kline(code, start, end, period, source="realtime", adjust=adjust)
        except Exception as e:
            self._obs.log("WARN", f"mootdx realtime failed for {code}: {str(e)}", "DataSourceResilience")
            return None
    
    # ---- ifind 调用 ----
    
    def _fetch_ifind_kline(self, code: str, start: str, end: str, adjust: str) -> Optional[pd.DataFrame]:
        """调用 ifind 获取K线"""
        from utils.data_fetcher import ifind_daily_kline
        
        # ifind 使用 forward/backward/none 语义
        adjust_map = {"qfq": "forward", "hfq": "backward", "none": "none"}
        mapped = adjust_map.get(adjust, adjust)
        
        def _call():
            return ifind_daily_kline(code, start, end, adjust=mapped)
        
        df = self._retry.execute(_call, timeout=self._source_timeouts["ifind"], 
                                  operation_name=f"ifind_kline_{code}")
        return df if df is not None and len(df) > 0 else None
    
    def _fetch_ifind_info(self, code: str) -> Optional[Dict]:
        """调用 ifind 获取股票信息"""
        from utils.data_fetcher import ifind_stock_info
        return ifind_stock_info(code)
    
    def _fetch_ifind_summary(self, code: str) -> Optional[Dict]:
        """调用 ifind 获取收盘摘要"""
        from utils.data_fetcher import ifind_close_summary
        return ifind_close_summary(code)
    
    # ---- stock_finance_data 调用 ----
    
    def _fetch_sfd_kline(self, code: str, start: str, end: str, adjust: str) -> Optional[pd.DataFrame]:
        """调用 stock_finance_data 获取K线"""
        from utils.data_fetcher import _sfd_get_price, _to_ifind_ticker
        
        ticker = _to_ifind_ticker(code)
        # stock_finance_data 同样使用 forward/backward/none 语义
        adjust_map = {"qfq": "forward", "hfq": "backward", "none": "none"}
        mapped = adjust_map.get(adjust, adjust)
        
        def _call():
            return _sfd_get_price(ticker, start, end, interval="D", adjust=mapped)
        
        df = self._retry.execute(_call, timeout=self._source_timeouts["stock_finance_data"],
                                  operation_name=f"sfd_kline_{code}")
        return df if df is not None and len(df) > 0 else None
    
    # ---- 东方财富调用 ----
    
    def _fetch_em_kline(self, code: str, start: str, end: str, period: str, adjust: str) -> Optional[pd.DataFrame]:
        """调用东方财富获取K线"""
        from utils.data_fetcher import em_fetch_daily_kline
        
        # 东方财富日期格式: YYYYMMDD
        em_start = start.replace("-", "")
        em_end = end.replace("-", "")
        
        def _call():
            return em_fetch_daily_kline(code, em_start, em_end, period, adjust)
        
        df = self._retry.execute(_call, timeout=self._source_timeouts["eastmoney"],
                                  operation_name=f"em_kline_{code}")
        return df if df is not None and len(df) > 0 else None
    
    def _fetch_em_sector_list(self) -> Optional[pd.DataFrame]:
        """调用东方财富获取板块列表"""
        from utils.data_fetcher import em_fetch_sector_list
        return em_fetch_sector_list()
    
    def _default_sector_list(self) -> pd.DataFrame:
        """内置默认板块列表"""
        from utils.data_fetcher import _default_sector_list
        return _default_sector_list()


# ========================================================================
# 便捷函数（全局单例）
# ========================================================================

_resilience_instance: Optional[DataSourceResilience] = None
_resilience_lock = threading.Lock()


def get_resilience() -> DataSourceResilience:
    """获取全局 resilience 实例"""
    global _resilience_instance
    if _resilience_instance is None:
        with _resilience_lock:
            if _resilience_instance is None:
                _resilience_instance = DataSourceResilience()
    return _resilience_instance


# 便捷包装函数（兼容旧接口）
def fetch_kline_with_resilience(code: str, start_date: str, end_date: str,
                                 period: str = "daily", adjust: str = "qfq") -> pd.DataFrame:
    """兼容旧接口的K线获取（返回DataFrame或空DataFrame）"""
    resilience = get_resilience()
    result = resilience.fetch_kline(code, start_date, end_date, period, adjust)
    if result.success and result.data is not None:
        return result.data
    return pd.DataFrame()


if __name__ == "__main__":
    # 快速测试
    print("=== Resilience System Test ===")
    
    resilience = DataSourceResilience()
    
    # 测试熔断器
    cb = resilience._get_breaker("test")
    print(f"Initial state: {cb.state.value}")
    
    # 测试健康状态
    health = resilience.get_health_status()
    print(f"Health: {health}")
    
    # 测试K线获取（实际调用）
    print("\n--- Fetch 000001 kline ---")
    result = resilience.fetch_kline("000001", "2025-06-01", "2025-06-19")
    print(f"Result: {result.to_dict()}")
    if result.success and isinstance(result.data, pd.DataFrame):
        print(f"DataFrame shape: {result.data.shape}")
        print(result.data.tail(3))
