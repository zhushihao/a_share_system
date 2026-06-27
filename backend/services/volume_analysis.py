# -*- coding: utf-8 -*-
"""
Volume Analysis Engine - 量价分析引擎

基于 OHLCV 数据识别量价关系特征。

支持的分析：
  - 量价节点（放量突破、缩量回调、天量、地量）
  - 量价背离
  - 支撑/阻力计算
  - 斐波那契位

注意：所有函数在数据不足时返回空列表或空字典。
"""

from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np


# ───────────────────────────────────────────────
# 1. 量价节点
# ───────────────────────────────────────────────

def detect_volume_nodes(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    检测量价节点（放量突破、缩量回调、天量、地量）。

    识别规则：
      - 放量突破：当日成交量 > 20 日均量 1.5 倍，且 close > 前日 close 3%
      - 缩量回调：当日成交量 < 20 日均量 0.6 倍，且 close < 前日 close 2%
      - 天量：成交量为最近 60 日最大值
      - 地量：成交量为最近 60 日最小值

    Args:
        df: OHLCV DataFrame，必须含 'date', 'close', 'volume' 列

    Returns:
        量价节点列表，每个元素含 type, date, close, volume, description
    """
    if df is None or len(df) < 20 or "volume" not in df.columns:
        return []
    
    df = df.copy().reset_index(drop=True)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["volume", "close"])
    
    if len(df) < 20:
        return []
    
    results: List[Dict[str, Any]] = []
    
    # 20 日均量
    df["vol_ma20"] = df["volume"].rolling(window=20, min_periods=10).mean()
    # 60 日极值
    df["vol_max60"] = df["volume"].rolling(window=60, min_periods=30).max()
    df["vol_min60"] = df["volume"].rolling(window=60, min_periods=30).min()
    # 涨跌幅
    df["change_pct"] = df["close"].pct_change()
    
    for i in range(20, len(df)):
        row = df.iloc[i]
        vol = row["volume"]
        vol_ma20 = row["vol_ma20"]
        change_pct = row["change_pct"]
        date = str(row["date"])
        close = round(float(row["close"]), 3)
        
        if pd.isna(vol_ma20) or vol_ma20 <= 0:
            continue
        
        ratio = vol / vol_ma20
        
        # 放量突破
        if ratio > 1.5 and change_pct > 0.03:
            results.append({
                "type": "volume_breakout",
                "direction": "up",  # 放量上涨 = bullish
                "date": date,
                "close": close,
                "volume": int(vol),
                "vol_ratio": round(float(ratio), 2),
                "description": (
                    f"放量突破：成交量 {vol:,.0f} ({ratio:.1f}x 均量)，"
                    f"涨幅 {change_pct:.1%}"
                ),
            })
        
        # 缩量回调
        elif ratio < 0.6 and change_pct < -0.02:
            results.append({
                "type": "volume_contraction",
                "direction": "up",  # 缩量回调在上涨趋势中 = bullish（整理后继续上涨）
                "date": date,
                "close": close,
                "volume": int(vol),
                "vol_ratio": round(float(ratio), 2),
                "description": (
                    f"缩量回调：成交量 {vol:,.0f} ({ratio:.1f}x 均量)，"
                    f"跌幅 {change_pct:.1%}"
                ),
            })
        
        # 天量（最近 60 日最大）
        elif vol >= row["vol_max60"] and not pd.isna(row["vol_max60"]):
            results.append({
                "type": "volume_spike",
                "direction": "up" if change_pct >= 0 else "down",
                "date": date,
                "close": close,
                "volume": int(vol),
                "vol_ratio": round(float(ratio), 2),
                "description": f"天量：成交量 {vol:,.0f} 为近60日最大",
            })
        
        # 地量（最近 60 日最小）
        elif vol <= row["vol_min60"] and not pd.isna(row["vol_min60"]):
            results.append({
                "type": "volume_dry",
                "direction": "neutral",
                "date": date,
                "close": close,
                "volume": int(vol),
                "vol_ratio": round(float(ratio), 2),
                "description": f"地量：成交量 {vol:,.0f} 为近60日最小",
            })
    
    return results


# ───────────────────────────────────────────────
# 2. 量价背离
# ───────────────────────────────────────────────

def detect_volume_price_divergence(
    df: pd.DataFrame, window: int = 20
) -> List[Dict[str, Any]]:
    """
    检测量价背离。

    识别规则：
      - 顶背离：价格创新高，成交量未创新高（或下降）
      - 底背离：价格创新低，成交量未创新低（或上升）

    Args:
        df: OHLCV DataFrame
        window: 对比窗口，默认 20

    Returns:
        背离事件列表，含 type, date, description
    """
    if df is None or len(df) < window * 2 or "volume" not in df.columns:
        return []
    
    df = df.copy().reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.dropna(subset=["close", "volume"])
    
    if len(df) < window * 2:
        return []
    
    results: List[Dict[str, Any]] = []
    
    # 改进：使用局部极值检测，降低噪音
    # 找局部高点：前后2日都低于当前
    # 找局部低点：前后2日都高于当前
    
    peaks = []
    troughs = []
    
    for i in range(2, len(df) - 2):
        curr_close = df.iloc[i]["close"]
        prev2 = df.iloc[i - 2:i]["close"].values
        next2 = df.iloc[i + 1:i + 3]["close"].values
        
        # 局部高点：当前比前后都高
        if curr_close > max(prev2) and curr_close > max(next2):
            peaks.append({
                "idx": i,
                "close": curr_close,
                "vol": df.iloc[i]["volume"],
                "date": str(df.iloc[i]["date"]),
            })
        
        # 局部低点：当前比前后都低
        if curr_close < min(prev2) and curr_close < min(next2):
            troughs.append({
                "idx": i,
                "close": curr_close,
                "vol": df.iloc[i]["volume"],
                "date": str(df.iloc[i]["date"]),
            })
    
    # 检测顶背离：连续两个峰值，后峰价格更高但成交量更低
    for i in range(1, len(peaks)):
        p1 = peaks[i - 1]
        p2 = peaks[i]
        
        # 后峰价格更高（至少高1%）
        if p2["close"] > p1["close"] * 1.01:
            # 后峰成交量显著低于前峰（低于80%）
            if p2["vol"] < p1["vol"] * 0.8:
                results.append({
                    "type": "bearish_divergence",
                    "date": p2["date"],
                    "close": round(float(p2["close"]), 3),
                    "volume": int(p2["vol"]),
                    "description": (
                        f"顶背离：价格新高 {p2['close']:.2f}（前高{p1['close']:.2f}），"
                        f"但成交量 {p2['vol']:,.0f} 低于前高时的 {p1['vol']:,.0f}"
                    ),
                })
    
    # 检测底背离：连续两个谷值，后谷价格更低但成交量放大
    for i in range(1, len(troughs)):
        t1 = troughs[i - 1]
        t2 = troughs[i]
        
        # 后谷价格更低（至少低1%）
        if t2["close"] < t1["close"] * 0.99:
            # 后谷成交量高于前谷（放量下跌=潜在底部信号）
            if t2["vol"] > t1["vol"] * 1.2:
                results.append({
                    "type": "bullish_divergence",
                    "date": t2["date"],
                    "close": round(float(t2["close"]), 3),
                    "volume": int(t2["vol"]),
                    "description": (
                        f"底背离：价格新低 {t2['close']:.2f}（前低{t1['close']:.2f}），"
                        f"但成交量 {t2['vol']:,.0f} 放大（前谷{t1['vol']:,.0f}）"
                    ),
                })
    
    return results


# ───────────────────────────────────────────────
# 3. 支撑与阻力
# ───────────────────────────────────────────────

def calculate_support_resistance(
    df: pd.DataFrame, window: int = 60, lookback: int = 252
) -> Dict[str, Any]:
    """
    计算关键支撑与阻力位。

    方法：
      - 通过局部极值点聚类找出价格密集区
      - 支撑位：近期低点密集区
      - 阻力位：近期高点密集区
      - 最近 60 日内的最高/最低作为短期阻力/支撑

    Args:
        df: OHLCV DataFrame
        window: 近期窗口，默认 60
        lookback: 历史回看窗口，默认 252（约一年）

    Returns:
        字典含 support_levels, resistance_levels, recent_high, recent_low
    """
    if df is None or len(df) < window:
        return {}
    
    df = df.copy().tail(lookback).reset_index(drop=True)
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df = df.dropna(subset=["high", "low"])
    
    if len(df) < window:
        return {}
    
    recent = df.tail(window)
    recent_high = float(recent["high"].max())
    recent_low = float(recent["low"].min())
    current_close = float(df.iloc[-1]["close"]) if "close" in df.columns else (recent_high + recent_low) / 2
    
    # 局部极值聚类（改进版：使用局部极值 + 价格过滤）
    # 支撑位：仅取低于当前价的局部低点密集区
    # 阻力位：仅取高于当前价的局部高点密集区
    
    # 1. 找局部低点（支撑位候选）
    lows = df["low"].copy()
    local_lows = lows[(lows.shift(1) > lows) & (lows.shift(-1) > lows)]
    # 只保留低于当前价的低点
    local_lows = local_lows[local_lows < current_close]
    support_levels = []
    if len(local_lows) >= 2:
        # 对局部低点进行分箱聚类
        low_bins = pd.cut(local_lows, bins=min(10, len(local_lows)))
        low_clusters = low_bins.value_counts().sort_values(ascending=False)
        for interval, count in low_clusters.head(3).items():
            if count >= 2:
                level = round((interval.left + interval.right) / 2, 3)
                support_levels.append({
                    "price": level,
                    "touches": int(count),
                    "strength": round(min(1.0, count / 5), 3),
                })
    # 如果聚类不足，直接用近期最低
    if not support_levels and recent_low < current_close:
        support_levels.append({
            "price": round(recent_low, 3),
            "touches": 1,
            "strength": 0.3,
        })
    
    # 2. 找局部高点（阻力位候选）
    highs = df["high"].copy()
    local_highs = highs[(highs.shift(1) < highs) & (highs.shift(-1) < highs)]
    # 只保留高于当前价的高点
    local_highs = local_highs[local_highs > current_close]
    resistance_levels = []
    if len(local_highs) >= 2:
        high_bins = pd.cut(local_highs, bins=min(10, len(local_highs)))
        high_clusters = high_bins.value_counts().sort_values(ascending=False)
        for interval, count in high_clusters.head(3).items():
            if count >= 2:
                level = round((interval.left + interval.right) / 2, 3)
                resistance_levels.append({
                    "price": level,
                    "touches": int(count),
                    "strength": round(min(1.0, count / 5), 3),
                })
    # 如果聚类不足，直接用近期最高
    if not resistance_levels and recent_high > current_close:
        resistance_levels.append({
            "price": round(recent_high, 3),
            "touches": 1,
            "strength": 0.3,
        })
    
    return {
        "support_levels": sorted(support_levels, key=lambda x: x["price"]),
        "resistance_levels": sorted(resistance_levels, key=lambda x: x["price"]),
        "recent_high": round(recent_high, 3),
        "recent_low": round(recent_low, 3),
    }


# ───────────────────────────────────────────────
# 4. 斐波那契位
# ───────────────────────────────────────────────

def calculate_fibonacci_levels(
    df: pd.DataFrame, swing_window: int = 30
) -> Dict[str, Any]:
    """
    计算斐波那契关键位。

    返回标准回调位和扩展位：
      - 回调：0.236, 0.382, 0.5, 0.618, 0.786
      - 扩展：1.272, 1.618

    Args:
        df: OHLCV DataFrame
        swing_window: 波段窗口，默认 30

    Returns:
        字典含 swing_high, swing_low, current, retracements, extensions
    """
    if df is None or len(df) < swing_window:
        return {}
    
    df = df.copy().tail(swing_window).reset_index(drop=True)
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["high", "low", "close"])
    
    if len(df) < 5:
        return {}
    
    swing_high = float(df["high"].max())
    swing_low = float(df["low"].min())
    current = float(df["close"].iloc[-1])
    
    if swing_high <= swing_low:
        return {}
    
    diff = swing_high - swing_low
    
    retracements = {}
    for lvl in [0.236, 0.382, 0.5, 0.618, 0.786]:
        retracements[f"{lvl:.3f}"] = round(swing_high - lvl * diff, 3)
    
    extensions = {}
    for lvl in [1.272, 1.618]:
        extensions[f"{lvl:.3f}"] = round(swing_high + (lvl - 1.0) * diff, 3)
    
    return {
        "swing_high": round(swing_high, 3),
        "swing_low": round(swing_low, 3),
        "current": round(current, 3),
        "retracements": retracements,
        "extensions": extensions,
    }
