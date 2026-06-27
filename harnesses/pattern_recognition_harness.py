"""
PatternRecognitionHarness - 型态识别模块

Inputs:  stock_data (Dict[str, DataFrame])
Outputs: patterns (Dict[str, List[Pattern]]), all_patterns (List[Dict])

职责：
1. 对每只股票扫描蔡森型态
2. 去噪过滤（置信度≥0.70，Top10）
3. 输出结构化的型态列表
"""

import sys
import pandas as pd
from typing import Dict, Any, List

sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")

from core.harness import Harness, HarnessConfig, Context
from data.pattern_recognition import scan_patterns, Pattern


class PatternRecognitionHarness(Harness):
    """型态识别 Harness"""
    
    INPUTS = ["stock_data"]
    OUTPUTS = ["patterns", "all_patterns"]
    
    def __init__(self, config: HarnessConfig):
        super().__init__(config)
        self.min_history = config.params.get("min_history", 80)
    
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        stock_data = inputs.get("stock_data", {})
        if not stock_data:
            return {"patterns": {}, "all_patterns": []}
        
        ctx.log("INFO", f"Scanning patterns for {len(stock_data)} stocks", self.name)
        
        patterns_map = {}
        all_patterns = []
        
        for code, df in stock_data.items():
            try:
                patterns = scan_patterns(df, code, code, min_history=self.min_history)
                if patterns:
                    patterns_map[code] = patterns
                    for p in patterns:
                        all_patterns.append(p.to_dict())
            except Exception as e:
                ctx.log("WARN", f"Pattern scan failed for {code}: {e}", self.name)
        
        ctx.log("INFO", f"Found patterns in {len(patterns_map)} stocks, total={len(all_patterns)}", self.name)
        
        return {
            "patterns": patterns_map,
            "all_patterns": all_patterns,
        }
