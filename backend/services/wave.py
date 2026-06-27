# -*- coding: utf-8 -*-
"""
Wave Structure Engine - 波浪结构引擎

基于 Elliott Wave 理论识别价格波浪结构。

实现：
  - 基于高低点序列识别 5-3 波浪结构（5 浪推动 + 3 浪回调）
  - 自动标注浪型序号（1, 2, 3, 4, 5, A, B, C）

注意：波浪识别是概率性的，返回置信度评估。数据不足时返回空列表。
"""

from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np


# ───────────────────────────────────────────────
# 辅助：极值点检测
# ───────────────────────────────────────────────

def _find_pivots(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    标记局部极值点（高点和低点交替）。

    Args:
        df: OHLCV DataFrame
        window: 半窗口大小

    Returns:
        DataFrame 附加 'pivot_type' 列 ('high' | 'low')
    """
    df = df.copy().reset_index(drop=True)
    
    # 局部高点
    rolling_max = df["high"].rolling(window=2 * window + 1, center=True, min_periods=1).max()
    is_peak = (df["high"] == rolling_max) & (df["high"] > df["high"].shift(1)) & (df["high"] > df["high"].shift(-1))
    
    # 局部低点
    rolling_min = df["low"].rolling(window=2 * window + 1, center=True, min_periods=1).min()
    is_trough = (df["low"] == rolling_min) & (df["low"] < df["low"].shift(1)) & (df["low"] < df["low"].shift(-1))
    
    df["pivot_type"] = None
    df.loc[is_peak, "pivot_type"] = "high"
    df.loc[is_trough, "pivot_type"] = "low"
    
    return df


def _extract_pivot_sequence(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    提取交替的极值点序列（高-低-高-低...）。

    Returns:
        极值点列表，每个元素含 index, date, price, type
    """
    df = _find_pivots(df, window=5)
    pivots = df[df["pivot_type"].notna()].copy()
    
    if len(pivots) < 3:
        return []
    
    sequence: List[Dict[str, Any]] = []
    last_type = None
    
    for idx, row in pivots.iterrows():
        ptype = row["pivot_type"]
        price = row["high"] if ptype == "high" else row["low"]
        
        # 确保高低交替
        if last_type == ptype:
            # 同类型只保留更极端的
            if sequence:
                if ptype == "high" and price > sequence[-1]["price"]:
                    sequence[-1] = {
                        "index": int(idx),
                        "date": str(row["date"]),
                        "price": round(float(price), 3),
                        "type": ptype,
                    }
                elif ptype == "low" and price < sequence[-1]["price"]:
                    sequence[-1] = {
                        "index": int(idx),
                        "date": str(row["date"]),
                        "price": round(float(price), 3),
                        "type": ptype,
                    }
            continue
        
        sequence.append({
            "index": int(idx),
            "date": str(row["date"]),
            "price": round(float(price), 3),
            "type": ptype,
        })
        last_type = ptype
    
    return sequence


# ───────────────────────────────────────────────
# 波浪结构检测
# ───────────────────────────────────────────────

def detect_wave_structure(
    df: pd.DataFrame, window: int = 120
) -> List[Dict[str, Any]]:
    """
    基于高低点序列识别 5-3 波浪结构。

    识别规则（5 浪推动）：
      - 浪 1：上升，从低点开始
      - 浪 2：回调，不跌破浪 1 起点
      - 浪 3：最长上升浪（通常是 1.618x 浪 1）
      - 浪 4：回调，不跌破浪 1 高点
      - 浪 5：最终上升，通常短于浪 3
      - ABC 修正：3 浪回调

    Args:
        df: OHLCV DataFrame
        window: 扫描窗口，默认 120

    Returns:
        波浪结构列表，每个元素含 waves, confidence, start_date, end_date
    """
    if df is None or len(df) < 30:
        return []
    
    df = df.copy().tail(window).reset_index(drop=True)
    sequence = _extract_pivot_sequence(df)
    
    if len(sequence) < 8:
        return []
    
    results: List[Dict[str, Any]] = []
    
    # 滑动窗口尝试匹配 5-3 结构
    for i in range(len(sequence) - 7):
        candidate = sequence[i:i + 8]
        
        # 检查类型交替
        if not all(
            candidate[j]["type"] != candidate[j + 1]["type"]
            for j in range(len(candidate) - 1)
        ):
            continue
        
        # 确保以低点开始（上升推动浪）
        if candidate[0]["type"] != "low":
            continue
        
        # 波浪结构验证
        p0 = candidate[0]["price"]  # 浪 1 起点
        p1 = candidate[1]["price"]  # 浪 1 高点
        p2 = candidate[2]["price"]  # 浪 2 低点
        p3 = candidate[3]["price"]  # 浪 3 高点
        p4 = candidate[4]["price"]  # 浪 4 低点
        p5 = candidate[5]["price"]  # 浪 5 高点
        pA = candidate[6]["price"]  # A 浪低点
        pB = candidate[7]["price"]  # B 浪高点
        
        # 基本约束
        if not (p1 > p0 and p3 > p1 and p5 > p3):
            continue
        if not (p2 < p1 and p2 > p0):
            continue
        if not (p4 < p3 and p4 > p1):
            continue
        if not (pA < p5 and pB <= p5):
            continue
        
        # 浪 3 通常最长
        len1 = p1 - p0
        len3 = p3 - p2
        len5 = p5 - p4
        if len3 < len1 or len3 < len5:
            continue
        
        # 浪 5 不最短（通常）
        if len5 < len1 * 0.3:
            continue
        
        # 置信度评估
        confidence = 0.6
        
        # 浪 3 长度 ~ 1.618x 浪 1
        if len1 > 0 and abs(len3 / len1 - 1.618) < 0.5:
            confidence += 0.15
        
        # 浪 2 和浪 4 交替（浪 2 深、浪 4 浅 或反之）
        retrace2 = (p1 - p2) / (p1 - p0 + 1e-6)
        retrace4 = (p3 - p4) / (p3 - p2 + 1e-6)
        if abs(retrace2 - retrace4) > 0.2:
            confidence += 0.1
        
        confidence = round(min(1.0, confidence), 3)
        
        waves = [
            {"label": "1", "start_date": candidate[0]["date"], "end_date": candidate[1]["date"],
             "start_price": p0, "end_price": p1, "type": "impulse"},
            {"label": "2", "start_date": candidate[1]["date"], "end_date": candidate[2]["date"],
             "start_price": p1, "end_price": p2, "type": "corrective"},
            {"label": "3", "start_date": candidate[2]["date"], "end_date": candidate[3]["date"],
             "start_price": p2, "end_price": p3, "type": "impulse"},
            {"label": "4", "start_date": candidate[3]["date"], "end_date": candidate[4]["date"],
             "start_price": p3, "end_price": p4, "type": "corrective"},
            {"label": "5", "start_date": candidate[4]["date"], "end_date": candidate[5]["date"],
             "start_price": p4, "end_price": p5, "type": "impulse"},
            {"label": "A", "start_date": candidate[5]["date"], "end_date": candidate[6]["date"],
             "start_price": p5, "end_price": pA, "type": "corrective"},
            {"label": "B", "start_date": candidate[6]["date"], "end_date": candidate[7]["date"],
             "start_price": pA, "end_price": pB, "type": "corrective"},
        ]
        
        # 如果有第 9 个点，包含 C 浪
        if len(candidate) > 8 and candidate[8]["type"] == "low":
            pC = candidate[8]["price"]
            waves.append({
                "label": "C", "start_date": candidate[7]["date"], "end_date": candidate[8]["date"],
                "start_price": pB, "end_price": pC, "type": "corrective",
            })
        
        results.append({
            "type": "elliott_wave_5_3",
            "start_date": candidate[0]["date"],
            "end_date": candidate[-1]["date"],
            "confidence": confidence,
            "waves": waves,
            "description": (
                f"5-3波浪结构：浪1 {p1:.2f} → 浪3 {p3:.2f} → 浪5 {p5:.2f}，"
                f"当前处于 {waves[-1]['label']} 浪"
            ),
        })
    
    # 去重：按起始日期保留置信度最高的
    seen = {}
    for r in results:
        key = r["start_date"]
        if key not in seen or r["confidence"] > seen[key]["confidence"]:
            seen[key] = r
    
    return sorted(seen.values(), key=lambda x: x["confidence"], reverse=True)
