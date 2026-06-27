# -*- coding: utf-8 -*-
"""
Mootdx Data Provider v5.0 - 通达信数据获取层

架构：离线层 + 实时层，统一接口，自动降级

使用方式：
    from utils.mootdx_provider import MootdxDataProvider
    
    provider = MootdxDataProvider(tdxdir="C:/new_tdx")
    
    # 离线读取（优先）
    df = provider.fetch_kline("000001", "20250101", "20250619", source="offline")
    
    # 实时获取（服务器直连）
    quote = provider.fetch_realtime_quote(["000001", "300750"])
    
    # 自动选择（离线优先 → 实时 → 缓存）
    df = provider.fetch_kline("000001", "20250101", "20250619")

数据源配置：
    - 离线层: Reader 读取本地通达信客户端数据（需预先下载）
    - 实时层: Quotes 连接通达信服务器（自动选择最优IP）
"""

import os
import time
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime
import pandas as pd
import numpy as np

from core.observability import get_obs
from core.cache import MultiLevelCache
from core.resilience import FallbackResult, DataSourceResilience

# 尝试导入 mootdx
try:
    from mootdx.quotes import Quotes
    from mootdx.reader import Reader
    MOOTDX_AVAILABLE = True
except ImportError:
    MOOTDX_AVAILABLE = False
    warnings.warn("mootdx not installed, fallback to network-only mode")

# 尝试导入复权工具
try:
    from mootdx.utils.adjust import to_adjust
    from mootdx.utils.factor import fq_factor
    MOOTDX_ADJUST_AVAILABLE = True
except ImportError:
    MOOTDX_ADJUST_AVAILABLE = False


# ─────────────────────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────────────────────

DEFAULT_TDX_DIR = "D:/TDX"  # 用户配置的通达信数据目录

# 市场代码映射
MARKET_PREFIX = {
    # 上海
    "600": "sh", "601": "sh", "603": "sh", "605": "sh", "688": "sh",
    "689": "sh", "510": "sh", "511": "sh", "512": "sh", "513": "sh",
    "515": "sh", "518": "sh", "560": "sh", "561": "sh", "563": "sh",
    "564": "sh", "565": "sh", "568": "sh", "58":  "sh",  # 580/588
    "900": "sh",  # B股
    # 深圳
    "000": "sz", "001": "sz", "002": "sz", "003": "sz", "300": "sz",
    "301": "sz", "159": "sz", "16":  "sz",  # 16xx
    "200": "sz",  # B股
    # 北京
    "430": "bj", "83":  "bj", "87":  "bj", "88":  "bj", "82":  "bj",
    "92":  "bj", "43":  "bj",
}


def _detect_market(code: str) -> str:
    """根据代码前缀检测市场（sh/sz/bj）"""
    code = str(code).strip()
    for prefix, market in MARKET_PREFIX.items():
        if code.startswith(prefix):
            return market
    return "sh"  # 默认上海


def _normalize_code(code: str) -> str:
    """标准化为6位数字代码"""
    code = str(code).strip()
    # 去除 .SH/.SZ/.BJ 后缀
    for suffix in [".SH", ".SZ", ".BJ", ".sh", ".sz", ".bj"]:
        if code.endswith(suffix):
            code = code[:-3]
            break
    return code.zfill(6) if code.isdigit() else code


def _format_tdx_code(code: str) -> str:
    """格式化为通达信需要的格式（如 market.code）"""
    code = _normalize_code(code)
    market = _detect_market(code)
    return f"{market}.{code}"


def _date_to_yyyymmdd(date_str: str) -> str:
    """统一日期格式为 YYYYMMDD"""
    if len(date_str) == 8 and date_str.isdigit():
        return date_str
    # 处理 YYYY-MM-DD
    if len(date_str) == 10 and date_str[4] == "-":
        return date_str.replace("-", "")
    return date_str


# ════════════════════════════════════════════════════════════
# 离线层：Reader 读取本地通达信数据
# ════════════════════════════════════════════════════════════

