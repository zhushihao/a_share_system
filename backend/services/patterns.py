# -*- coding: utf-8 -*-
"""
Pattern Recognition Engine - 形态识别引擎

基于 OHLCV 数据识别经典价格形态。

支持的形态：
  - 双顶 / 双底
  - 头肩顶 / 头肩底
  - 三角形（收敛 / 上升 / 下降）
  - V 型反转
  - 斐波那契回调位

注意：所有检测函数在数据不足或无法识别时返回空列表。
"""

from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np


# ───────────────────────────────────────────────
# 辅助工具
# ───────────────────────────────────────────────

def _find_local_extrema(
    df: pd.DataFrame, window: int = 5, mode: str = "high"
) -> pd.DataFrame:
    """
    使用滚动窗口寻找局部极值点。

    Args:
        df: 含 'high', 'low', 'close' 列的 DataFrame
        window: 半窗口大小（极值点前后各 window 根 K 线）
        mode: 'high' 找局部高点, 'low' 找局部低点

    Returns:
        原 DataFrame 附加 'is_peak' 或 'is_trough' 布尔列
    """
    df = df.copy().reset_index(drop=True)
    col = "high" if mode == "high" else "low"
    
    # 滚动窗口最大值/最小值
    if mode == "high":
        rolling_max = df[col].rolling(window=2 * window + 1, center=True, min_periods=1).max()
        df["is_peak"] = (df[col] == rolling_max) & (df[col] > df[col].shift(1)) & (df[col] > df[col].shift(-1))
    else:
        rolling_min = df[col].rolling(window=2 * window + 1, center=True, min_periods=1).min()
        df["is_trough"] = (df[col] == rolling_min) & (df[col] < df[col].shift(1)) & (df[col] < df[col].shift(-1))
    
    return df


def _find_pivots(
    df: pd.DataFrame, window: int = 5
) -> tuple:
    """
    同时找出局部高点和低点序列。

    Returns:
        (peaks_df, troughs_df) — 两个 DataFrame，仅包含极值行
    """
    df = _find_local_extrema(df, window=window, mode="high")
    df = _find_local_extrema(df, window=window, mode="low")
    
    peaks = df[df["is_peak"]].copy()
    troughs = df[df["is_trough"]].copy()
    
    return peaks, troughs


# ───────────────────────────────────────────────
# 1. 双顶
# ───────────────────────────────────────────────

def detect_double_top(
    df: pd.DataFrame, window: int = 60, tolerance: float = 0.03
) -> List[Dict[str, Any]]:
    """
    检测双顶形态。

    识别条件：
      - 两个相近的局部高点（价差在 tolerance 内）
      - 中间存在明显低点（谷底）
      - 谷底低于两个高点，且构成颈线
      - 第二个高点后确认跌破颈线

    Args:
        df: OHLCV DataFrame，必须含 'date', 'high', 'low', 'close' 列
        window: 扫描窗口（K 线数），默认 60
        tolerance: 两个高点价格容差（相对比例），默认 3%

    Returns:
        双顶形态列表，每个元素含 type, start_date, end_date, peak_dates, peak_prices,
        neck_line, confidence, target, description
    """
    if df is None or len(df) < window * 2 // 3:
        return []
    
    df = df.copy().tail(window).reset_index(drop=True)
    peaks, troughs = _find_pivots(df, window=5)
    
    if len(peaks) < 2 or len(troughs) < 1:
        return []
    
    results: List[Dict[str, Any]] = []
    
    for i in range(len(peaks) - 1):
        for j in range(i + 1, len(peaks)):
            p1 = peaks.iloc[i]
            p2 = peaks.iloc[j]
            
            # 两高点价差容忍
            price_avg = (p1["high"] + p2["high"]) / 2
            if abs(p1["high"] - p2["high"]) / price_avg > tolerance:
                continue
            
            # 中间低点
            mid_low = troughs[
                (troughs.index > p1.name) & (troughs.index < p2.name)
            ]
            if len(mid_low) == 0:
                continue
            
            neck = mid_low["low"].min()
            neck_idx = mid_low["low"].idxmin()
            
            # 谷底必须低于两个高点
            if neck >= min(p1["high"], p2["high"]):
                continue
            
            # 确认跌破颈线（第二个高点后有 close < neck_line）
            confirm = df.loc[p2.name:]
            if len(confirm) < 2:
                continue
            break_confirm = confirm.iloc[1:]
            break_confirm = break_confirm[break_confirm["close"] < neck]
            if len(break_confirm) == 0:
                continue
            
            # 目标价 = 颈线 - (高点 - 颈线)
            target = neck - (price_avg - neck)
            
            # 置信度：基于高度差和成交量
            height = price_avg - neck
            confidence = min(1.0, height / (price_avg * 0.1)) * 0.7
            if len(df) > 2 and "volume" in df.columns:
                vol_ratio = df.loc[p2.name, "volume"] / df.loc[p1.name, "volume"] if df.loc[p1.name, "volume"] > 0 else 1.0
                if vol_ratio < 1.0:
                    confidence += 0.15
            confidence = round(min(1.0, confidence), 3)
            
            results.append({
                "type": "double_top",
                "start_date": str(p1["date"]),
                "end_date": str(break_confirm.iloc[0]["date"]),
                "peak_dates": [str(p1["date"]), str(p2["date"])],
                "peak_prices": [round(float(p1["high"]), 3), round(float(p2["high"]), 3)],
                "neck_line": round(float(neck), 3),
                "confidence": confidence,
                "target": round(float(target), 3),
                "description": (
                    f"双顶形态：两个高点 {p1['high']:.2f}/{p2['high']:.2f}，"
                    f"颈线 {neck:.2f}，目标 {target:.2f}"
                ),
            })
    
    return results


