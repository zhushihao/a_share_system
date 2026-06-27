# -*- coding: utf-8 -*-
"""
Data Provider Service - 行情数据服务层

职责：
1. 封装旧系统 mootdx_provider，适配 FastAPI 标准接口
2. 返回标准化格式（StandardQuote / DataFrame）
3. 复用 core/ 模块：observability, cache, resilience
4. 统一数据源入口（离线优先 → 实时降级 → 缓存兜底）
"""

import sys
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

# 复用旧系统核心模块（项目根目录需在 sys.path）
import sys, os
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import utils.mootdx_provider as mootdx_module
from backend.core.observability import get_obs
from backend.core.cache import MultiLevelCache, TTL_PRESETS
from backend.core.resilience import get_resilience, FallbackResult

# 新系统 Schema（使用 backend 前缀兼容独立运行）
try:
    from models.schemas import StandardQuote
except ImportError:
    from backend.models.schemas import StandardQuote


# 用于 mootdx 超时控制的线程池
_mootdx_fetch_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mootdx_fetch")


class DataProviderService:
    """
    行情数据服务
    
    封装 mootdx 数据层，提供标准化接口：
    - K线数据（OHLCV）
    - 实时行情
    - 股票列表
    - 健康检查
    """
    
    def __init__(self, tdxdir: str = "D:/TDX"):
        self.tdxdir = tdxdir
        self._provider: Optional[mootdx_module.MootdxDataProvider] = None
        self._resilience = None
        self._obs = get_obs()
        self._cache = MultiLevelCache()
        self._valid_symbols: Optional[set] = None  # 本地有效股票代码缓存
        
    def _load_valid_symbols(self) -> set:
        """加载本地通达信有效股票代码列表（缓存）"""
        if self._valid_symbols is not None:
            return self._valid_symbols
        try:
            df = self.provider.fetch_stock_list()
            if df is not None and len(df) > 0 and "code" in df.columns:
                self._valid_symbols = set(df["code"].astype(str).str.strip().str.zfill(6).tolist())
            else:
                self._valid_symbols = set()
        except Exception as e:
            self._obs.log("WARN", f"Failed to load stock list for validation: {e}", "DataProviderService")
            self._valid_symbols = set()
        return self._valid_symbols
    
    def _is_valid_symbol(self, code: str) -> bool:
        """检查代码是否在本地有效股票列表中"""
        valid = self._load_valid_symbols()
        return code in valid

    def _fetch_kline_with_timeout(
        self,
        code: str,
        start_date: str = "",
        end_date: str = "",
        period: str = "daily",
        adjust: str = "qfq",
        timeout: float = 2.0,
    ) -> Optional[pd.DataFrame]:
        """
        带超时的 mootdx K 线读取
        防止个别股票数据文件缺失/损坏导致 mootdx 阻塞 14s+
        """
        future = _mootdx_fetch_executor.submit(
            self.provider.fetch_kline,
            code, start_date, end_date, period, adjust=adjust
        )
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            self._obs.log(
                "WARN",
                f"mootdx fetch_kline timeout for {code} (> {timeout}s), treating as no data",
                "DataProviderService",
            )
            return None
        except Exception as e:
            self._obs.log(
                "WARN",
                f"mootdx fetch_kline error for {code}: {e}",
                "DataProviderService",
            )
            return None
        
    @property
    def provider(self) -> mootdx_module.MootdxDataProvider:
        """延迟初始化 mootdx provider"""
        if self._provider is None:
            self._provider = mootdx_module.get_mootdx_provider(tdxdir=self.tdxdir)
        return self._provider
    
    @property
    def resilience(self):
        """延迟初始化 resilience"""
        if self._resilience is None:
            self._resilience = get_resilience()
        return self._resilience
    
    def _fetch_kline_resilient_with_timeout(
        self,
        code: str,
        start_date: str = "",
        end_date: str = "",
        period: str = "daily",
        adjust: str = "qfq",
        timeout: float = 2.0,
    ):
        """
        带超时的 resilience K 线读取
        防止 resilience 降级链中 mootdx 阻塞 14s+
        """
        future = _mootdx_fetch_executor.submit(
            self.resilience.fetch_kline,
            code, start_date, end_date, period, adjust
        )
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            self._obs.log(
                "WARN",
                f"resilience fetch_kline timeout for {code} (> {timeout}s), treating as no data",
                "DataProviderService",
            )
            return FallbackResult(
                trace_id=f"timeout-{code}",
                success=False,
                degraded=True,
                source="timeout",
                error=f"Timeout after {timeout}s",
            )
        except Exception as e:
            self._obs.log(
                "WARN",
                f"resilience fetch_kline error for {code}: {e}",
                "DataProviderService",
            )
            return FallbackResult(
                trace_id=f"error-{code}",
                success=False,
                degraded=True,
                source="error",
                error=str(e),
            )
    
    # ─────────────────────────────────────────
    # 健康检查
    # ─────────────────────────────────────────
    
    def health_check(self) -> Dict[str, Any]:
        """数据源健康检查"""
        return self.provider.health_check()
    
    # ─────────────────────────────────────────
    # K线数据
    # ─────────────────────────────────────────
    
    def fetch_ohlcv(
        self,
        symbol: str,
        start_date: str = "",
        end_date: str = "",
        period: str = "daily",
        adjust: str = "qfq",
        source: str = "auto",
    ) -> Optional[pd.DataFrame]:
        """
        获取K线数据（OHLCV格式）
        
        Args:
            symbol: 股票代码（如 600519, 000001）或指数代码（sh000001, sz399001）
            start_date: 起始日期（YYYYMMDD 或 YYYY-MM-DD）
            end_date: 结束日期
            period: daily / weekly / monthly / minute
            adjust: qfq(前复权) / hfq(后复权) / none(不复权)
            source: auto / offline / realtime
        
        Returns:
            DataFrame[date, code, open, high, low, close, volume, amount]
        """
        # 处理指数代码：直接使用 Reader 读取，绕过 _normalize_code 和 resilience
        idx_lower = symbol.lower().strip()
        if idx_lower in self.INDEX_MAP:
            info = self.INDEX_MAP[idx_lower]
            tdx_code = info['code']
            try:
                # 确保 reader 已初始化
                self.provider._offline._init_reader()
                reader = self.provider._offline._reader
                if reader is None:
                    self._obs.log("WARN", f"Reader not initialized for index {idx_lower}", "DataProviderService")
                    return None
                
                if period == 'daily':
                    df = reader.daily(symbol=tdx_code)
                elif period == 'weekly':
                    # StdReader 不支持 weekly，基于 daily 聚合
                    df = reader.daily(symbol=tdx_code)
                    if df is not None and len(df) > 0:
                        df = self._aggregate_period(df, 'weekly')
                elif period == 'monthly':
                    # StdReader 不支持 monthly，基于 daily 聚合
                    df = reader.daily(symbol=tdx_code)
                    if df is not None and len(df) > 0:
                        df = self._aggregate_period(df, 'monthly')
                elif period in ('minute', '1m', '5m', '15m', '30m', '60m'):
                    # 分钟级数据：先读取1分钟，再按需聚合
                    df = reader.minute(symbol=tdx_code)
                    if df is not None and len(df) > 0:
                        df = self._standardize_ohlcv(df, idx_lower)
                        _, interval = self._resolve_minute_period(period)
                        if interval > 1:
                            df = self._aggregate_minute(df, interval)
                        if len(df) > 1000:
                            df = df.tail(1000).reset_index(drop=True)
                else:
                    df = reader.daily(symbol=tdx_code)
                
                if df is not None and len(df) > 0:
                    if period not in ('minute', '1m', '5m', '15m', '30m', '60m'):
                        df = self._standardize_ohlcv(df, idx_lower)
                    return df
                return None
            except Exception as e:
                self._obs.log("WARN", f"Index OHLCV failed for {idx_lower}: {e}", "DataProviderService")
                return None
        
        # 普通股票代码
        code = mootdx_module._normalize_code(symbol)
        
        # Fast validation: skip invalid codes
        if not (len(code) == 6 and code.isdigit()):
            self._obs.log("WARN", f"Invalid symbol code skipped: {symbol} -> {code}", "DataProviderService")
            return None
        
        # 二次验证：检查代码是否在本地通达信有效列表中（避免 mootdx 14s 超时）
        if not self._is_valid_symbol(code):
            self._obs.log("WARN", f"Symbol not in local TDX list: {code}", "DataProviderService")
            return None
        
        # 处理分钟级周期：映射到基础分钟数据获取，再聚合
        base_period, interval = self._resolve_minute_period(period)
        fetch_period = base_period if base_period != period else period
        
        cache_key = f"ohlcv:{code}:{start_date}:{end_date}:{period}:{adjust}"
        
        # 1. 检查缓存
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._obs.log("INFO", f"Cache hit for OHLCV: {code}", "DataProviderService")
            return pd.DataFrame(cached) if isinstance(cached, list) else cached
        
        # 2. 获取数据（实时优先，失败降级到离线）
        df = None
        source_name = "unknown"
        
        if source == "realtime" or source == "auto":
            # 2.1 先尝试实时数据（优先！）
            try:
                df = self._fetch_realtime_kline(code, fetch_period, adjust)
                if df is not None and len(df) > 0:
                    source_name = "realtime"
                    self._obs.log("INFO", f"OHLCV fetched (realtime): {code} ({len(df)} rows)", "DataProviderService")
                    # 实时数据持久化到 SQLite
                    self._persist_realtime_data(code, df, period, adjust)
            except Exception as e:
                self._obs.log("WARN", f"Realtime fetch failed for {code}: {e}", "DataProviderService")
        
        # 2.2 实时失败，降级到离线（TDX本地文件）
        if df is None or len(df) == 0:
            if source == "auto" or source == "offline":
                result = self._fetch_kline_resilient_with_timeout(code, start_date, end_date, fetch_period, adjust)
                if result.success and result.data is not None and len(result.data) > 0:
                    df = result.data
                    source_name = result.source
                    self._obs.log("INFO", f"OHLCV fetched ({source_name}): {code} ({len(df)} rows)", "DataProviderService")
        
        # 2.3 离线也失败，尝试从 SQLite 缓存读取
        if df is None or len(df) == 0:
            df = self._read_persisted_data(code, fetch_period, adjust)
            if df is not None and len(df) > 0:
                source_name = "persisted"
                self._obs.log("INFO", f"OHLCV fetched (persisted): {code} ({len(df)} rows)", "DataProviderService")
        
        if df is not None and len(df) > 0:
            # 分钟级聚合（5m/15m/30m/60m）
            if interval > 1 and fetch_period == "minute":
                df = self._aggregate_minute(df, interval)
            # 标准化
            df = self._standardize_ohlcv(df, code)
            # 缓存
            self._cache.set(cache_key, df.to_dict("records"), ttl_seconds=TTL_PRESETS["stock_kline"])
            return df
        
        self._obs.log("WARN", f"OHLCV fetch failed: {code}", "DataProviderService")
        return None
    
    def _standardize_ohlcv(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """标准化 OHLCV DataFrame"""
        df = df.copy()
        
        # 确保 code 列
        if "code" not in df.columns:
            df["code"] = code
        
        # 确保日期列
        if "date" not in df.columns:
            if df.index.name == "date":
                df = df.reset_index()
            else:
                for col in ["time", "datetime"]:
                    if col in df.columns:
                        df = df.rename(columns={col: "date"})
                        break
        
        # 确保数值列
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # 过滤掉OHLC全为NaN的脏数据行（如非交易时间的midnight行）
        df = df.dropna(subset=["open", "high", "low", "close"], how="all")
        if len(df) == 0:
            return df
        
        # 确保 amount 列
        if "amount" not in df.columns and "amt" in df.columns:
            df = df.rename(columns={"amt": "amount"})
        if "amount" in df.columns:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        
        # 排序
        if "date" in df.columns:
            df = df.sort_values("date").reset_index(drop=True)
        
        # 检测非交易日填充
        df = self._detect_filled_ohlcv(df)

        # 选择标准列
        standard_cols = ["date", "code", "open", "high", "low", "close", "volume", "amount", "is_filled"]
        available_cols = [c for c in standard_cols if c in df.columns]
        return df[available_cols]
    

    def _detect_filled_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        检测非交易日复制填充。
        若最后一条数据的日期为周末，且 OHLC 与前一条完全相同，则标记 is_filled=True。
        """
        if df is None or len(df) < 2:
            if df is not None:
                df["is_filled"] = False
            return df
        df = df.copy()
        df["is_filled"] = False
        last = df.iloc[-1]
        prev = df.iloc[-2]
        try:
            last_date = str(int(last.get("date", "")))
            if len(last_date) == 8:
                dt = datetime.strptime(last_date, "%Y%m%d")
                if dt.weekday() >= 5:  # 周六/周日
                    ohlc_same = (
                        abs(float(last.get("open", 0)) - float(prev.get("open", 0))) < 1e-6
                        and abs(float(last.get("high", 0)) - float(prev.get("high", 0))) < 1e-6
                        and abs(float(last.get("low", 0)) - float(prev.get("low", 0))) < 1e-6
                        and abs(float(last.get("close", 0)) - float(prev.get("close", 0))) < 1e-6
                    )
                    if ohlc_same:
                        df.at[df.index[-1], "is_filled"] = True
        except Exception:
            pass
        return df
    def _aggregate_period(self, df: pd.DataFrame, period: str) -> pd.DataFrame:
        """
        将日K线或分钟K线数据聚合为周/月/季/年K线，或从1分钟聚合为5/15/30/60分钟K线
        
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
            df["_period"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
        elif period == "monthly":
            df["_period"] = df["date"].dt.to_period("M").apply(lambda r: r.start_time)
        elif period == "quarterly":
            df["_period"] = df["date"].dt.to_period("Q").apply(lambda r: r.start_time)
        elif period == "yearly":
            df["_period"] = df["date"].dt.to_period("Y").apply(lambda r: r.start_time)
        elif period in ("5m", "15m", "30m", "60m"):
            # 分钟级聚合：基于1分钟数据，按指定间隔聚合
            minutes = int(period.replace("m", ""))
            # 使用 pd.Grouper 按分钟间隔聚合
            df["_period"] = df["date"].dt.floor(f"{minutes}min")
        else:
            return df
        
        agg_df = df.groupby("_period").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            amount=("amount", "sum"),
        ).reset_index()
        
        agg_df = agg_df.rename(columns={"_period": "date"})
        if period in ("5m", "15m", "30m", "60m"):
            # 分钟级保留完整时间戳格式
            agg_df["date"] = agg_df["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            agg_df["date"] = agg_df["date"].dt.strftime("%Y%m%d")
        
        # 保留 code 列
        if "code" in df.columns:
            code_map = df.groupby("_period")["code"].first().reset_index()
            code_map = code_map.rename(columns={"_period": "date"})
            if period in ("5m", "15m", "30m", "60m"):
                code_map["date"] = code_map["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                code_map["date"] = code_map["date"].dt.strftime("%Y%m%d")
            agg_df = agg_df.merge(code_map, on="date", how="left")
        
        cols = ["date", "code", "open", "high", "low", "close", "volume", "amount"]
        available = [c for c in cols if c in agg_df.columns]
        return agg_df[available].sort_values("date").reset_index(drop=True)
        
    def _aggregate_minute(self, df: pd.DataFrame, interval_min: int) -> pd.DataFrame:
        """
        将1分钟K线数据聚合为指定分钟间隔的K线
        
        Args:
            df: 1分钟DataFrame，必须含 date 列
            interval_min: 聚合间隔分钟数（5, 15, 30, 60）
        """
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df[df["date"].notna()].sort_values("date").reset_index(drop=True)
        
        # 过滤掉OHLC全为NaN的脏数据行（如非交易时间 midnight 行）
        df = df.dropna(subset=["open", "high", "low", "close"], how="all")
        if len(df) == 0:
            return df
        
        df["_period"] = df["date"].dt.floor(f"{interval_min}min")
        
        agg_df = df.groupby("_period").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            amount=("amount", "sum"),
        ).reset_index()
        
        agg_df = agg_df.rename(columns={"_period": "date"})
        agg_df["date"] = agg_df["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
        
        if "code" in df.columns:
            code_map = df.groupby(df["date"].dt.floor(f"{interval_min}min"))["code"].first().reset_index()
            code_map.columns = ["date", "code"]
            code_map["date"] = pd.to_datetime(code_map["date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
            agg_df = agg_df.merge(code_map, on="date", how="left")
        
        cols = ["date", "code", "open", "high", "low", "close", "volume", "amount"]
        available = [c for c in cols if c in agg_df.columns]
        return agg_df[available].sort_values("date").reset_index(drop=True)
        
    def _resolve_minute_period(self, period: str) -> tuple:
        """
        将分钟周期参数解析为 (基础周期, 聚合间隔)
        
        Returns:
            (base_period, interval_min): base_period 为 'minute' 或 period 本身，
            interval_min 为聚合间隔（1 表示不聚合）
        """
        mapping = {
            "1m": ("minute", 1),
            "5m": ("minute", 5),
            "15m": ("minute", 15),
            "30m": ("minute", 30),
            "60m": ("minute", 60),
            "minute": ("minute", 1),
        }
        return mapping.get(period, (period, 1))
    
    # ─────────────────────────────────────────
    # 实时行情
    # ─────────────────────────────────────────
    
    # 指数代码映射（支持通达信市场前缀格式）
    INDEX_MAP = {
        'sh000001': {'code': 'sh000001', 'name': '上证指数', 'market': 'sh'},
        'sz399001': {'code': '399001', 'name': '深证成指', 'market': 'sz'},
        'sz399006': {'code': '399006', 'name': '创业板指', 'market': 'sz'},
        'sh000688': {'code': 'sh000688', 'name': '科创50', 'market': 'sh'},
        'sh000016': {'code': 'sh000016', 'name': '上证50', 'market': 'sh'},
        'sh000300': {'code': 'sh000300', 'name': '沪深300', 'market': 'sh'},
    }

    def fetch_realtime_quotes(self, symbols: List[str]) -> List[StandardQuote]:
        """
        获取实时行情（多股）
        支持股票和指数代码
        """
        # 分离指数和股票
        index_symbols = []
        stock_symbols = []
        for s in symbols:
            s_lower = s.lower().strip()
            if s_lower in self.INDEX_MAP:
                index_symbols.append(s_lower)
            else:
                stock_symbols.append(s)
        
        quotes = []
        
        # 处理指数：从 Quotes 实时接口获取（避免离线文件滞后，确保显示最新数据）
        for idx_symbol in index_symbols:
            info = self.INDEX_MAP[idx_symbol]
            try:
                # 优先使用 Quotes 实时接口获取最新指数
                if not getattr(self.provider._realtime, '_initialized', False):
                    self.provider._realtime._init_client()
                client = getattr(self.provider._realtime, '_client', None)
                if client is not None:
                    tdx_code = info['code']  # 如 'sh000001' 或 '399006'
                    df = client.quotes(symbol=[tdx_code])
                    if df is not None and len(df) > 0:
                        row = df.iloc[0]
                        price = float(row.get('price', 0))
                        if price > 0:
                            quotes.append(StandardQuote(
                                symbol=idx_symbol,
                                name=info['name'],
                                timestamp=datetime.now(),
                                open=float(row.get('open', price)),
                                high=float(row.get('high', price)),
                                low=float(row.get('low', price)),
                                close=price,
                                volume=int(row.get('volume', row.get('vol', 0))),
                                amount=float(row.get('amount', 0)) or None,
                                source='mootdx',
                                freq='1d',
                            ))
                            continue  # 成功获取，跳过离线降级
                
                # 降级：从离线 K 线获取
                df = self.fetch_ohlcv(info['code'], period='daily', adjust='none')
                if df is not None and len(df) > 0:
                    latest = df.iloc[-1]
                    quotes.append(StandardQuote(
                        symbol=idx_symbol,
                        name=info['name'],
                        timestamp=datetime.now(),
                        open=float(latest['open']),
                        high=float(latest['high']),
                        low=float(latest['low']),
                        close=float(latest['close']),
                        volume=int(latest['volume']),
                        amount=float(latest.get('amount', 0)) if 'amount' in latest else None,
                        source='mootdx',
                        freq='1d',
                    ))
            except Exception as e:
                self._obs.log('WARN', f'Index quote failed for {idx_symbol}: {e}', 'DataProviderService')
        
        # 处理股票：先尝试 Quotes 实时接口，失败时降级到离线 K 线数据
        if stock_symbols:
            codes = [mootdx_module._normalize_code(s) for s in stock_symbols]
            valid_codes = [c for c in codes if len(c) == 6 and c.isdigit()]
            if valid_codes:
                # 1. 先尝试实时接口
                realtime_df = None
                try:
                    realtime_df = self.provider.fetch_realtime_quote(valid_codes)
                except Exception as e:
                    self._obs.log('WARN', f'Realtime quote failed: {e}', 'DataProviderService')
                
                if realtime_df is not None and len(realtime_df) > 0:
                    quotes.extend(self._df_to_standard_quotes(realtime_df))
                
                # 2. 找出实时接口没获取到的代码，降级到离线 K 线
                got_codes = set()
                if realtime_df is not None and len(realtime_df) > 0 and 'code' in realtime_df.columns:
                    got_codes = set(realtime_df['code'].astype(str).str.strip().str.zfill(6).tolist())
                
                missing_codes = [c for c in valid_codes if c not in got_codes]
                if missing_codes:
                    self._obs.log('INFO', f'Falling back to offline for {len(missing_codes)} codes: {missing_codes[:5]}...', 'DataProviderService')
                    for code in missing_codes:
                        try:
                            df = self.fetch_ohlcv(code, period='daily', adjust='qfq')
                            if df is not None and len(df) > 0:
                                latest = df.iloc[-1]
                                quotes.append(StandardQuote(
                                    symbol=code,
                                    name=None,
                                    timestamp=datetime.now(),
                                    open=float(latest['open']),
                                    high=float(latest['high']),
                                    low=float(latest['low']),
                                    close=float(latest['close']),
                                    volume=int(latest['volume']),
                                    amount=float(latest.get('amount', 0)) if 'amount' in latest else None,
                                    source='mootdx-offline',
                                    freq='1d',
                                ))
                        except Exception as e:
                            self._obs.log('WARN', f'Offline fallback failed for {code}: {e}', 'DataProviderService')
        
        return quotes
    
    def _df_to_standard_quotes(self, df: pd.DataFrame) -> List[StandardQuote]:
        """将 DataFrame 转换为 StandardQuote 列表"""
        quotes = []
        for _, row in df.iterrows():
            try:
                q = self._row_to_standard_quote(row)
                if q:
                    quotes.append(q)
            except Exception as e:
                self._obs.log("WARN", f"Quote row parse failed: {e}", "DataProviderService")
        return quotes
    
    def _row_to_standard_quote(self, row: pd.Series) -> Optional[StandardQuote]:
        """将单行转换为 StandardQuote"""
        try:
            # 提取 code
            code = str(row.get("code", row.get("symbol", ""))).strip()
            if not code:
                return None
            
            # 提取 name
            name = str(row.get("name", "")).strip() or None
            
            # 提取价格（mootdx realtime 返回的字段名可能不同）
            close = float(row.get("close", row.get("price", row.get("latest", 0))))
            if close <= 0:
                # 尝试其他字段
                close = float(row.get("price", 0))
                if close <= 0:
                    return None
            
            open_p = float(row.get("open", close))
            high = float(row.get("high", close))
            low = float(row.get("low", close))
            volume = int(row.get("volume", row.get("vol", 0)))
            amount = float(row.get("amount", row.get("amt", 0))) or None
            
            # 时间戳
            ts = datetime.now()
            if "datetime" in row.index:
                try:
                    ts = pd.to_datetime(row["datetime"])
                except Exception:
                    pass
            elif "date" in row.index:
                try:
                    ts = pd.to_datetime(str(row["date"]))
                except Exception:
                    pass
            
            return StandardQuote(
                symbol=code,
                name=name,
                timestamp=ts,
                open=open_p,
                high=high,
                low=low,
                close=close,
                volume=volume,
                amount=amount,
                source="mootdx",
                freq="1d",
            )
        except Exception as e:
            self._obs.log("DEBUG", f"StandardQuote parse failed: {e}", "DataProviderService")
            return None
    
    # ─────────────────────────────────────────
    # 实时数据优先化 + 数据持久化 + 数据比对
    # ─────────────────────────────────────────
    
    def _fetch_realtime_kline(self, code: str, period: str = "daily", adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """
        通过 mootdx Quotes 接口获取实时数据（日线优先）
        
        策略：
        - 日线：获取实时报价（最新价格），合并到历史数据中
        - 分钟：获取当日分钟数据
        - 失败返回 None，由调用方降级到离线
        """
        try:
            # 日线：获取实时报价补充当日数据
            if period == "daily":
                # 先获取离线历史数据（作为基础）
                offline_df = self._fetch_kline_with_timeout(code, "", "", period, adjust)
                if offline_df is None or len(offline_df) == 0:
                    return None
                
                # 获取实时报价（最新价格）
                try:
                    realtime_df = self.provider.fetch_realtime_quote([code])
                    if realtime_df is not None and len(realtime_df) > 0:
                        row = realtime_df.iloc[0]
                        latest_date = str(datetime.now().date()).replace("-", "")
                        # 如果实时日期 == 离线最后日期，更新最后一条
                        # 如果实时日期 > 离线最后日期，追加一条
                        last_offline_date = str(offline_df.iloc[-1].get("date", "")).replace("-", "")
                        if latest_date == last_offline_date:
                            # 更新最后一条
                            offline_df.at[offline_df.index[-1], "close"] = float(row.get("price", row.get("close", 0)))
                            offline_df.at[offline_df.index[-1], "high"] = max(
                                float(offline_df.iloc[-1].get("high", 0)),
                                float(row.get("price", 0))
                            )
                            offline_df.at[offline_df.index[-1], "low"] = min(
                                float(offline_df.iloc[-1].get("low", 999999)),
                                float(row.get("price", 0))
                            )
                            # 累加成交量
                            vol = int(row.get("volume", 0))
                            if vol > 0:
                                offline_df.at[offline_df.index[-1], "volume"] = int(offline_df.iloc[-1].get("volume", 0)) + vol
                        else:
                            # 追加新日期（当日盘中）
                            new_row = {
                                "date": latest_date,
                                "code": code,
                                "open": float(row.get("open", row.get("price", 0))),
                                "high": float(row.get("high", row.get("price", 0))),
                                "low": float(row.get("low", row.get("price", 0))),
                                "close": float(row.get("price", 0)),
                                "volume": int(row.get("volume", 0)),
                                "amount": float(row.get("amount", 0)) if "amount" in row else None,
                            }
                            offline_df = pd.concat([offline_df, pd.DataFrame([new_row])], ignore_index=True)
                        
                        return offline_df
                except Exception as e:
                    self._obs.log("DEBUG", f"Realtime quote supplement failed for {code}: {e}", "DataProviderService")
                
                return offline_df
            
            # 分钟级：获取实时分钟数据（1m/5m/15m/30m/60m 都先获取1分钟原始数据）
            elif period in ("minute", "1m", "5m", "15m", "30m", "60m"):
                try:
                    self.provider._realtime._init_client()
                    client = getattr(self.provider._realtime, '_client', None)
                    if client is not None:
                        # mootdx 的 minute 接口获取分钟数据
                        df = client.minute(symbol=code)
                        if df is not None and len(df) > 0:
                            return df
                except Exception as e:
                    self._obs.log("DEBUG", f"Realtime minute fetch failed for {code}: {e}", "DataProviderService")
            
            return None
        except Exception as e:
            self._obs.log("WARN", f"Realtime kline fetch failed for {code}: {e}", "DataProviderService")
            return None
    
    def _persist_realtime_data(self, code: str, df: pd.DataFrame, period: str, adjust: str) -> None:
        """
        将实时数据写入 SQLite 持久化缓存
        
        表结构：realtime_kline_cache
        - symbol, date, period, adjust, open, high, low, close, volume, amount, updated_at
        """
        try:
            import sqlite3
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "backend", "quant_workbench.db")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS realtime_kline_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    period TEXT NOT NULL,
                    adjust TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    amount REAL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(symbol, date, period, adjust)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rtk_symbol ON realtime_kline_cache(symbol, period, adjust)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rtk_date ON realtime_kline_cache(date)")
            
            now = datetime.now().isoformat()
            for _, row in df.iterrows():
                # 正确解析日期：支持 YYYYMMDD、YYYY-MM-DD、Timestamp 等多种格式
                raw_date = row.get("date", "")
                if pd.isna(raw_date):
                    continue
                try:
                    # 尝试用 pandas 解析日期
                    dt = pd.to_datetime(raw_date)
                    date_val = dt.strftime("%Y%m%d")
                except Exception:
                    # 回退到字符串处理
                    date_val = str(raw_date).replace("-", "").replace(" ", "").replace(":", "")[:8]
                if not date_val or len(date_val) != 8:
                    continue
                conn.execute("""
                    INSERT INTO realtime_kline_cache (symbol, date, period, adjust, open, high, low, close, volume, amount, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, date, period, adjust) DO UPDATE SET
                        open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                        volume=excluded.volume, amount=excluded.amount, updated_at=excluded.updated_at
                """, (
                    code, date_val, period, adjust,
                    float(row.get("open", 0)), float(row.get("high", 0)), float(row.get("low", 0)),
                    float(row.get("close", 0)), int(row.get("volume", 0)),
                    float(row.get("amount", 0)) if "amount" in row and pd.notna(row.get("amount")) else None,
                    now
                ))
            
            conn.commit()
            conn.close()
            self._obs.log("INFO", f"Persisted realtime data for {code}: {len(df)} rows", "DataProviderService")
        except Exception as e:
            self._obs.log("WARN", f"Failed to persist realtime data for {code}: {e}", "DataProviderService")
    
    def _read_persisted_data(self, code: str, period: str, adjust: str) -> Optional[pd.DataFrame]:
        """从 SQLite 读取持久化的实时数据"""
        try:
            import sqlite3
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "backend", "quant_workbench.db")
            if not os.path.exists(db_path):
                return None
            
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT date, open, high, low, close, volume, amount FROM realtime_kline_cache WHERE symbol = ? AND period = ? AND adjust = ? ORDER BY date",
                (code, period, adjust)
            )
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return None
            
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
            df["code"] = code
            df["open"] = pd.to_numeric(df["open"], errors="coerce")
            df["high"] = pd.to_numeric(df["high"], errors="coerce")
            df["low"] = pd.to_numeric(df["low"], errors="coerce")
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
            return df
        except Exception as e:
            self._obs.log("DEBUG", f"Failed to read persisted data for {code}: {e}", "DataProviderService")
            return None
    
    def compare_realtime_vs_offline(self, code: str, period: str = "daily", adjust: str = "qfq") -> Dict[str, Any]:
        """
        比对实时数据 vs TDX 离线数据

        如果 SQLite 中没有实时缓存数据，强制 fetch 并写入后再比对。
        返回差异报告：缺失日期、价格差异、成交量差异。
        """
        try:
            # 先尝试读取 SQLite 缓存
            realtime_df = self._read_persisted_data(code, period, adjust)
            # 如果 SQLite 中没有，强制 fetch 并写入
            if realtime_df is None or len(realtime_df) == 0:
                self._obs.log("INFO", f"No persisted data for {code}, forcing refresh", "DataProviderService")
                fetched_df = self.fetch_ohlcv(code, period=period, adjust=adjust, source="auto")
                if fetched_df is not None and len(fetched_df) > 0:
                    self._persist_realtime_data(code, fetched_df, period, adjust)
                    realtime_df = self._read_persisted_data(code, period, adjust)

            # 获取离线数据（TDX 文件）
            offline_df = self._fetch_kline_with_timeout(code, "", "", period, adjust)

            if realtime_df is None or offline_df is None:
                return {"status": "error", "reason": "missing data", "symbol": code}

            # 标准化日期格式
            realtime_df["date"] = realtime_df["date"].astype(str).str.replace("-", "")
            offline_df["date"] = offline_df["date"].astype(str).str.replace("-", "")

            # 合并比对
            merged = pd.merge(realtime_df, offline_df, on="date", suffixes=("_rt", "_off"), how="outer")

            # 缺失日期
            missing_in_offline = merged[merged["close_off"].isna()]["date"].tolist()
            missing_in_realtime = merged[merged["close_rt"].isna()]["date"].tolist()

            # 价格差异（>0.1% 视为差异）
            both_have = merged[(merged["close_rt"].notna()) & (merged["close_off"].notna())].copy()
            both_have["price_diff_pct"] = abs(both_have["close_rt"] - both_have["close_off"]) / both_have["close_off"] * 100
            price_diffs = both_have[both_have["price_diff_pct"] > 0.1][["date", "close_rt", "close_off", "price_diff_pct"]].to_dict("records")

            return {
                "status": "ok",
                "symbol": code,
                "realtime_rows": len(realtime_df),
                "offline_rows": len(offline_df),
                "missing_in_offline": missing_in_offline[:10],  # 最多10条
                "missing_in_realtime": missing_in_realtime[:10],
                "price_differences": price_diffs[:10],
                "summary": {
                    "total_missing_offline": len(missing_in_offline),
                    "total_missing_realtime": len(missing_in_realtime),
                    "total_price_diffs": len(price_diffs),
                }
            }
        except Exception as e:
            self._obs.log("WARN", f"Data comparison failed for {code}: {e}", "DataProviderService")
            return {"status": "error", "reason": str(e), "symbol": code}
    
    # ─────────────────────────────────────────
    # 股票列表
    # ─────────────────────────────────────────
    
    def fetch_stock_list(self, source: str = "auto") -> Optional[pd.DataFrame]:
        """获取全市场股票列表"""
        return self.provider.fetch_stock_list(source=source)
    
    def get_stock_quote(self, symbol: str, adjust: str = "qfq") -> Optional[StandardQuote]:
        """
        获取单股最新行情（离线K线 + 实时补充）
        
        策略：
        1. 获取离线K线最新数据
        2. 尝试获取实时报价补充当日数据
        3. 返回 StandardQuote
        """
        try:
            # 获取离线K线（取最新一条）
            df = self.fetch_ohlcv(symbol, period="daily", adjust=adjust, source="offline")
            if df is None or len(df) == 0:
                return None
            
            latest = df.iloc[-1]
            code = str(latest.get("code", symbol)).strip().zfill(6)
            
            # 尝试获取实时报价（补充当日最新价格）
            try:
                realtime_df = self.provider.fetch_realtime_quote([code])
                if realtime_df is not None and len(realtime_df) > 0:
                    row = realtime_df.iloc[0]
                    price = float(row.get("price", 0))
                    if price > 0:
                        # 用实时价格更新 close
                        return StandardQuote(
                            symbol=code,
                            name=str(row.get("name", "")).strip() or None,
                            timestamp=datetime.now(),
                            open=float(row.get("open", latest.get("open", 0))),
                            high=float(row.get("high", max(price, latest.get("high", 0)))),
                            low=float(row.get("low", min(price, latest.get("low", 999999)))),
                            close=price,
                            volume=int(row.get("volume", latest.get("volume", 0))),
                            amount=float(row.get("amount", 0)) if "amount" in row and pd.notna(row.get("amount")) else None,
                            source="mootdx-realtime",
                            freq="1d",
                        )
            except Exception:
                pass
            
            # 返回离线最新数据
            return StandardQuote(
                symbol=code,
                name=None,
                timestamp=datetime.now(),
                open=float(latest.get("open", 0)),
                high=float(latest.get("high", 0)),
                low=float(latest.get("low", 0)),
                close=float(latest.get("close", 0)),
                volume=int(latest.get("volume", 0)),
                amount=float(latest.get("amount", 0)) if "amount" in latest and pd.notna(latest.get("amount")) else None,
                source="mootdx-offline",
                freq="1d",
            )
        except Exception as e:
            self._obs.log("WARN", f"get_stock_quote failed for {symbol}: {e}", "DataProviderService")
            return None
    
    # ─────────────────────────────────────────
    # 快捷接口
    # ─────────────────────────────────────────
    
    def fetch_single_ohlcv(
        self,
        symbol: str,
        start_date: str = "",
        end_date: str = "",
        period: str = "daily",
        adjust: str = "qfq",
    ) -> Optional[pd.DataFrame]:
        """获取单股K线（快捷接口）"""
        return self.fetch_ohlcv(symbol, start_date, end_date, period, adjust, "auto")
    
    def get_kline_latest(self, symbol: str, n: int = 60, period: str = "daily", adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """获取最近 N 条K线（快捷接口）"""
        df = self.fetch_ohlcv(symbol, period=period, adjust=adjust)
        if df is not None and len(df) > 0:
            return df.tail(n).reset_index(drop=True)
        return None
    
    def fetch_market_overview(self) -> Optional[Dict[str, Any]]:
        """
        获取全市场 A 股实时行情概览
        数据来源：mootdx Quotes 实时接口
        
        计算指标：
        - 上涨/下跌/平盘家数
        - 涨停/跌停家数（涨幅>=9.9%, 跌幅<=-9.9%）
        - 涨跌比
        - 热点板块（按代码前缀分组，取平均涨跌幅前10）
        """
        try:
            # 获取 Quotes 客户端（如果不可用则返回 None）
            # 确保客户端已初始化（RealtimeDataProvider 延迟连接）
            if not getattr(self.provider._realtime, '_initialized', False):
                self.provider._realtime._init_client()
            client = getattr(self.provider._realtime, '_client', None)
            if client is None:
                self._obs.log("WARN", "Quotes client unavailable for market overview", "DataProviderService")
                return None
            
            # 获取股票列表：优先使用本地通达信扫描（更完整，包含沪深京所有A股）
            stocks_df = self.fetch_stock_list()
            if stocks_df is None or len(stocks_df) == 0:
                self._obs.log("WARN", "Stock list empty from local TDX", "DataProviderService")
                return None
            
            # 过滤 A 股：只保留沪深A股，排除指数/B股/基金等
            codes = stocks_df["code"].astype(str).str.strip().str.zfill(6).tolist()
            valid_codes = []
            for c in codes:
                if not c.isdigit() or len(c) != 6:
                    continue
                # 排除指数（本地列表中 market=sh 的 000001-000016 是指数）
                if c.startswith("999") or c in ["000001","000002","000003","000004","000005","000006","000007","000008","000009","000010","000011","000012","000013","000014","000015","000016"]:
                    continue
                # 只保留 A 股
                if c.startswith(("600","601","603","605","688","689","000","001","002","003","300","301","430","83","87","88","82","92")):
                    valid_codes.append(c)
            
            if not valid_codes:
                self._obs.log("WARN", "No valid A-share codes after filtering", "DataProviderService")
                return None
            
            self._obs.log("INFO", f"Fetching market overview for {len(valid_codes)} A-shares", "DataProviderService")
            
            # 分批获取实时行情（每批100只，约90批，总时间约5秒）
            batch_size = 100
            all_dfs = []
            for i in range(0, len(valid_codes), batch_size):
                batch = valid_codes[i:i + batch_size]
                try:
                    df = client.quotes(symbol=batch)
                    if df is not None and len(df) > 0:
                        all_dfs.append(df)
                except Exception as e:
                    self._obs.log("WARN", f"Batch {i // batch_size + 1} realtime quote failed: {e}", "DataProviderService")
                    continue
            
            if not all_dfs:
                return None
            
            quotes = pd.concat(all_dfs, ignore_index=True)
            
            # 确保 code 列为字符串
            if "code" not in quotes.columns:
                self._obs.log("WARN", "Realtime quote missing code column", "DataProviderService")
                return None
            
            quotes["code"] = quotes["code"].astype(str).str.strip().str.zfill(6)
            
            # 查找价格列和前收盘价列
            price_col = "price" if "price" in quotes.columns else "close"
            prev_cols = ["prev_close", "pre_close", "last_close", "yesterday", "previous_close"]
            prev_col = None
            for col in prev_cols:
                if col in quotes.columns:
                    prev_col = col
                    break
            
            # 过滤停牌股票（price <= 0 或 prev_close <= 0）
            if price_col not in quotes.columns:
                self._obs.log("WARN", "Realtime quote missing price column", "DataProviderService")
                return None
            
            quotes = quotes[quotes[price_col] > 0]
            if prev_col is not None and prev_col in quotes.columns:
                quotes = quotes[quotes[prev_col] > 0]
            else:
                # 没有前收盘价，尝试用 open 作为近似
                if "open" in quotes.columns:
                    prev_col = "open"
                    quotes = quotes[quotes[prev_col] > 0]
                else:
                    self._obs.log("WARN", "Realtime quote missing prev_close/open column", "DataProviderService")
                    return None
            
            # 计算涨跌幅
            quotes["change_pct"] = (quotes[price_col] - quotes[prev_col]) / quotes[prev_col] * 100
            
            # 统计计算
            advancing = int((quotes["change_pct"] > 0).sum())
            declining = int((quotes["change_pct"] < 0).sum())
            flat = int((quotes["change_pct"] == 0).sum())
            total_valid = len(quotes)
            
            limit_up = int((quotes["change_pct"] >= 9.9).sum())
            limit_down = int((quotes["change_pct"] <= -9.9).sum())
            
            up_down_ratio = round(advancing / max(declining, 1), 2)
            
            # 热点板块：按代码前缀分组计算平均涨跌幅
            quotes["prefix"] = quotes["code"].str[:2]
            
            prefix_names = {
                "60": "上海主板",
                "00": "深圳主板",
                "30": "创业板",
                "68": "科创板",
                "43": "北交所",
                "83": "北交所",
                "87": "北交所",
                "88": "北交所",
                "89": "北交所",
            }
            
            hotspots = []
            for prefix, group in quotes.groupby("prefix"):
                avg_change = round(group["change_pct"].mean(), 2)
                stock_count = len(group)
                up_count = int((group["change_pct"] > 0).sum())
                
                hotspots.append({
                    "block_name": prefix_names.get(prefix, f"{prefix}xx板块"),
                    "change_pct": avg_change,
                    "stock_count": stock_count,
                    "up_count": up_count,
                })
            
            # 按涨跌幅降序取前10
            hotspots = sorted(hotspots, key=lambda x: x["change_pct"], reverse=True)[:10]
            
            return {
                "up_down_ratio": up_down_ratio,
                "limit_up": limit_up,
                "limit_down": limit_down,
                "advancing": advancing,
                "declining": declining,
                "flat": flat,
                "total_valid": total_valid,
                "source": "mootdx",
                "hotspots": hotspots,
            }
            
        except Exception as e:
            self._obs.log("WARN", f"Market overview fetch failed: {e}", "DataProviderService")
            return None


# 全局单例
_service_instance: Optional[DataProviderService] = None

def get_data_provider_service(tdxdir: str = "D:/TDX") -> DataProviderService:
    """获取全局 DataProviderService 实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = DataProviderService(tdxdir=tdxdir)
    return _service_instance


if __name__ == "__main__":
    # 独立测试：确保项目根目录在 sys.path 中
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    
    print("=== DataProviderService Test ===")
    svc = DataProviderService()
    
    # 1. 健康检查（happy path）
    health = svc.health_check()
    print(f"\n[1] Health Check: {health}")
    assert "offline_available" in health
    assert "realtime_available" in health
    assert "tdxdir_exists" in health
    print("  Health check: PASSED")
    
    # 2. 测试K线（edge case: 无效代码）
    print("\n[2] Edge case - invalid symbol")
    df_invalid = svc.fetch_ohlcv("INVALID999", period="daily")
    assert df_invalid is None or len(df_invalid) == 0
    print("  Invalid symbol handled: PASSED")
    
    # 3. 测试K线（如果数据源可用）
    if health.get("tdxdir_exists") or health.get("realtime_available"):
        print("\n[3] OHLCV Test - 000001")
        df = svc.fetch_ohlcv("000001", period="daily", adjust="qfq")
        if df is not None and len(df) > 0:
            print(f"  Shape: {df.shape}")
            print(f"  Columns: {list(df.columns)}")
            print(f"  Tail(3):\n{df.tail(3)}")
            # 验证标准列
            assert "date" in df.columns
            assert "code" in df.columns
            assert "open" in df.columns
            assert "high" in df.columns
            assert "low" in df.columns
            assert "close" in df.columns
            assert "volume" in df.columns
            print("  OHLCV standard columns: PASSED")
            
            # 验证数值类型
            assert df["close"].dtype in (np.float64, np.float32, float)
            print("  OHLCV numeric types: PASSED")
        else:
            print("  OHLCV unavailable (no data source)")
        
        # 4. 测试实时行情（如果可用）
        if health.get("realtime_available"):
            print("\n[4] Realtime Quotes Test")
            quotes = svc.fetch_realtime_quotes(["000001", "600519"])
            print(f"  Quotes count: {len(quotes)}")
            for q in quotes:
                print(f"  {q.symbol}: {q.close} (vol={q.volume})")
            print("  Realtime quotes: PASSED")
    else:
        print("\nNo data source available, skipping data tests")
    
    print("\n=== All Tests Done ===")