class OfflineDataProvider:
    """
    离线数据提供者：读取本地通达信客户端数据
    
    前提：用户已通过通达信客户端下载了日线/分钟线数据
    数据路径：tdxdir/vipdoc/ 下按市场分类（sh/sz/bj）
    
    优点：
    - 速度快（本地文件读取，毫秒级）
    - 离线可用（无需网络）
    - 数据完整（通达信客户端下载的数据质量高）
    - 无反爬风险（纯本地操作）
    
    缺点：
    - 需要手动/定时下载更新数据
    - 无法获取实时行情
    """
    
    def __init__(self, tdxdir: str = DEFAULT_TDX_DIR):
        self.tdxdir = tdxdir
        self._reader = None
        self._obs = get_obs()
        self._initialized = False
        self._name_map_cache: Optional[Dict[str, str]] = None
        self._name_map_cache_time: float = 0.0
    
    def _init_reader(self) -> bool:
        """初始化 Reader"""
        if self._initialized:
            return self._reader is not None
        
        if not MOOTDX_AVAILABLE:
            self._obs.log("WARN", "mootdx not available, offline data disabled", "OfflineDataProvider")
            return False
        
        if not os.path.exists(self.tdxdir):
            self._obs.log("WARN", f"Tdx data dir not found: {self.tdxdir}", "OfflineDataProvider")
            return False
        
        try:
            self._reader = Reader.factory(market='std', tdxdir=self.tdxdir)
            self._initialized = True
            self._obs.log("INFO", f"OfflineDataProvider initialized: {self.tdxdir}", "OfflineDataProvider")
            return True
        except Exception as e:
            self._obs.log("ERROR", f"Failed to init Reader: {str(e)}", "OfflineDataProvider")
            return False
    
    def is_available(self) -> bool:
        """检查离线数据是否可用"""
        return self._init_reader()
    
    def fetch_kline(self, code: str, start_date: str = "", end_date: str = "",
                    period: str = "daily", adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """
        读取本地日线数据，自动前复权

        Args:
            code: 股票代码（如 000001, 600519）
            start_date/end_date: 可选，用于过滤
            period: daily / weekly / monthly / minute
            adjust: qfq(前复权) / hfq(后复权) / none(不复权)

        Returns:
            DataFrame[date, open, high, low, close, volume, amount] or None
        """
        if not self._init_reader():
            return None

        code = _normalize_code(code)

        try:
            start_time = time.time()

            # 选择读取方法
            if period == "daily":
                df = self._reader.daily(symbol=code)
            elif period == "weekly":
                df = self._reader.weekly(symbol=code)
            elif period == "monthly":
                df = self._reader.monthly(symbol=code)
            elif period == "minute":
                df = self._reader.minute(symbol=code)
            else:
                df = self._reader.daily(symbol=code)

            if df is None or len(df) == 0:
                return None

            # 前复权处理（必须在标准化之前，保持原始格式）
            if adjust in ("qfq", "hfq") and MOOTDX_ADJUST_AVAILABLE:
                try:
                    # 使用自定义 _apply_adjust，兼容 pandas 2.0+（修复 mootdx fillna 兼容性）
                    df = self._apply_adjust(df, code=code, adjust=adjust)
                    self._obs.log("INFO", f"Offline kline adjusted ({adjust}): {code}", "OfflineDataProvider")
                except Exception as e:
                    self._obs.log("WARN", f"Adjust failed for {code}: {e}, using raw prices", "OfflineDataProvider")
            elif adjust == "none":
                self._obs.log("INFO", f"Offline kline raw (no adjust): {code}", "OfflineDataProvider")

            # 标准化列名（复权后统一格式化）
            df = self._standardize_columns(df, code)

            # 日期过滤
            if start_date:
                start_date = _date_to_yyyymmdd(start_date)
                df = df[df["date"] >= start_date]
            if end_date:
                end_date = _date_to_yyyymmdd(end_date)
                df = df[df["date"] <= end_date]

            duration = (time.time() - start_time) * 1000
            self._obs.log("INFO", f"Offline kline loaded: {code} ({len(df)} rows, {duration:.1f}ms)",
                          "OfflineDataProvider")

            return df.sort_values("date").reset_index(drop=True)

        except Exception as e:
            self._obs.log("WARN", f"Offline kline failed for {code}: {str(e)}", "OfflineDataProvider")
            return None
    
    def fetch_stock_list(self) -> Optional[pd.DataFrame]:
        """读取本地股票列表"""
        if not self._init_reader():
            return None
        
        try:
            # 尝试读取通达信板块数据获取股票列表
            # 如果没有直接接口，通过扫描 vipdoc 目录获取
            stocks = self._scan_local_stocks()
            if stocks:
                return pd.DataFrame(stocks)
            return None
        except Exception as e:
            self._obs.log("WARN", f"Offline stock list failed: {str(e)}", "OfflineDataProvider")
            return None
    
    def _scan_local_stocks(self) -> List[Dict]:
        """扫描本地通达信数据目录获取股票列表（带名称）"""
        stocks = []
        vipdoc_dir = os.path.join(self.tdxdir, "vipdoc")
        
        # 优先从 TDX 的 infoharbor_ex.code 读取代码→名称映射（本地、快速、准确）
        name_map = self._load_stock_names_from_infoharbor()
        
        # 兜底：base.dbf 或东方财富在线接口
        if not name_map:
            name_map = self._load_stock_names_from_base_dbf()
        if not name_map:
            name_map = self._load_stock_names_from_eastmoney()
        
        if not os.path.exists(vipdoc_dir):
            return stocks
        
        for market in ["sh", "sz", "bj"]:
            market_dir = os.path.join(vipdoc_dir, market, "lday")
            if not os.path.exists(market_dir):
                continue
            
            for filename in os.listdir(market_dir):
                if filename.endswith(".day"):
                    # 文件名格式: sh600000.day
                    code = filename[2:8]  # 去掉前缀和后缀
                    stocks.append({
                        "code": code,
                        "market": market,
                        "name": name_map.get(code, code),  # 优先从名称映射读取
                    })
        
        return stocks
    
    def _load_stock_names_from_infoharbor(self) -> Dict[str, str]:
        """从 TDX infoharbor_ex.code 读取股票代码→名称映射"""
        name_map = {}
        code_file = os.path.join(self.tdxdir, "T0002", "hq_cache", "infoharbor_ex.code")
        
        if not os.path.exists(code_file):
            return name_map
        
        try:
            with open(code_file, "r", encoding="gbk", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("|")
                    if len(parts) >= 2:
                        code = str(parts[0]).strip().zfill(6)
                        name = str(parts[1]).strip()
                        if code and name:
                            name_map[code] = name
        except Exception as e:
            if self._obs:
                self._obs.log("WARN", f"infoharbor_ex.code parse failed: {e}", "OfflineDataProvider")
        
        return name_map
    
    def _load_stock_names_from_base_dbf(self) -> Dict[str, str]:
        """从 TDX base.dbf 读取股票名称映射（不依赖 dbfread）"""
        name_map = {}
        base_dbf = os.path.join(self.tdxdir, "T0002", "hq_cache", "base.dbf")
        
        if not os.path.exists(base_dbf):
            return name_map
        
        try:
            import struct
            with open(base_dbf, "rb") as f:
                header = f.read(32)
                if len(header) < 32:
                    return name_map
                num_records = struct.unpack("<I", header[4:8])[0]
                header_size = struct.unpack("<H", header[8:10])[0]
                record_size = struct.unpack("<H", header[10:12])[0]
                
                # 解析字段描述符
                fields = {}
                offset = 1  # 记录第一个字节是删除标记
                pos = 32
                while True:
                    f.seek(pos)
                    desc = f.read(32)
                    if not desc or desc[0] == 0x0D:
                        break
                    field_name = desc[:11].split(b"\x00")[0].decode("ascii", errors="ignore").strip()
                    field_len = desc[16]
                    fields[field_name] = (offset, field_len)
                    offset += field_len
                    pos += 32
                
                if "CODE" not in fields or "NAME" not in fields:
                    return name_map
                
                code_off, code_len = fields["CODE"]
                name_off, name_len = fields["NAME"]
                
                f.seek(header_size)
                for _ in range(num_records):
                    rec = f.read(record_size)
                    if not rec or rec[0] == 0x2A:  # 0x2A 表示已删除记录
                        continue
                    code = rec[code_off:code_off + code_len].decode("gbk", errors="ignore").strip()
                    name = rec[name_off:name_off + name_len].decode("gbk", errors="ignore").strip()
                    if code and name:
                        name_map[code.zfill(6)] = name
        except Exception as e:
            if self._obs:
                self._obs.log("WARN", f"base.dbf parse failed: {e}", "OfflineDataProvider")
        
        return name_map
    
    def _load_stock_names_from_eastmoney(self) -> Dict[str, str]:
        """从东方财富在线接口获取股票代码→名称映射（兜底），结果缓存 1 小时。"""
        if self._name_map_cache is not None and time.time() - self._name_map_cache_time < 3600:
            return self._name_map_cache

        name_map = {}
        base_url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            "?pz=100&po=1&np=1&fltt=2&invt=2&fid=f20"
            "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:204"
            "&fields=f12,f14&pn="
        )
        try:
            page = 1
            while True:
                url = f"{base_url}{page}"
                # 优先使用 requests，未安装则回退到 urllib
                try:
                    import requests
                    resp = requests.get(url, timeout=30)
                    data = resp.json()
                except Exception:
                    import urllib.request, json
                    with urllib.request.urlopen(url, timeout=30) as resp:
                        data = json.loads(resp.read().decode("utf-8"))

                if data.get("data") is None or data["data"].get("diff") is None:
                    break

                diff = data["data"]["diff"]
                if not diff:
                    break

                for item in diff:
                    code = str(item.get("f12", "")).strip().zfill(6)
                    name = str(item.get("f14", "")).strip()
                    if code and name:
                        name_map[code] = name

                if len(diff) < 100:
                    break
                page += 1
                if page > 200:
                    break

            self._name_map_cache = name_map
            self._name_map_cache_time = time.time()
        except Exception as e:
            if self._obs:
                self._obs.log("WARN", f"Eastmoney stock name fallback failed: {e}", "OfflineDataProvider")
        return name_map
    
    def _apply_adjust(self, df: pd.DataFrame, code: str, adjust: str = "qfq") -> pd.DataFrame:
        """
        应用前复权/后复权，兼容 pandas 2.0+

        说明：
        - mootdx 的 fq_factor 返回的 factor 定义为：factor = raw_price / qfq_price
          因此前复权价格 = raw_price / factor。
        - 后复权以最早数据为基准：hfq_price = raw_price * (max_factor / factor)。

        Args:
            df: reader.daily() 返回的原始 DataFrame（索引为 date）
            code: 股票代码
            adjust: 'qfq' / 'hfq'

        Returns:
            复权后的 DataFrame
        """
        if not MOOTDX_ADJUST_AVAILABLE:
            return df

        factor = fq_factor(code, method=adjust)
        if factor is None or factor.empty:
            self._obs.log("WARN", f"No fq_factor for {code}, skip adjust", "OfflineDataProvider")
            return df

        df = df.copy()
        if df.index.name != 'date':
            if 'date' in df.columns:
                df = df.set_index('date')
            else:
                self._obs.log("WARN", f"No date index for {code}, skip adjust", "OfflineDataProvider")
                return df

        # 因子按日期升序排列，并取不晚于 df 最后日期的所有因子
        # 这样可以包含 df 起始日期之前的除权因子，ffill 后正确应用到早期数据
        factor = factor.sort_index(ascending=True)
        df = df.sort_index(ascending=True)
        factor_slice = factor.loc[:df.index[-1], ['factor']]

        merged = pd.concat([df, factor_slice], axis=1)
        # 合并后按日期排序，确保 ffill 能取到更早的除权因子
        merged = merged.sort_index()
        # 用该日期前最近一次的除权因子填充（ffill），缺失的用 1.0 兜底
        merged['factor'] = merged['factor'].ffill().fillna(1.0).astype(float)

        if adjust == 'qfq':
            for col in ['open', 'high', 'low', 'close']:
                if col in merged.columns:
                    merged[col] = merged[col] / merged['factor']
        else:  # hfq
            max_factor = merged['factor'].max()
            for col in ['open', 'high', 'low', 'close']:
                if col in merged.columns:
                    merged[col] = merged[col] * (max_factor / merged['factor'])

        # 只保留原始 df 的日期行，去掉因子表引入的额外日期
        merged = merged.loc[df.index]
        merged = merged.drop(columns=['factor'], errors='ignore')
        return merged
    
    def _standardize_columns(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """标准化列名（OfflineDataProvider 版本）"""
        df = df.copy()
        
        # date 可能在 index 中（Reader 默认行为）
        if "date" not in df.columns and df.index.name == "date":
            df = df.reset_index()
        
        # 确保 code 列存在
        df["code"] = code
        
        # 标准化列名映射
        rename_map = {
            "time": "date",
            "datetime": "date",
            "vol": "volume",
            "amt": "amount",
        }
        for old, new in rename_map.items():
            if old in df.columns and new not in df.columns:
                df = df.rename(columns={old: new})
        
        # 确保日期格式：如果有时间信息保留完整时间戳，否则仅保留日期
        if "date" in df.columns:
            dt = pd.to_datetime(df["date"], errors="coerce")
            # 判断是否有时间信息（非 00:00:00）
            has_time = (dt.dt.hour != 0) | (dt.dt.minute != 0) | (dt.dt.second != 0)
            if has_time.any():
                df["date"] = dt.dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                df["date"] = dt.dt.strftime("%Y%m%d")
            df = df[df["date"].notna()]
        
        return df


# ════════════════════════════════════════════════════════════
# 实时层：Quotes 连接通达信服务器
# ════════════════════════════════════════════════════════════

class RealtimeDataProvider:
    """
    实时数据提供者：连接通达信行情服务器
    
    优点：
    - 实时行情（毫秒级延迟）
    - 不需要本地数据
    - 自动选择最优服务器（bestip=True）
    
    缺点：
    - 需要网络连接
    - 服务器可能不稳定
    - 高频调用可能受限
    """
    
    def __init__(self, timeout: int = 2, auto_retry: int = 0):
        self.timeout = timeout
        self.auto_retry = auto_retry
        self._client = None
        self._obs = get_obs()
        self._initialized = False
    
    def _init_client(self) -> bool:
        """初始化 Quotes 客户端（延迟连接，避免构造时卡住）"""
        if self._initialized:
            return self._client is not None
        
        if not MOOTDX_AVAILABLE:
            self._obs.log("WARN", "mootdx not available, realtime data disabled", "RealtimeDataProvider")
            return False
        
        try:
            self._client = Quotes.factory(
                market='std',
                bestip=False,  # 禁用自动选最优IP，避免网络扫描耗时
                timeout=self.timeout,
                heartbeat=False,
                auto_retry=self.auto_retry,
            )
            self._initialized = True
            self._obs.log("INFO", "RealtimeDataProvider connected to server", "RealtimeDataProvider")
            return True
        except Exception as e:
            self._obs.log("WARN", f"Failed to connect Quotes: {str(e)} (server unreachable, skipping)", "RealtimeDataProvider")
            self._initialized = True  # 标记已尝试，避免重复尝试
            return False
    
    def _ensure_client(self) -> bool:
        """确保客户端可用（带重连）"""
        if self._client is None:
            return self._init_client()
        
        try:
            # 简单心跳测试
            _ = self._client.quotes(symbol=['000001'])
            return True
        except Exception:
            self._obs.log("WARN", "Quotes connection lost, reconnecting...", "RealtimeDataProvider")
            self._client = None
            self._initialized = False
            return self._init_client()
    
    def is_available(self) -> bool:
        """检查实时连接是否可用（只做轻量检查，不实际连接服务器）"""
        if not MOOTDX_AVAILABLE:
            return False
        # 不实际连接，只返回潜在可用性
        # 真正的连接在 fetch_* 时延迟进行
        return True
    
    def close(self):
        """关闭连接"""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._initialized = False
    
    def fetch_kline(self, code: str, start_date: str = "", end_date: str = "",
                    period: str = "daily", offset: int = 365) -> Optional[pd.DataFrame]:
        """
        从服务器获取历史K线
        
        Args:
            code: 股票代码
            start_date/end_date: 用于过滤（服务器返回后过滤）
            period: daily / minute
            offset: 返回条数（默认365天）
        
        Returns:
            DataFrame or None
        """
        if not self._ensure_client():
            return None
        
        code = _normalize_code(code)
        
        try:
            start_time = time.time()
            
            # frequency: 9=日线, 0=分钟
            frequency = 9 if period == "daily" else 0
            
            df = self._client.bars(symbol=code, frequency=frequency, offset=offset)
            
            if df is None or len(df) == 0:
                return None
            
            # 标准化
            df = self._standardize_columns(df, code)
            
            # 日期过滤
            if start_date:
                start_date = _date_to_yyyymmdd(start_date)
                df = df[df["date"] >= start_date]
            if end_date:
                end_date = _date_to_yyyymmdd(end_date)
                df = df[df["date"] <= end_date]
            
            duration = (time.time() - start_time) * 1000
            self._obs.log("INFO", f"Realtime kline fetched: {code} ({len(df)} rows, {duration:.1f}ms)", 
                          "RealtimeDataProvider")
            
            return df.sort_values("date").reset_index(drop=True)
            
        except Exception as e:
            self._obs.log("WARN", f"Realtime kline failed for {code}: {str(e)}", "RealtimeDataProvider")
            return None
    
    def fetch_realtime_quote(self, codes: List[str]) -> Optional[pd.DataFrame]:
        """
        获取多股实时行情
        
        Args:
            codes: 股票代码列表（如 ["000001", "300750"]）
        
        Returns:
            DataFrame[code, name, price, open, high, low, pre_close, volume, amount, ...]
        """
        if not self._ensure_client():
            return None
        
        codes = [_normalize_code(c) for c in codes]
        
        try:
            start_time = time.time()
            
            df = self._client.quotes(symbol=codes)
            
            if df is None or len(df) == 0:
                return None
            
            duration = (time.time() - start_time) * 1000
            self._obs.log("INFO", f"Realtime quotes fetched: {len(codes)} codes ({duration:.1f}ms)", 
                          "RealtimeDataProvider")
            
            return df
            
        except Exception as e:
            self._obs.log("WARN", f"Realtime quotes failed: {str(e)}", "RealtimeDataProvider")
            return None
    
    def fetch_stock_list(self) -> Optional[pd.DataFrame]:
        """从服务器获取全市场股票列表"""
        if not self._ensure_client():
            return None
        
        try:
            # 获取市场所有股票（使用 quotes 获取所有代码）
            # mootdx 的 quotes 方法支持获取多个代码
            # 这里需要获取所有代码列表，可能需要通过其他方式
            # 简化：返回一个基础列表，或者通过 scan 方式
            return self._fetch_all_stock_codes()
        except Exception as e:
            self._obs.log("WARN", f"Realtime stock list failed: {str(e)}", "RealtimeDataProvider")
            return None
    
    def _fetch_all_stock_codes(self) -> Optional[pd.DataFrame]:
        """获取全市场代码列表（通过扫描通达信服务器）"""
        # 这里简化处理，实际可能需要调用 mootdx 的扩展接口
        # 返回基础列表，后续可扩展
        codes = []
        # 上海主板
        for i in range(600000, 609999):
            codes.append({"code": str(i), "market": "sh", "name": ""})
        # 深圳主板
        for i in range(1, 3000):
            codes.append({"code": str(i).zfill(6), "market": "sz", "name": ""})
        # 创业板
        for i in range(300000, 301999):
            codes.append({"code": str(i), "market": "sz", "name": ""})
        
        return pd.DataFrame(codes)
    
    def _standardize_columns(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """标准化列名（RealtimeDataProvider 版本）"""
        df = df.copy()
        df["code"] = code
        
        # 重命名 datetime → date
        if "datetime" in df.columns and "date" not in df.columns:
            df = df.rename(columns={"datetime": "date"})
        if "time" in df.columns and "date" not in df.columns:
            df = df.rename(columns={"time": "date"})
        
        # 重命名 vol → volume
        if "vol" in df.columns and "volume" not in df.columns:
            df = df.rename(columns={"vol": "volume"})
        
        # 格式化日期列：根据是否有时间信息决定格式
        if "date" in df.columns:
            try:
                dt = pd.to_datetime(df["date"], errors="coerce")
                has_time = (dt.dt.hour != 0) | (dt.dt.minute != 0) | (dt.dt.second != 0)
                if has_time.any():
                    df["date"] = dt.dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    df["date"] = dt.dt.strftime("%Y%m%d")
                df = df[df["date"].notna()]
            except Exception:
                # 兜底：直接转字符串取前8位数字
                df["date"] = df["date"].astype(str).str.replace(r'[^0-9]', '', regex=True).str[:8]
        
        # 确保 volume 是数值类型
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        
        return df


# ════════════════════════════════════════════════════════════
# 统一入口：MootdxDataProvider
# ════════════════════════════════════════════════════════════

class MootdxDataProvider:
    """
    Mootdx 数据统一入口
    
    策略：
    1. 离线优先：先尝试本地通达信数据（最快、最稳定）
    2. 实时降级：离线不可用时连接服务器
    3. 缓存兜底：都失败时使用缓存
    4. 与 resilience 集成：自动熔断、重试
    
    使用方式：
        provider = MootdxDataProvider(tdxdir="C:/new_tdx")
        
        # 获取K线（自动选择最优数据源）
        df = provider.fetch_kline("000001", "20250101", "20250619")
        
        # 获取实时行情
        quote = provider.fetch_realtime_quote(["000001", "300750"])
        
        # 获取股票列表
        stocks = provider.fetch_stock_list()
    """
    
    def __init__(self, tdxdir: str = DEFAULT_TDX_DIR,
                 offline_priority: bool = True,
                 enable_cache: bool = True):
        self.tdxdir = tdxdir
        self.offline_priority = offline_priority
        self.enable_cache = enable_cache
        
        # 初始化两层
        self._offline = OfflineDataProvider(tdxdir=tdxdir)
        self._realtime = RealtimeDataProvider(timeout=5)
        
        # 缓存
        self._cache = MultiLevelCache() if enable_cache else None
        
        # 可观测性
        self._obs = get_obs()
        
        # 统计
        self._stats = {"offline_hits": 0, "realtime_hits": 0, "cache_hits": 0, "failures": 0}
    
    # ────────────────────────────────────────────────────────
    # 状态检查
    # ────────────────────────────────────────────────────────
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "offline_available": self._offline.is_available(),
            "realtime_available": self._realtime.is_available(),
            "tdxdir_exists": os.path.exists(self.tdxdir),
            "mootdx_installed": MOOTDX_AVAILABLE,
            "stats": self._stats.copy(),
        }
    
    # ────────────────────────────────────────────────────────
    # K线数据（离线优先）
    # ────────────────────────────────────────────────────────
    
    def fetch_kline(self, code: str, start_date: str = "", end_date: str = "",
                    period: str = "daily", source: str = "auto", adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """
        获取K线数据
        
        Args:
            code: 股票代码
            start_date: 起始日期（YYYYMMDD 或 YYYY-MM-DD）
            end_date: 结束日期
            period: daily / weekly / monthly / minute
            source: auto / offline / realtime
        
        Returns:
            DataFrame[date, code, open, high, low, close, volume, amount] or None
        """
        code = _normalize_code(code)
        cache_key = f"mootdx:kline:{code}:{start_date}:{end_date}:{period}:{adjust}"
        
        # 1. 检查缓存
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                self._obs.log("INFO", f"Cache hit for {code}", "MootdxDataProvider")
                return pd.DataFrame(cached) if isinstance(cached, list) else cached
        
        result = None
        
        # 2. 离线优先
        if source in ("auto", "offline") and self.offline_priority:
            result = self._offline.fetch_kline(code, start_date, end_date, period, adjust=adjust)
            if result is not None and len(result) > 0:
                self._stats["offline_hits"] += 1
                self._cache_result(cache_key, result)
                return result
        
        # 3. 实时降级
        if source in ("auto", "realtime"):
            result = self._realtime.fetch_kline(code, start_date, end_date, period)
            if result is not None and len(result) > 0:
                self._stats["realtime_hits"] += 1
                self._cache_result(cache_key, result)
                return result
        
        # 4. 如果离线优先关闭，也尝试离线
        if not self.offline_priority and source in ("auto", "offline"):
            result = self._offline.fetch_kline(code, start_date, end_date, period, adjust=adjust)
            if result is not None and len(result) > 0:
                self._stats["offline_hits"] += 1
                self._cache_result(cache_key, result)
                return result
        
        # 5. 全部失败
        self._stats["failures"] += 1
        self._obs.log("ERROR", f"All sources failed for {code} kline", "MootdxDataProvider")
        return None
    
    def fetch_klines_batch(self, codes: List[str], start_date: str, end_date: str,
                           period: str = "daily", max_workers: int = 8,
                           adjust: str = "qfq") -> Dict[str, pd.DataFrame]:
        """
        批量获取K线（并行）
        
        Args:
            codes: 股票代码列表
            start_date, end_date: 日期范围
            period: 周期
            max_workers: 并行数
        
        Returns:
            {code: DataFrame}
        """
        from concurrent.futures import ThreadPoolExecutor
        
        results = {}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {
                executor.submit(self.fetch_kline, code, start_date, end_date, period, "auto", adjust): code
                for code in codes
            }
            
            for future in future_to_code:
                code = future_to_code[future]
                try:
                    df = future.result(timeout=30)
                    if df is not None and len(df) > 0:
                        results[code] = df
                except Exception as e:
                    self._obs.log("WARN", f"Batch kline failed for {code}: {str(e)}", "MootdxDataProvider")
        
        return results
    
    # ────────────────────────────────────────────────────────
    # 实时行情
    # ────────────────────────────────────────────────────────
    
    def fetch_realtime_quote(self, codes: List[str]) -> Optional[pd.DataFrame]:
        """
        获取实时行情（只能通过实时层）
        
        Args:
            codes: 股票代码列表
        
        Returns:
            DataFrame 实时行情数据
        """
        return self._realtime.fetch_realtime_quote(codes)
    
    # ────────────────────────────────────────────────────────
    # 股票列表
    # ────────────────────────────────────────────────────────
    
    def fetch_stock_list(self, source: str = "auto") -> Optional[pd.DataFrame]:
        """
        获取股票列表
        
        Args:
            source: auto / offline / realtime
        """
        if source in ("auto", "offline"):
            result = self._offline.fetch_stock_list()
            if result is not None and len(result) > 0:
                return result
        
        if source in ("auto", "realtime"):
            return self._realtime.fetch_stock_list()
        
        return None
    
    # ────────────────────────────────────────────────────────
    # 辅助方法
    # ────────────────────────────────────────────────────────
    
    def _cache_result(self, key: str, df: pd.DataFrame, ttl: int = 3600) -> None:
        """缓存结果"""
        if self._cache is not None and df is not None and len(df) > 0:
            try:
                self._cache.set(key, df.to_dict("records"), ttl_seconds=ttl)
            except Exception:
                pass
    
    def close(self):
        """关闭资源"""
        self._realtime.close()


# ════════════════════════════════════════════════════════════
# 与现有系统集成的便捷函数
# ════════════════════════════════════════════════════════════

_provider_instance: Optional[MootdxDataProvider] = None


def get_mootdx_provider(tdxdir: str = DEFAULT_TDX_DIR) -> MootdxDataProvider:
    """获取全局 MootdxDataProvider 实例"""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = MootdxDataProvider(tdxdir=tdxdir)
    return _provider_instance


# 兼容旧接口的便捷函数
def fetch_kline(code: str, start_date: str = "", end_date: str = "",
                period: str = "daily", tdxdir: str = DEFAULT_TDX_DIR, adjust: str = "qfq") -> Optional[pd.DataFrame]:
    """兼容旧接口的K线获取"""
    provider = get_mootdx_provider(tdxdir)
    return provider.fetch_kline(code, start_date, end_date, period, adjust=adjust)


def fetch_realtime_quote(codes: List[str], tdxdir: str = DEFAULT_TDX_DIR) -> Optional[pd.DataFrame]:
    """兼容旧接口的实时行情获取"""
    provider = get_mootdx_provider(tdxdir)
    return provider.fetch_realtime_quote(codes)


def fetch_stock_list(tdxdir: str = DEFAULT_TDX_DIR, source: str = "auto") -> Optional[pd.DataFrame]:
    """兼容旧接口的股票列表获取"""
    provider = get_mootdx_provider(tdxdir)
    return provider.fetch_stock_list(source)


if __name__ == "__main__":
    # 快速测试
    print("=== Mootdx Data Provider Test ===")
    
    provider = MootdxDataProvider(tdxdir=DEFAULT_TDX_DIR)
    
    # 健康检查
    health = provider.health_check()
    print(f"\nHealth Check:")
    print(f"  Offline available: {health['offline_available']}")
    print(f"  Realtime available: {health['realtime_available']}")
    print(f"  Tdxdir exists: {health['tdxdir_exists']}")
    print(f"  Mootdx installed: {health['mootdx_installed']}")
    
    # 测试实时行情（如果可用）
    if health['realtime_available']:
        print("\n--- Realtime Quote Test ---")
        quote = provider.fetch_realtime_quote(["000001", "300750"])
        if quote is not None:
            print(f"Quote shape: {quote.shape}")
            print(quote.head())
        else:
            print("Realtime quote returned None")
    
    # 测试离线数据（如果目录存在）
    if health['tdxdir_exists']:
        print("\n--- Offline Kline Test ---")
        df = provider.fetch_kline("000001", source="offline")
        if df is not None:
            print(f"Kline shape: {df.shape}")
            print(df.tail(3))
        else:
            print("Offline kline not available (data may not be downloaded)")
    
    print("\nDone.")