# ───────────────────────────────────────────────
# 2. 双底
# ───────────────────────────────────────────────

def detect_double_bottom(
    df: pd.DataFrame, window: int = 60, tolerance: float = 0.03
) -> List[Dict[str, Any]]:
    """
    检测双底形态。

    识别条件：
      - 两个相近的局部低点（价差在 tolerance 内）
      - 中间存在明显高点（峰）
      - 峰高于两个低点，构成颈线
      - 第二个低点后确认突破颈线

    Args:
        df: OHLCV DataFrame
        window: 扫描窗口，默认 60
        tolerance: 两个低点价格容差，默认 3%

    Returns:
        双底形态列表
    """
    if df is None or len(df) < window * 2 // 3:
        return []
    
    df = df.copy().tail(window).reset_index(drop=True)
    peaks, troughs = _find_pivots(df, window=5)
    
    if len(troughs) < 2 or len(peaks) < 1:
        return []
    
    results: List[Dict[str, Any]] = []
    
    for i in range(len(troughs) - 1):
        for j in range(i + 1, len(troughs)):
            t1 = troughs.iloc[i]
            t2 = troughs.iloc[j]
            
            price_avg = (t1["low"] + t2["low"]) / 2
            if abs(t1["low"] - t2["low"]) / price_avg > tolerance:
                continue
            
            # 中间高点
            mid_high = peaks[
                (peaks.index > t1.name) & (peaks.index < t2.name)
            ]
            if len(mid_high) == 0:
                continue
            
            neck = mid_high["high"].max()
            
            if neck <= max(t1["low"], t2["low"]):
                continue
            
            # 确认突破颈线
            confirm = df.loc[t2.name:]
            if len(confirm) < 2:
                continue
            break_confirm = confirm.iloc[1:]
            break_confirm = break_confirm[break_confirm["close"] > neck]
            if len(break_confirm) == 0:
                continue
            
            target = neck + (neck - price_avg)
            
            height = neck - price_avg
            confidence = min(1.0, height / (price_avg * 0.1)) * 0.7
            if "volume" in df.columns:
                vol_ratio = df.loc[t2.name, "volume"] / df.loc[t1.name, "volume"] if df.loc[t1.name, "volume"] > 0 else 1.0
                if vol_ratio > 1.0:
                    confidence += 0.15
            confidence = round(min(1.0, confidence), 3)
            
            results.append({
                "type": "double_bottom",
                "start_date": str(t1["date"]),
                "end_date": str(break_confirm.iloc[0]["date"]),
                "trough_dates": [str(t1["date"]), str(t2["date"])],
                "trough_prices": [round(float(t1["low"]), 3), round(float(t2["low"]), 3)],
                "neck_line": round(float(neck), 3),
                "confidence": confidence,
                "target": round(float(target), 3),
                "description": (
                    f"双底形态：两个低点 {t1['low']:.2f}/{t2['low']:.2f}，"
                    f"颈线 {neck:.2f}，目标 {target:.2f}"
                ),
            })
    
    return results


