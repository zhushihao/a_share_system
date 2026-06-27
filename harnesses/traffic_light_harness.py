"""
TrafficLightHarness - 交通灯系统

Inputs:  stock_data, patterns, sector_results, market_regime, date
Outputs: traffic_light.all, traffic_light.trend_pool, traffic_light.watch_pool, traffic_light.risk_pool, traffic_light.position_signals

职责：
1. 候选池分类（趋势池/观察池/风险池）
2. 持仓信号灯判定（绿灯/黄灯/红灯）
3. 生成可操作的交易信号
"""

import sys
import pandas as pd
from typing import Dict, Any, List

sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")

from core.harness import Harness, HarnessConfig, Context
from data.sector_calculation import SectorResult
from strategy.traffic_light import run_traffic_light_system, TrafficLightResult


class TrafficLightHarness(Harness):
    """交通灯系统 Harness"""
    
    INPUTS = ["stock_data", "patterns", "sector_results", "market_regime", "date"]
    OUTPUTS = [
        "traffic_light.all",
        "traffic_light.trend_pool",
        "traffic_light.watch_pool",
        "traffic_light.risk_pool",
        "traffic_light.position_signals",
    ]
    
    def __init__(self, config: HarnessConfig):
        super().__init__(config)
    
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        stock_data = inputs.get("stock_data", {})
        patterns = inputs.get("patterns", {})
        sector_results = inputs.get("sector_results", [])
        market_regime = inputs.get("market_regime", "结构性趋势")
        
        if not stock_data:
            return {
                "traffic_light.all": {},
                "traffic_light.trend_pool": [],
                "traffic_light.watch_pool": [],
                "traffic_light.risk_pool": [],
                "traffic_light.position_signals": [],
            }
        
        ctx.log("INFO", f"Running traffic light for {len(stock_data)} stocks, regime={market_regime}", self.name)
        
        try:
            traffic_results = run_traffic_light_system(
                stock_data, patterns, sector_results, market_regime
            )
        except Exception as e:
            ctx.log("ERROR", f"Traffic light failed: {e}", self.name)
            return {
                "traffic_light.all": {},
                "traffic_light.trend_pool": [],
                "traffic_light.watch_pool": [],
                "traffic_light.risk_pool": [],
                "traffic_light.position_signals": [],
            }
        
        trend_pool = traffic_results.get("趋势池", [])
        watch_pool = traffic_results.get("观察池", [])
        risk_pool = traffic_results.get("风险池", [])
        position_signals = traffic_results.get("持仓", [])
        
        ctx.log("INFO", f"Trend={len(trend_pool)}, Watch={len(watch_pool)}, Risk={len(risk_pool)}, Pos={len(position_signals)}", self.name)
        
        return {
            "traffic_light.all": traffic_results,
            "traffic_light.trend_pool": trend_pool,
            "traffic_light.watch_pool": watch_pool,
            "traffic_light.risk_pool": risk_pool,
            "traffic_light.position_signals": position_signals,
        }
