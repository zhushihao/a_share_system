"""
DataFetcherHarness - 数据获取模块

Inputs:  date (str), mode (str via config.params)
Outputs: stock_data.{code}, stock_info.{code}, market_indices, market_regime

职责：
1. 加载个股历史K线
2. 加载市场指数（沪深300、中证1000等）
3. 判定市场状态（强趋势/结构性趋势/震荡/风险市）
"""

import sys
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional

sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")

from core.harness import Harness, HarnessConfig, Context, RunMode
from utils.data_fetcher import fetch_daily_kline, fetch_sector_list, fetch_sector_kline, fetch_northbound_money
from utils.config_loader import get_config


class DataFetcherHarness(Harness):
    """数据获取 Harness"""
    
    INPUTS = ["date"]
    OUTPUTS = [
        "stock_data",
        "market_indices",
        "market_regime",
        "raw_data_loaded",
    ]
    
    def __init__(self, config: HarnessConfig):
        super().__init__(config)
        self.codes_to_scan: List[str] = []
        self.days_back: int = 120
    
    def init(self, ctx: Context) -> None:
        # 加载配置
        self.codes_to_scan = self.config.params.get("codes", self._default_codes())
        self.days_back = self.config.params.get("days_back", 120)
    
    def _default_codes(self) -> List[str]:
        """默认扫描股票列表"""
        return [
            "000001", "300750", "600519", "000858", "002594", "601318",
            "000002", "000333", "600036", "601888", "600276", "300760",
        ]
    
    def _load_stock_data(self, date_str: str) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any], int]:
        """加载个股历史数据（带本地缓存）
        返回: (stock_data, stock_info, cache_hit_count)"""
        end_date = date_str
        start_date = (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=self.days_back)).strftime("%Y%m%d")
        
        stock_data = {}
        stock_info = {}
        cache_hit = 0
        
        for code in self.codes_to_scan:
            try:
                # 检查本地缓存
                cache_key = f"{code}_{start_date}_{end_date}"
                cached = self._check_cache(cache_key)
                if cached is not None:
                    stock_data[code] = cached
                    cache_hit += 1
                    continue
                
                df = fetch_daily_kline(code, start_date, end_date)
                if len(df) > 0:
                    stock_data[code] = df
                    stock_info[code] = {"name": code}
            except Exception as e:
                pass
        
        return stock_data, stock_info, cache_hit
    
    def _check_cache(self, cache_key: str) -> Optional[pd.DataFrame]:
        """检查本地缓存（暂不实现，预留接口）"""
        return None
    
    def _load_market_indices(self, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """加载市场指数（风格轮动需要沪深300 + 中证1000）"""
        indices = {}
        # 沪深300 + 中证1000 + 上证50（用于风格轮动判定）
        for code in ["000300", "000852", "000016"]:
            try:
                df = fetch_daily_kline(code, start_date, end_date)
                if len(df) > 0:
                    indices[code] = df
            except:
                pass
        return indices
    
    def _detect_market_regime(self, indices: Dict[str, pd.DataFrame]) -> str:
        """判定市场状态（基于沪深300的20日均线趋势）"""
        if "000300" not in indices or len(indices["000300"]) < 20:
            return "未知"
        
        hs300 = indices["000300"]
        ma20 = hs300["close"].rolling(20).mean()
        ma20_slope = (ma20.iloc[-1] - ma20.iloc[-5]) / ma20.iloc[-5] if ma20.iloc[-5] != 0 else 0
        
        # 近5日上涨比例
        recent = hs300.iloc[-5:]
        up_ratio = (recent["close"].diff() > 0).sum() / 5
        
        if ma20_slope > 0.02 and up_ratio >= 0.6:
            return "强趋势"
        elif ma20_slope > -0.01 and 0.4 <= up_ratio <= 0.6:
            return "结构性趋势"
        elif up_ratio < 0.35:
            return "风险市"
        else:
            return "震荡"
    
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        date_str = inputs.get("date", "")
        if not date_str:
            return {"raw_data_loaded": False}
        
        ctx.log("INFO", f"Loading stock data for {len(self.codes_to_scan)} codes", self.name)
        
        stock_data, stock_info, cache_hit = self._load_stock_data(date_str)
        
        start_date = (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=self.days_back)).strftime("%Y%m%d")
        indices = self._load_market_indices(start_date, date_str)
        regime = self._detect_market_regime(indices)
        
        ctx.log("INFO", f"Loaded {len(stock_data)} stocks (cache_hit={cache_hit}), regime={regime}", self.name)
        
        return {
            "stock_data": stock_data,
            "market_indices": indices,
            "market_regime": regime,
            "raw_data_loaded": len(stock_data) > 0,
        }