# ───────────────────────────────────────────────
# 3. 头肩顶
# ───────────────────────────────────────────────

def detect_head_shoulder_top(
    df: pd.DataFrame, window: int = 60, tolerance: float = 0.03
) -> List[Dict[str, Any]]:
    """
    检测头肩顶形态。

    识别条件：
      - 三个峰：左肩 < 头 > 右肩
      - 头明显高于两个肩
      - 两个肩高度相近（在 tolerance 内）
      - 颈线连接左肩和右肩之间的两个低点

    Args:
        df: OHLCV DataFrame
        window: 扫描窗口，默认 60
        tolerance: 两肩价格容差，默认 3%

    Returns:
        头肩顶形态列表
    """
    if df is None or len(df) < window * 2 // 3:
        return []
    
    df = df.copy().tail(window).reset_index(drop=True)
    peaks, troughs = _find_pivots(df, window=5)
    
    if len(peaks) < 3 or len(troughs) < 2:
        return []
    
    results: List[Dict[str, Any]] = []
    
    for i in range(len(peaks) - 2):
        for j in range(i + 1, len(peaks) - 1):
            for k in range(j + 1, len(peaks)):
                left = peaks.iloc[i]
                head = peaks.iloc[j]
                right = peaks.iloc[k]
                
                # 头必须高于两肩
                if not (head["high"] > left["high"] and head["high"] > right["high"]):
                    continue
                
                # 两肩相近
                shoulder_avg = (left["high"] + right["high"]) / 2
                if abs(left["high"] - right["high"]) / shoulder_avg > tolerance:
                    continue
                
                # 左肩与头之间、头与右肩之间各有一个低点
                t1 = troughs[(troughs.index > left.name) & (troughs.index < head.name)]
                t2 = troughs[(troughs.index > head.name) & (troughs.index < right.name)]
                if len(t1) == 0 or len(t2) == 0:
                    continue
                
                neck = min(t1["low"].min(), t2["low"].min())
                
                # 确认跌破颈线
                confirm = df.loc[right.name:]
                if len(confirm) < 2:
                    continue
                break_confirm = confirm.iloc[1:]
                break_confirm = break_confirm[break_confirm["close"] < neck]
                if len(break_confirm) == 0:
                    continue
                
                target = neck - (head["high"] - neck)
                confidence = min(1.0, (head["high"] - neck) / (head["high"] * 0.1)) * 0.8
                confidence = round(min(1.0, confidence), 3)
                
                results.append({
                    "type": "head_shoulder_top",
                    "start_date": str(left["date"]),
                    "end_date": str(break_confirm.iloc[0]["date"]),
                    "shoulder_dates": [str(left["date"]), str(right["date"])],
                    "shoulder_prices": [round(float(left["high"]), 3), round(float(right["high"]), 3)],
                    "head_date": str(head["date"]),
                    "head_price": round(float(head["high"]), 3),
                    "neck_line": round(float(neck), 3),
                    "confidence": confidence,
                    "target": round(float(target), 3),
                    "description": (
                        f"头肩顶：左肩 {left['high']:.2f} → 头 {head['high']:.2f} → 右肩 {right['high']:.2f}，"
                        f"颈线 {neck:.2f}，目标 {target:.2f}"
                    ),
                })
    
    return results


# ───────────────────────────────────────────────
# 4. 头肩底
# ───────────────────────────────────────────────

