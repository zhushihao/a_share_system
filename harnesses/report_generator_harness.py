"""
ReportGeneratorHarness - 报告生成模块

Inputs:  traffic_light.*, sector_results, market_regime, date, all_patterns
Outputs: reports.post_market, reports.pre_market, reports.deviation, reports.position_csv

职责：
1. 生成盘后策略报告（Markdown）
2. 生成持仓CSV（附录A格式）
3. 生成执行偏差报告
"""

import sys
import os
from typing import Dict, Any, List

sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")

from core.harness import Harness, HarnessConfig, Context, RunMode
from strategy.report_generator import ReportGenerator


class ReportGeneratorHarness(Harness):
    """报告生成 Harness"""
    
    INPUTS = [
        "traffic_light.trend_pool",
        "traffic_light.watch_pool",
        "traffic_light.risk_pool",
        "traffic_light.position_signals",
        "sector_results",
        "market_regime",
        "date",
        "all_patterns",
    ]
    OUTPUTS = ["reports.post_market", "reports.position_csv"]
    
    def __init__(self, config: HarnessConfig):
        super().__init__(config)
        self.gen = ReportGenerator()
    
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        date_str = inputs.get("date", "")
        market_regime = inputs.get("market_regime", "结构性趋势")
        sector_results = inputs.get("sector_results", [])
        trend_pool = inputs.get("traffic_light.trend_pool", [])
        watch_pool = inputs.get("traffic_light.watch_pool", [])
        risk_pool = inputs.get("traffic_light.risk_pool", [])
        position_signals = inputs.get("traffic_light.position_signals", [])
        
        if not date_str:
            return {}
        
        ctx.log("INFO", f"Generating reports for {date_str}", self.name)
        
        outputs = {}
        
        # 盘后报告
        if ctx.mode == RunMode.POST_MARKET:
            try:
                total_position = 0.50 if market_regime == "结构性趋势" else 0.80
                
                report_path = self.gen.generate_post_market_report(
                    date=date_str,
                    market_regime=market_regime,
                    total_position_limit=total_position,
                    actual_position=0.0,
                    sector_results=sector_results,
                    trend_pool=trend_pool,
                    watch_pool=watch_pool[:20],
                    risk_pool=risk_pool[:20],
                    position_signals=position_signals,
                    invalidation_signals=[
                        "最高连板股跌停开或低开>-5%",
                        "昨日龙虎榜买入席位今日全部卖出",
                        "候选股集合竞价成交量<昨日50%",
                        "北向净流出>50亿",
                        "炸板率>60%",
                    ],
                )
                outputs["reports.post_market"] = report_path
                ctx.log("INFO", f"Post-market report: {report_path}", self.name)
            except Exception as e:
                ctx.log("ERROR", f"Post-market report failed: {e}", self.name)
        
        # 持仓CSV
        try:
            positions = []
            for t in trend_pool:
                positions.append({
                    "code": t.code,
                    "name": t.name,
                    "sector": "",
                    "pattern": "",
                    "entry_date": "",
                    "entry_price": t.entry_price,
                    "stop_loss": t.stop_loss,
                    "current_price": t.entry_price,
                    "pnl_pct": 0.0,
                    "position_pct": t.position_size,
                    "signal": t.signal,
                    "target_1": t.target_1,
                    "target_2": t.target_2,
                    "next_action": t.action,
                    "notes": "; ".join(t.reasons),
                })
            
            csv_path = self.gen.generate_position_csv(
                date=date_str,
                market_regime=market_regime,
                total_position_limit=0.50,
                actual_position=0.0,
                positions=positions,
            )
            outputs["reports.position_csv"] = csv_path
            ctx.log("INFO", f"Position CSV: {csv_path}", self.name)
        except Exception as e:
            ctx.log("ERROR", f"Position CSV failed: {e}", self.name)
        
        return outputs
