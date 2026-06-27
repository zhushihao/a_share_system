"""
SectorCalculationHarness - 板块计算模块

Inputs:  stock_data (Dict[str, DataFrame]), date (str)
Outputs: sector_results, sector_ranking, style_rotation

职责：
1. 计算板块动量排名
2. 判定板块生命周期（萌芽/发酵/高潮/衰退）
3. 大小盘风格轮动
"""

import sys
import pandas as pd
from typing import Dict, Any, List

sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")

from core.harness import Harness, HarnessConfig, Context
from data.sector_calculation import calculate_sector_ranking, calculate_style_rotation, SectorResult


class SectorCalculationHarness(Harness):
    """板块计算 Harness"""
    
    INPUTS = ["stock_data", "date"]
    OUTPUTS = ["sector_results", "sector_ranking", "style_rotation"]
    
    def __init__(self, config: HarnessConfig):
        super().__init__(config)
        self.top_n = config.params.get("top_n", 30)
        self.max_sectors = config.params.get("max_sectors", 15)
        self.max_components = config.params.get("max_components", 10)
    
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        date_str = inputs.get("date", "")
        stock_data = inputs.get("stock_data", {})
        
        if not date_str:
            return {"sector_results": [], "sector_ranking": [], "style_rotation": {}}
        
        ctx.log("INFO", f"Calculating sector rankings for {date_str} (max_sectors={self.max_sectors}, max_components={self.max_components})", self.name)
        
        try:
            sector_results = calculate_sector_ranking(
                date_str, top_n=self.top_n,
                max_sectors=self.max_sectors,
                stock_data_cache=stock_data,
                max_components=self.max_components
            )
        except Exception as e:
            ctx.log("WARN", f"Sector ranking failed: {e}, using fallback", self.name)
            sector_results = []
        
        # Fallback: 如果板块K线接口不可用，使用 sector_list 的基础数据生成简化排名
        if not sector_results:
            ctx.log("INFO", "Sector ranking empty, using fallback from sector_list", self.name)
            try:
                from utils.data_fetcher import fetch_sector_list
                sector_list = fetch_sector_list()
                if len(sector_list) > 0:
                    sector_results = []
                    for _, row in sector_list.iterrows():
                        return_20d = row.get("pct_20d", 0)
                        score = min(max(return_20d * 100, -20), 20) * 2.5 + 50
                        lifecycle = "萌芽期"
                        if score >= 60:
                            lifecycle = "发酵期"
                        elif score >= 70:
                            lifecycle = "高潮期"
                        elif score < 30:
                            lifecycle = "衰退期"
                        sector_results.append(SectorResult(
                            sector_code=row.get("sector_code", ""),
                            sector_name=row.get("sector_name", ""),
                            score=score,
                            rank=0,
                            lifecycle=lifecycle,
                            style="题材概念",
                            score_20d_return=score,
                            score_new_high_ratio=0,
                            score_volume_change=0,
                            score_limit_up_quality=0,
                            score_continuity=0,
                            score_institutional=0,
                            return_20d=return_20d,
                            new_high_ratio=0,
                            volume_change=0,
                            limit_up_info={},
                            continuity_days=0,
                            institutional_ratio=0,
                            new_high_20d_count=0,
                            new_high_60d_count=0,
                            rule_3plus2=False,
                            recommendation="观察池" if score < 60 else "趋势池候选",
                        ))
                    sector_results.sort(key=lambda x: x.score, reverse=True)
                    for i, r in enumerate(sector_results):
                        r.rank = i + 1
                    sector_results = sector_results[:self.top_n]
            except Exception as e2:
                ctx.log("WARN", f"Fallback sector ranking also failed: {e2}", self.name)
        
        # 风格轮动
        index_data = {}
        for code, df in stock_data.items():
            if code == "000300":
                index_data["沪深300"] = df
            elif code == "000852":
                index_data["中证1000"] = df
            elif code == "000905":
                index_data["中证500"] = df
        
        style_rotation = calculate_style_rotation(index_data)
        
        ctx.log("INFO", f"Sector results: {len(sector_results)}, style={style_rotation.get('style')}", self.name)
        
        return {
            "sector_results": sector_results,
            "sector_ranking": sector_results,  # 别名
            "style_rotation": style_rotation,
        }