def detect_head_shoulder_bottom(
    df: pd.DataFrame, window: int = 60, tolerance: float = 0.03
) -> List[Dict[str, Any]]:
    """
    检测头肩底形态。

    识别条件：
      - 三个谷：左肩 > 头 < 右肩
      - 头明显低于两个肩
      - 两肩高度相近
      - 颈线连接左肩和右肩之间的两个高点

    Args:
        df: OHLCV DataFrame
        window: 扫描窗口，默认 60
        tolerance: 两肩价格容差，默认 3%

    Returns:
        头肩底形态列表
    """
    if df is None or len(df) < window * 2 // 3:
        return []
    
    df = df.copy().tail(window).reset_index(drop=True)
    peaks, troughs = _find_pivots(df, window=5)
    
    if len(troughs) < 3 or len(peaks) < 2:
        return []
    
    results: List[Dict[str, Any]] = []
    
    for i in range(len(troughs) - 2):
        for j in range(i + 1, len(troughs) - 1):
            for k in range(j + 1, len(troughs)):
                left = troughs.iloc[i]
                head = troughs.iloc[j]
                right = troughs.iloc[k]
                
                if not (head["low"] < left["low"] and head["low"] < right["low"]):
                    continue
                
                shoulder_avg = (left["low"] + right["low"]) / 2
                if abs(left["low"] - right["low"]) / shoulder_avg > tolerance:
                    continue
                
                p1 = peaks[(peaks.index > left.name) & (peaks.index < head.name)]
                p2 = peaks[(peaks.index > head.name) & (peaks.index < right.name)]
                if len(p1) == 0 or len(p2) == 0:
                    continue
                
                neck = max(p1["high"].max(), p2["high"].max())
                
                confirm = df.loc[right.name:]
                if len(confirm) < 2:
                    continue
                break_confirm = confirm.iloc[1:]
                break_confirm = break_confirm[break_confirm["close"] > neck]
                if len(break_confirm) == 0:
                    continue
                
                target = neck + (neck - head["low"])
                confidence = min(1.0, (neck - head["low"]) / (neck * 0.1)) * 0.8
                confidence = round(min(1.0, confidence), 3)
                
                results.append({
                    "type": "head_shoulder_bottom",
                    "start_date": str(left["date"]),
                    "end_date": str(break_confirm.iloc[0]["date"]),
                    "shoulder_dates": [str(left["date"]), str(right["date"])],
                    "shoulder_prices": [round(float(left["low"]), 3), round(float(right["low"]), 3)],
                    "head_date": str(head["date"]),
                    "head_price": round(float(head["low"]), 3),
                    "neck_line": round(float(neck), 3),
                    "confidence": confidence,
                    "target": round(float(target), 3),
                    "description": (
                        f"头肩底：左肩 {left['low']:.2f} → 头 {head['low']:.2f} → 右肩 {right['low']:.2f}，"
                        f"颈线 {neck:.2f}，目标 {target:.2f}"
                    ),
                })
    
    return results


# ───────────────────────────────────────────────
# 5. 三角形
# ───────────────────────────────────────────────

