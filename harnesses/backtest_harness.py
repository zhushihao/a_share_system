"""
BacktestHarness - 回测模块

Inputs:  traffic_light.all, stock_data, date, market_regime
Outputs: backtest.results, backtest.summary

职责：
1. 使用交通灯信号驱动历史回测
2. 计算收益率、夏普、最大回撤、胜率、盈亏比
3. 对比 Buy&Hold 基准
"""

import sys
import pandas as pd
from typing import Dict, Any, List

sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")

from core.harness import Harness, HarnessConfig, Context
from strategy.backtest import BacktestEngine, _convert_traffic_light_to_signals


class BacktestHarness(Harness):
    """回测 Harness"""
    
    INPUTS = ["traffic_light.all", "stock_data", "date", "market_regime"]
    OUTPUTS = ["backtest.results", "backtest.summary"]
    
    def __init__(self, config: HarnessConfig):
        super().__init__(config)
        self.initial_capital = config.params.get("initial_capital", 1000000)
    
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        traffic_light = inputs.get("traffic_light.all", {})
        stock_data = inputs.get("stock_data", {})
        date_str = inputs.get("date", "")
        
        if not traffic_light or not stock_data:
            return {
                "backtest.results": {},
                "backtest.summary": {"error": "Missing traffic_light or stock_data"},
            }
        
        ctx.log("INFO", f"Running backtest for {date_str}", self.name)
        
        # 提取日期列表
        all_dates = set()
        for code, df in stock_data.items():
            if "date" in df.columns:
                all_dates.update(df["date"].astype(str).tolist())
        dates = sorted(list(all_dates))
        
        if len(dates) < 2:
            return {
                "backtest.results": {},
                "backtest.summary": {"error": "Insufficient dates"},
            }
        
        # 生成每日信号
        daily_signals = {}
        for day_tl in traffic_light.values() if isinstance(traffic_light, dict) else []:
            if isinstance(day_tl, list):
                signals = _convert_traffic_light_to_signals(day_tl)
                # 这里简化：假设 traffic_light 是单日的
                for code, sig in signals.items():
                    daily_signals.setdefault(code, {})[code] = sig
        
        # 简化回测：使用最后一个日期的收盘价作为基准
        engine = BacktestEngine(initial_capital=self.initial_capital)
        
        # 由于 traffic_light 是单日的（不是历史序列），这里做简化模拟
        ctx.log("WARN", "BacktestHarness: simplified single-day backtest (historical traffic light not yet implemented)", self.name)
        
        # 实际回测需要每日 traffic_light 序列，这里预留接口
        return {
            "backtest.results": {},
            "backtest.summary": {
                "status": "placeholder",
                "note": "Historical backtest requires daily traffic_light sequence",
            },
        }