def detect_triangle(
    df: pd.DataFrame, window: int = 40
) -> List[Dict[str, Any]]:
    """
    检测三角形形态（收敛、上升、下降）。

    识别条件（收敛三角形）：
      - 近期高点连线呈下降趋势线
      - 近期低点连线呈上升趋势线
      - 两线收敛

    Args:
        df: OHLCV DataFrame
        window: 扫描窗口，默认 40

    Returns:
        三角形形态列表，包含 subtype: 'convergent' | 'ascending' | 'descending'
    """
    if df is None or len(df) < window * 2 // 3:
        return []
    
    df = df.copy().tail(window).reset_index(drop=True)
    peaks, troughs = _find_pivots(df, window=3)
    
    if len(peaks) < 2 or len(troughs) < 2:
        return []
    
    results: List[Dict[str, Any]] = []
    
    # 取最近 3 个高点和 3 个低点进行线性拟合
    recent_peaks = peaks.tail(3)
    recent_troughs = troughs.tail(3)
    
    if len(recent_peaks) < 2 or len(recent_troughs) < 2:
        return []
    
    # 高点趋势线斜率
    x_high = np.arange(len(recent_peaks)).astype(float)
    y_high = recent_peaks["high"].values.astype(float)
    slope_high = np.polyfit(x_high, y_high, 1)[0] if len(x_high) > 1 else 0.0
    
    # 低点趋势线斜率
    x_low = np.arange(len(recent_troughs)).astype(float)
    y_low = recent_troughs["low"].values.astype(float)
    slope_low = np.polyfit(x_low, y_low, 1)[0] if len(x_low) > 1 else 0.0
    
    # 判断类型
    subtype = "convergent"
    if slope_high < -0.01 and slope_low > 0.01:
        subtype = "convergent"
    elif abs(slope_high) < 0.01 and slope_low > 0.01:
        subtype = "ascending"
    elif slope_high < -0.01 and abs(slope_low) < 0.01:
        subtype = "descending"
    else:
        # 不够典型，不返回
        return []
    
    # 计算当前收敛区间
    latest = df.iloc[-1]
    upper = recent_peaks["high"].iloc[-1]
    lower = recent_troughs["low"].iloc[-1]
    
    confidence = 0.5
    if len(df) > 10:
        # 收敛程度
        range_ratio = (upper - lower) / ((df["high"].max() - df["low"].min()) + 1e-6)
        confidence = min(1.0, max(0.3, 0.5 + (0.5 - range_ratio)))
    confidence = round(confidence, 3)
    
    results.append({
        "type": "triangle",
        "subtype": subtype,
        "start_date": str(recent_peaks.iloc[0]["date"]),
        "end_date": str(latest["date"]),
        "upper_bound": round(float(upper), 3),
        "lower_bound": round(float(lower), 3),
        "confidence": confidence,
        "description": (
            f"{subtype}三角形：上边界 {upper:.2f}，下边界 {lower:.2f}，"
            f"等待突破方向"
        ),
    })
    
    return results


# ───────────────────────────────────────────────
# 6. V 型反转
# ───────────────────────────────────────────────

def detect_v_reversal(
    df: pd.DataFrame, window: int = 20
) -> List[Dict[str, Any]]:
    """
    检测 V 型（或倒 V 型）反转。

    识别条件：
      - V 底：快速下跌后快速上涨，低点两侧对称
      - 倒 V 顶：快速上涨后快速下跌

    Args:
        df: OHLCV DataFrame
        window: 扫描窗口，默认 20

    Returns:
        V 型反转列表，subtype: 'bottom' | 'top'
    """
    if df is None or len(df) < window:
        return []
    
    df = df.copy().tail(window).reset_index(drop=True)
    if len(df) < 10:
        return []
    
    results: List[Dict[str, Any]] = []
    
    # 找窗口内的最低点和最高点
    min_idx = df["low"].idxmin()
    max_idx = df["high"].idxmax()
    
    # V 底：最低点在窗口中部偏后
    if 3 <= min_idx <= len(df) - 3:
        left = df.iloc[:min_idx]
        right = df.iloc[min_idx + 1:]
        if len(left) >= 2 and len(right) >= 2:
            drop = (left["high"].max() - df.loc[min_idx, "low"]) / (left["high"].max() + 1e-6)
            rise = (right["high"].max() - df.loc[min_idx, "low"]) / (df.loc[min_idx, "low"] + 1e-6)
            
            if drop > 0.03 and rise > 0.03:
                symmetry = 1 - abs(drop - rise) / max(drop, rise)
                confidence = round(min(1.0, symmetry * 0.8 + 0.2), 3)
                results.append({
                    "type": "v_reversal",
                    "subtype": "bottom",
                    "pivot_date": str(df.loc[min_idx, "date"]),
                    "end_date": str(df.loc[min_idx, "date"]),
                    "pivot_price": round(float(df.loc[min_idx, "low"]), 3),
                    "confidence": confidence,
                    "description": (
                        f"V型底反转：低点 {df.loc[min_idx, 'low']:.2f}，"
                        f"左侧跌幅 {drop:.1%}，右侧涨幅 {rise:.1%}"
                    ),
                })
    
    # 倒 V 顶：最高点在窗口中部偏后
    if 3 <= max_idx <= len(df) - 3 and max_idx != min_idx:
        left = df.iloc[:max_idx]
        right = df.iloc[max_idx + 1:]
        if len(left) >= 2 and len(right) >= 2:
            rise = (df.loc[max_idx, "high"] - left["low"].min()) / (left["low"].min() + 1e-6)
            drop = (df.loc[max_idx, "high"] - right["low"].min()) / (df.loc[max_idx, "high"] + 1e-6)
            
            if rise > 0.03 and drop > 0.03:
                symmetry = 1 - abs(rise - drop) / max(rise, drop)
                confidence = round(min(1.0, symmetry * 0.8 + 0.2), 3)
                results.append({
                    "type": "v_reversal",
                    "subtype": "top",
                    "pivot_date": str(df.loc[max_idx, "date"]),
                    "end_date": str(df.loc[max_idx, "date"]),
                    "pivot_price": round(float(df.loc[max_idx, "high"]), 3),
                    "confidence": confidence,
                    "description": (
                        f"倒V型顶反转：高点 {df.loc[max_idx, 'high']:.2f}，"
                        f"左侧涨幅 {rise:.1%}，右侧跌幅 {drop:.1%}"
                    ),
                })
    
    return results


# ───────────────────────────────────────────────
# 7. 斐波那契回调
# ───────────────────────────────────────────────

def detect_fibonacci_retracement(
    df: pd.DataFrame, swing_window: int = 30
) -> List[Dict[str, Any]]:
    """
    检测当前价格相对于最近波段高低点的斐波那契回调位。

    返回标准回调位：0.236, 0.382, 0.5, 0.618, 0.786

    Args:
        df: OHLCV DataFrame
        swing_window: 波段窗口，默认 30

    Returns:
        斐波那契回调位列表，含当前价格所处区间
    """
    if df is None or len(df) < swing_window:
        return []
    
    df = df.copy().tail(swing_window).reset_index(drop=True)
    
    swing_high = float(df["high"].max())
    swing_low = float(df["low"].min())
    current = float(df["close"].iloc[-1])
    
    if swing_high <= swing_low:
        return []
    
    # 斐波那契回调位
    levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    retracements = {}
    for lvl in levels:
        retracements[lvl] = round(swing_high - lvl * (swing_high - swing_low), 3)
    
    # 当前价格所处区间
    current_ratio = (swing_high - current) / (swing_high - swing_low)
    current_level = None
    for i in range(len(levels) - 1):
        if levels[i] <= current_ratio <= levels[i + 1]:
            current_level = f"{levels[i]:.3f} - {levels[i+1]:.3f}"
            break
    
    return [{
        "type": "fibonacci_retracement",
        "start_date": str(df["date"].iloc[0]),
        "end_date": str(df["date"].iloc[-1]),
        "swing_high": round(swing_high, 3),
        "swing_low": round(swing_low, 3),
        "current": round(current, 3),
        "current_ratio": round(current_ratio, 3),
        "current_level": current_level or "unknown",
        "levels": {f"{k:.3f}": v for k, v in retracements.items()},
        "description": (
            f"斐波那契回调：高点 {swing_high:.2f} → 低点 {swing_low:.2f}，"
            f"当前 {current:.2f} 位于 {current_ratio:.1%} 回调位"
        ),
    }]


# ───────────────────────────────────────────────
# 8. 一键检测
# ───────────────────────────────────────────────

def detect_all_patterns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    一键检测所有形态。

    依次调用：双顶、双底、头肩顶、头肩底、三角形、V 型反转、斐波那契回调。

    Args:
        df: OHLCV DataFrame

    Returns:
        所有检测到的形态合并列表
    """
    if df is None or len(df) == 0:
        return []
    
    results: List[Dict[str, Any]] = []
    
    results.extend(detect_double_top(df, window=60, tolerance=0.03))
    results.extend(detect_double_bottom(df, window=60, tolerance=0.03))
    results.extend(detect_head_shoulder_top(df, window=60, tolerance=0.03))
    results.extend(detect_head_shoulder_bottom(df, window=60, tolerance=0.03))
    results.extend(detect_triangle(df, window=40))
    results.extend(detect_v_reversal(df, window=20))
    results.extend(detect_fibonacci_retracement(df, swing_window=30))
    
    # 按置信度排序
    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return results
