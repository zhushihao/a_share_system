# -*- coding: utf-8 -*-
"""
SignalComposer - 多因子买卖点合成引擎

核心目标：综合技术指标、形态识别、量价分析、支撑阻力、波浪结构、SuperTrend，
输出可执行的交易信号：买入/卖出/观望 + 入场价 + 止损价 + 止盈价 + 置信度 + 理由。

权重分配（6因子）：
  指标因子 25% + 形态因子 25% + 量价因子 20% + 支撑阻力 15% + 波浪 5% + SuperTrend 10%
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import pandas as pd
import numpy as np


# ───────────────────────────────────────────────
# 数据模型
# ───────────────────────────────────────────────

@dataclass
class FactorScore:
    """单因子评分"""
    name: str
    score: float          # -1.0 ~ +1.0
    weight: float         # 0.0 ~ 1.0
    description: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradingSignal:
    """交易信号（完整交易计划）"""
    type: str             # "BUY" / "SELL" / "HOLD"
    confidence: float     # 0.0 ~ 1.0
    entry_price: float    # 建议入场价
    stop_loss: float      # 止损价
    take_profit: float    # 主止盈价（TP2 / 2R）
    tp1: float            # 第一止盈位（1R）
    tp2: float            # 第二止盈位（2R，与 take_profit 一致）
    tp3: float            # 第三止盈位（3R）
    position_pct: float   # 建议仓位比例 0-1
    risk_reward_ratio: float  # 风险收益比（基于 TP2）
    rationale: str        # 综合理由
    factors: List[FactorScore] = field(default_factory=list)
    timestamp: str = ""
    symbol: str = ""
    period: str = "daily"
    trailing_stop: float = 0.0  # 追踪止损（价格移动1R后上移至保本价）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "signal_type": self.type,  # 兼容字段，满足 API 规范要求
            "confidence": round(self.confidence, 3),
            "entry_price": round(self.entry_price, 3),
            "stop_loss": round(self.stop_loss, 3),
            "take_profit": round(self.take_profit, 3),
            "tp1": round(self.tp1, 3),
            "tp2": round(self.tp2, 3),
            "tp3": round(self.tp3, 3),
            "position_pct": round(self.position_pct, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "rationale": self.rationale,
            "factors": [
                {
                    "name": f.name,
                    "score": round(f.score, 3),
                    "weight": f.weight,
                    "description": f.description,
                    "details": f.details,
                }
                for f in self.factors
            ],
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "period": self.period,
            "trailing_stop": round(self.trailing_stop, 3),
        }


# ───────────────────────────────────────────────
# 因子评分引擎
# ───────────────────────────────────────────────

def _score_indicators(df: pd.DataFrame, indicators: Dict[str, Any]) -> FactorScore:
    """
    技术指标因子评分 (-1.0 ~ +1.0)
    
    评分规则：
      + 趋势：MA多头排列/价格>MA20 → +0.3
      + 动量：MACD金叉/DIF向上/MACD_BAR为正 → +0.3
      + 超买超卖：KDJ在50以下金叉/RSI不极端 → +0.2
      + 波动：价格在BOLL中轨上方 → +0.2
      
      - 趋势：MA空头排列/价格<MA20 → -0.3
      - 动量：MACD死叉/DIF向下 → -0.3
      - 超买超卖：KDJ在80以上死叉/RSI超买 → -0.2
      - 波动：价格在BOLL中轨下方 → -0.2
    """
    if not indicators or len(df) < 2:
        return FactorScore("indicators", 0.0, 0.25, "数据不足，无法评分")
    
    score = 0.0
    details = {}
    
    curr = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else curr
    
    # 1. 趋势 (±0.3)
    trend_score = 0.0
    if all(k in indicators for k in ["ma5", "ma10", "ma20"]):
        ma5, ma10, ma20 = indicators["ma5"], indicators["ma10"], indicators["ma20"]
        close = indicators.get("close", curr.get("close", 0))
        if not any(pd.isna(v) for v in [ma5, ma10, ma20, close]):
            if ma5 > ma10 > ma20 and close > ma20:
                trend_score = 0.3
            elif ma5 < ma10 < ma20 and close < ma20:
                trend_score = -0.3
            elif close > ma20:
                trend_score = 0.1
            elif close < ma20:
                trend_score = -0.1
    details["trend"] = trend_score
    
    # 2. 动量 (±0.3)
    momentum_score = 0.0
    if all(k in indicators for k in ["macd_dif", "macd_dea", "macd_bar"]):
        dif, dea, bar = indicators["macd_dif"], indicators["macd_dea"], indicators["macd_bar"]
        if not any(pd.isna(v) for v in [dif, dea, bar]):
            prev_dif = prev.get("macd_dif", dif)
            prev_dea = prev.get("macd_dea", dea)
            # MACD金叉（DIF上穿DEA）
            if dif > dea and (pd.isna(prev_dif) or prev_dif <= prev_dea):
                momentum_score = 0.3
            # MACD死叉
            elif dif < dea and (pd.isna(prev_dif) or prev_dif >= prev_dea):
                momentum_score = -0.3
            elif dif > dea:
                momentum_score = 0.1
            elif dif < dea:
                momentum_score = -0.1
    details["momentum"] = momentum_score
    
    # 3. 超买超卖 (±0.2)
    oscillation_score = 0.0
    kdj_k = indicators.get("kdj_k")
    kdj_d = indicators.get("kdj_d")
    rsi6 = indicators.get("rsi6")
    
    if kdj_k is not None and kdj_d is not None and not pd.isna(kdj_k) and not pd.isna(kdj_d):
        prev_k = prev.get("kdj_k", kdj_k)
        prev_d = prev.get("kdj_d", kdj_d)
        # KDJ金叉在50以下（超卖区）
        if kdj_k > kdj_d and kdj_k < 50 and (pd.isna(prev_k) or prev_k <= prev_d):
            oscillation_score += 0.15
        # KDJ死叉在80以上（超买区）
        elif kdj_k < kdj_d and kdj_k > 80 and (pd.isna(prev_k) or prev_k >= prev_d):
            oscillation_score -= 0.15
    
    if rsi6 is not None and not pd.isna(rsi6):
        if rsi6 < 30:
            oscillation_score += 0.05  # 超卖
        elif rsi6 > 70:
            oscillation_score -= 0.05  # 超买
    details["oscillation"] = oscillation_score
    
    # 4. 波动 (±0.2)
    volatility_score = 0.0
    boll_mid = indicators.get("boll_mid")
    close = indicators.get("close", curr.get("close", 0))
    if boll_mid is not None and not pd.isna(boll_mid) and not pd.isna(close):
        if close > boll_mid:
            volatility_score = 0.2
        else:
            volatility_score = -0.2
    details["volatility"] = volatility_score
    
    score = trend_score + momentum_score + oscillation_score + volatility_score
    score = max(-1.0, min(1.0, score))
    
    # 生成描述
    direction = "偏多" if score > 0.2 else "偏空" if score < -0.2 else "中性"
    desc = f"技术指标{direction}：趋势{trend_score:+.1f} 动量{momentum_score:+.1f} 震荡{oscillation_score:+.1f} 波动{volatility_score:+.1f}"
    
    return FactorScore("indicators", score, 0.25, desc, details)


def _score_patterns(patterns: List[Dict[str, Any]]) -> FactorScore:
    """
    形态因子评分 (-1.0 ~ +1.0)
    
    买入形态：双底、头肩底、V型底、三角形突破 → 正向
    卖出形态：双顶、头肩顶、V型顶、三角形跌破 → 负向
    """
    if not patterns:
        return FactorScore("patterns", 0.0, 0.25, "未识别到形态")
    
    # 去重：同一 pattern 类型（含 subtype）只取最高置信度的一个，避免同一形态的不同变体过度计分
    dedup_patterns = {}
    for p in patterns:
        ptype = p.get("pattern", "") or p.get("type", "")
        subtype = p.get("subtype", "")
        key = f"{ptype}:{subtype}" if subtype else ptype
        conf = p.get("confidence", 0.5)
        if key not in dedup_patterns or conf > dedup_patterns[key].get("confidence", 0):
            dedup_patterns[key] = p
    
    score = 0.0
    details = {"detected": []}
    
    bullish_types = {"double_bottom", "head_shoulder_bottom", "v_reversal_bottom", 
                     "ascending_triangle", "symmetric_triangle_breakout"}
    bearish_types = {"double_top", "head_shoulder_top", "v_reversal_top",
                     "descending_triangle", "symmetric_triangle_breakdown"}
    
    for p in dedup_patterns.values():
        ptype = p.get("pattern", "") or p.get("type", "")
        conf = p.get("confidence", 0.5)
        subtype = p.get("subtype", "")
        
        # V 型反转特殊处理：type="v_reversal"，subtype 区分顶/底
        if ptype == "v_reversal":
            if subtype == "bottom":
                score += conf * 0.5
                details["detected"].append(f"+v_reversal_bottom({conf:.2f})")
            elif subtype == "top":
                score -= conf * 0.5
                details["detected"].append(f"-v_reversal_top({conf:.2f})")
        # 三角形特殊处理：type="triangle"，subtype 区分方向
        elif ptype == "triangle":
            if subtype == "ascending":
                score += conf * 0.4
                details["detected"].append(f"+ascending_triangle({conf:.2f})")
            elif subtype == "descending":
                score -= conf * 0.4
                details["detected"].append(f"-descending_triangle({conf:.2f})")
            elif subtype == "convergent":
                # 收敛三角形方向中性，轻微加分（等待突破）
                score += conf * 0.1
                details["detected"].append(f"~convergent_triangle({conf:.2f})")
        elif ptype in bullish_types:
            score += conf * 0.5
            details["detected"].append(f"+{ptype}({conf:.2f})")
        elif ptype in bearish_types:
            score -= conf * 0.5
            details["detected"].append(f"-{ptype}({conf:.2f})")
    
    score = max(-1.0, min(1.0, score))
    
    direction = "偏多" if score > 0.2 else "偏空" if score < -0.2 else "中性"
    desc = f"形态识别{direction}：识别到 {len(patterns)} 个形态"
    if details["detected"]:
        desc += f" ({', '.join(details['detected'][:3])})"
    
    return FactorScore("patterns", score, 0.15, desc, details)


def _score_volume(df: pd.DataFrame, volume_analysis: List[Dict[str, Any]]) -> FactorScore:
    """
    量价因子评分 (-1.0 ~ +1.0)
    
    放量突破/底背离 → 正向
    顶背离/放量滞涨 → 负向
    """
    if df is None or len(df) < 2:
        return FactorScore("volume", 0.0, 0.20, "数据不足")
    
    score = 0.0
    details = {}
    
    # 1. 最新量价节点
    latest_nodes = [n for n in volume_analysis if n.get("date") == str(df.iloc[-1].get("date", ""))]
    if latest_nodes:
        node = latest_nodes[0]
        ntype = node.get("type", "")
        direction = node.get("direction", "")
        if ntype == "volume_breakout":
            score += 0.4
            details["latest_node"] = "放量突破"
        elif ntype == "volume_contraction":
            if direction == "up":
                score += 0.2
                details["latest_node"] = "缩量回调（整理偏多）"
            else:
                score -= 0.2
                details["latest_node"] = "缩量回调（偏弱）"
        elif ntype == "volume_spike":
            if direction == "up":
                score += 0.3
                details["latest_node"] = "天量（偏多）"
            else:
                score -= 0.3
                details["latest_node"] = "天量（偏空）"
        elif ntype == "volume_dry":
            score += 0.0
            details["latest_node"] = "地量（观望）"
    # 2. 背离检测：使用正确逻辑 —— 当前价格 vs 前窗口极值对比
    if len(df) >= 20:
        recent = df.tail(20)
        # 顶背离：当前收盘价创前19日新高，但成交量未同步放大（<前高量的80%）
        prev_window = recent.iloc[:-1]
        if len(prev_window) > 0:
            max_close_idx = prev_window["close"].idxmax()
            max_close_price = prev_window.loc[max_close_idx, "close"]
            max_close_vol = prev_window.loc[max_close_idx, "volume"]
            min_close_idx = prev_window["close"].idxmin()
            min_close_vol = prev_window.loc[min_close_idx, "volume"]
            curr_close = recent.iloc[-1]["close"]
            curr_vol = recent.iloc[-1]["volume"]
            
            if curr_close > max_close_price * 1.01 and curr_vol < max_close_vol * 0.8:
                score -= 0.3
                details["divergence"] = "顶背离：价格创新高但成交量萎缩"
            # 底背离：当前收盘价创前19日新低，但成交量放大（>前低量的1.5倍）
            elif curr_close < prev_window["close"].min() * 0.99 and curr_vol > min_close_vol * 1.5:
                score += 0.2
                details["divergence"] = "潜在底背离：价格创新低但成交量放大"
    
    # 3. 成交量趋势
    if len(df) >= 5:
        recent_vol = df.tail(5)["volume"].mean()
        prev_vol = df.iloc[-10:-5]["volume"].mean() if len(df) >= 10 else recent_vol
        if prev_vol > 0:
            vol_trend = recent_vol / prev_vol
            if vol_trend > 1.3:
                score += 0.1
                details["vol_trend"] = f"放量({vol_trend:.1f}x)"
            elif vol_trend < 0.7:
                score -= 0.1
                details["vol_trend"] = f"缩量({vol_trend:.1f}x)"
    
    score = max(-1.0, min(1.0, score))
    
    direction = "偏多" if score > 0.2 else "偏空" if score < -0.2 else "中性"
    desc = f"量价分析{direction}"
    if details.get("latest_node"):
        desc += f"，最近{details['latest_node']}"
    if details.get("divergence"):
        desc += f"，{details['divergence']}"
    
    return FactorScore("volume", score, 0.20, desc, details)


def _score_support_resistance(df: pd.DataFrame, sr: Dict[str, Any]) -> FactorScore:
    """
    支撑阻力因子评分 (-1.0 ~ +1.0)
    
    价格接近强支撑 + 反弹 → 正向
    价格接近强阻力 + 回落 → 负向
    """
    if df is None or len(df) == 0 or not sr:
        return FactorScore("support_resistance", 0.0, 0.15, "数据不足")
    
    close = float(df.iloc[-1]["close"])
    
    # 兼容两种返回格式：原始 service 返回的 support_levels/resistance_levels（对象数组）
    # 以及 quote.py 映射后的 support/resistance（简单数组）
    support_levels = sr.get("support_levels", [])
    resistance_levels = sr.get("resistance_levels", [])
    
    # 如果传入的是 API 映射后的格式（简单数组），转换回对象数组
    if not support_levels and "support" in sr:
        support_levels = [{"price": float(p), "strength": 1.0} for p in sr["support"] if isinstance(p, (int, float))]
    if not resistance_levels and "resistance" in sr:
        resistance_levels = [{"price": float(p), "strength": 1.0} for p in sr["resistance"] if isinstance(p, (int, float))]
    
    if not support_levels and not resistance_levels:
        return FactorScore("support_resistance", 0.0, 0.15, "未找到支撑阻力位")
    
    score = 0.0
    details = {}
    
    # 找最近的支撑和阻力
    nearest_support = None
    nearest_resistance = None
    
    for s in support_levels:
        price = s.get("price", 0)
        if price < close and (nearest_support is None or price > nearest_support["price"]):
            nearest_support = s
    
    for r in resistance_levels:
        price = r.get("price", 0)
        if price > close and (nearest_resistance is None or price < nearest_resistance["price"]):
            nearest_resistance = r
    
    # 计算距离
    if nearest_support:
        support_dist = (close - nearest_support["price"]) / close
        details["nearest_support"] = {"price": nearest_support["price"], "distance": round(support_dist, 4)}
        # 距离支撑很近（<3%）→ 强买入信号
        if support_dist < 0.03:
            score += 0.5
        elif support_dist < 0.05:
            score += 0.3
        elif support_dist < 0.08:
            score += 0.1
    
    if nearest_resistance:
        resistance_dist = (nearest_resistance["price"] - close) / close
        details["nearest_resistance"] = {"price": nearest_resistance["price"], "distance": round(resistance_dist, 4)}
        # 距离阻力很近（<3%）→ 强卖出信号
        if resistance_dist < 0.03:
            score -= 0.5
        elif resistance_dist < 0.05:
            score -= 0.3
        elif resistance_dist < 0.08:
            score -= 0.1
    
    score = max(-1.0, min(1.0, score))
    
    direction = "偏多" if score > 0.2 else "偏空" if score < -0.2 else "中性"
    desc = f"支撑阻力{direction}"
    if nearest_support:
        desc += f"，最近支撑 {nearest_support['price']:.2f}（距离{details['nearest_support']['distance']:.1%}）"
    if nearest_resistance:
        desc += f"，最近阻力 {nearest_resistance['price']:.2f}（距离{details['nearest_resistance']['distance']:.1%}）"
    
    return FactorScore("support_resistance", score, 0.15, desc, details)


def _score_wave(df: pd.DataFrame, wave_structure: List[Dict[str, Any]]) -> FactorScore:
    """
    波浪结构因子评分 (-1.0 ~ +1.0)
    
    评分规则：
      - 当前处于 1/3/5 浪（推动浪）→ 正向
      - 当前处于 A/B/C 浪（修正浪）→ 负向
      - 浪 3 最长且最强劲 → 大幅加分
      - 浪 5 衰竭（短于浪 1）→ 轻微负向（可能见顶）
    """
    if not wave_structure or len(wave_structure) == 0:
        return FactorScore("wave", 0.0, 0.05, "未识别到波浪结构")
    
    # 取置信度最高的波浪结构
    best_wave = max(wave_structure, key=lambda w: w.get("confidence", 0))
    waves = best_wave.get("waves", [])
    confidence = best_wave.get("confidence", 0.5)
    
    if not waves:
        return FactorScore("wave", 0.0, 0.05, "波浪结构不完整")
    
    # 当前所处的最后一浪
    current_wave = waves[-1]
    label = current_wave.get("label", "")
    wave_type = current_wave.get("type", "")
    
    score = 0.0
    details = {"current_label": label, "wave_type": wave_type, "confidence": confidence}
    
    # 推动浪（1, 3, 5）→ 偏多
    if label in ("1", "3", "5"):
        if label == "3":
            score = 0.6  # 浪 3 最强
        elif label == "5":
            score = 0.3  # 浪 5 可能衰竭
        else:
            score = 0.2  # 浪 1 刚开始
    
    # 修正浪（A, B, C）→ 偏空
    elif label in ("A", "B", "C"):
        if label == "C":
            score = -0.5  # C 浪下跌最猛
        elif label == "A":
            score = -0.3
        else:
            score = -0.1  # B 浪反弹较弱
    
    # 置信度加权
    score = score * confidence
    score = max(-1.0, min(1.0, score))
    
    direction = "偏多" if score > 0.2 else "偏空" if score < -0.2 else "中性"
    desc = f"波浪结构{direction}：当前处于 {label} 浪（{wave_type}）"
    
    return FactorScore("wave", score, 0.05, desc, details)


def _calculate_stop_loss(df: pd.DataFrame, entry: float, sr: Dict[str, Any], signal_type: str) -> float:
    """
    计算止损价
    
    策略优先级：
    1. 最近支撑位下方（买入）/ 最近阻力位上方（卖出）
    2. ATR-based：2倍ATR
    3. 固定百分比：买入-5%，卖出+5%
    
    新增：止损价合理性验证，确保 BUY 时止损 < entry，SELL 时止损 > entry
    """
    if signal_type == "HOLD" or df is None or len(df) < 5:
        return 0.0  # HOLD信号不计算止损
    
    # ATR 计算（简化版：最近5日平均真实波幅）
    # 多取1行用于 shift 连续性，计算后再取最后5日均值
    recent = df.tail(21)
    tr1 = recent["high"] - recent["low"]
    tr2 = (recent["high"] - recent["close"].shift(1)).abs()
    tr3 = (recent["low"] - recent["close"].shift(1)).abs()
    atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).iloc[1:].tail(5).mean()
    
    stop_loss = 0.0
    
    if signal_type == "BUY":
        # 买入止损：取支撑下方或ATR
        stop_from_support = None
        support_levels = sr.get("support_levels", []) if sr else []
        if not support_levels and sr and "support" in sr:
            support_levels = [{"price": float(p)} for p in sr["support"] if isinstance(p, (int, float))]
        for s in support_levels:
            price = s.get("price", 0) if isinstance(s, dict) else float(s)
            if price < entry and (stop_from_support is None or price > stop_from_support):
                stop_from_support = price
        
        if stop_from_support and stop_from_support > entry * 0.9:
            stop_loss = round(stop_from_support * 0.97, 3)  # 支撑下方3%
        elif not pd.isna(atr) and atr > 0:
            stop_loss = round(entry - 2 * atr, 3)
        else:
            stop_loss = round(entry * 0.95, 3)
        
        # 验证：买入止损必须低于入场价
        if stop_loss >= entry:
            stop_loss = round(entry * 0.95, 3)
    
    else:  # SELL
        # A股不支持普通散户做空，SELL 信号应理解为 "卖出建议/平仓多头"
        # 止损设在阻力位上方：若价格向上突破，说明卖出判断错误
        # 止盈设在下方：若价格下跌，说明卖出判断正确
        stop_from_resistance = None
        resistance_levels = sr.get("resistance_levels", []) if sr else []
        if not resistance_levels and sr and "resistance" in sr:
            resistance_levels = [{"price": float(p)} for p in sr["resistance"] if isinstance(p, (int, float))]
        for r in resistance_levels:
            price = r.get("price", 0) if isinstance(r, dict) else float(r)
            if price > entry and (stop_from_resistance is None or price < stop_from_resistance):
                stop_from_resistance = price
        
        if stop_from_resistance and stop_from_resistance < entry * 1.1:
            stop_loss = round(stop_from_resistance * 1.03, 3)  # 阻力上方3%
        elif not pd.isna(atr) and atr > 0:
            stop_loss = round(entry + 2 * atr, 3)
        else:
            stop_loss = round(entry * 1.05, 3)
        
        # 验证：卖出止损必须高于入场价
        if stop_loss <= entry:
            stop_loss = round(entry * 1.05, 3)
    
    return stop_loss


def _calculate_take_profit(entry: float, stop_loss: float, signal_type: str) -> tuple[float, float, float]:
    """
    计算多止盈位：TP1 (1R), TP2 (2R, 主止盈), TP3 (3R)
    
    修复：当 stop_loss 为0或无效时，使用合理的 fallback 值（固定10%）
    而不是 risk = entry 导致 take_profit = entry * 3
    
    返回: (tp1, tp2, tp3)
    """
    risk = abs(entry - stop_loss)
    
    # 止损无效时使用 fallback（固定百分比）
    if risk <= 0 or stop_loss <= 0:
        # 修复：当 stop_loss=0 时，不应返回非零止盈位，与 position_pct=0 保持一致
        return 0.0, 0.0, 0.0
    
    # 止损异常大时的保护（如风险超过入场价20%）
    if risk > entry * 0.20:
        risk = entry * 0.20
    
    if signal_type == "BUY":
        tp1 = round(entry + risk, 3)       # 1R
        tp2 = round(entry + risk * 2, 3)   # 2R
        tp3 = round(entry + risk * 3, 3)   # 3R
    else:
        tp1 = round(entry - risk, 3)       # 1R
        tp2 = round(entry - risk * 2, 3)   # 2R
        tp3 = round(entry - risk * 3, 3)   # 3R
    
    return tp1, tp2, tp3


def _calculate_risk_reward_ratio(entry: float, stop_loss: float, take_profit: float, signal_type: str) -> float:
    """
    计算风险收益比（R:R）
    """
    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    if risk <= 0 or stop_loss <= 0:
        return 0.0
    return round(reward / risk, 2)


def _calculate_position_pct(confidence: float, risk_reward_ratio: float, signal_type: str, df: pd.DataFrame = None, entry_price: float = None) -> float:
    """
    计算建议仓位比例

    改进：
    1. 使用连续仓位（10% 粒度），避免 confidence 微小变化导致仓位跳变
    2. 当风险收益比 < 1.5 时降低仓位（信号质量不足）
    3. 当风险收益比 >= 2.0 时允许高仓位（高赔率信号）
    4. 波动率调整：高波动（ATR > 5%）降低仓位，低波动（ATR < 2%）增加仓位
    """
    if signal_type == "HOLD":
        return 0.0

    # 基础仓位 = sqrt(confidence) * 最大仓位
    # 使用平方根平滑，避免高置信度时仓位过于激进
    base_pct = min(1.0, confidence ** 0.5)

    # 根据风险收益比调整
    if risk_reward_ratio < 1.0:
        # 赔率不足，大幅减仓
        base_pct *= 0.25
    elif risk_reward_ratio < 1.5:
        base_pct *= 0.5
    elif risk_reward_ratio >= 2.5:
        # 高赔率，可加仓
        base_pct = min(1.0, base_pct * 1.15)

    # 波动率调整（如果数据可用）
    if df is not None and entry_price is not None and len(df) >= 5 and entry_price > 0:
        try:
            recent = df.tail(5)
            atr = (recent["high"] - recent["low"]).mean()
            volatility = atr / entry_price
            if volatility > 0.05:
                base_pct *= 0.7  # 高波动，降低 30%
            elif volatility < 0.02:
                base_pct = min(1.0, base_pct * 1.1)  # 低波动，增加 10%
        except Exception:
            pass

    # 连续仓位（10% 粒度），避免跳变
    if base_pct < 0.25:
        return 0.0
    return round(round(base_pct / 0.1) * 0.1, 1)


def _calc_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """
    计算 SuperTrend 指标（ATR-based 趋势跟踪和动态止损）
    
    返回 DataFrame，附加 supertrend_value, supertrend_direction 列
    direction: 1 = bullish, -1 = bearish
    
    优化：使用 NumPy 数组加速循环，减少 pandas 索引开销
    """
    if df is None or len(df) < period + 1:
        return df.copy() if df is not None else pd.DataFrame()
    
    df = df.copy().reset_index(drop=True)
    n = len(df)
    
    # ATR 计算
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()
    
    # 基础上下轨
    hl2 = (df["high"] + df["low"]) / 2.0
    upper_band = (hl2 + multiplier * atr).to_numpy()
    lower_band = (hl2 - multiplier * atr).to_numpy()
    close = df["close"].to_numpy()
    
    # NumPy 数组加速循环
    st = np.zeros(n, dtype=np.float64)
    direction = np.ones(n, dtype=np.int8)
    
    # 第一个有效位置（period 之后）初始化
    first = period
    if close[first] > upper_band[first - 1]:
        direction[first] = 1
    elif close[first] < lower_band[first - 1]:
        direction[first] = -1
    else:
        direction[first] = 1  # 默认 bullish
    
    st[first] = lower_band[first] if direction[first] == 1 else upper_band[first]
    
    for i in range(first + 1, n):
        prev_dir = direction[i - 1]
        prev_st = st[i - 1]
        
        if close[i] > upper_band[i - 1]:
            direction[i] = 1
        elif close[i] < lower_band[i - 1]:
            direction[i] = -1
        else:
            direction[i] = prev_dir
        
        if direction[i] == 1:
            st[i] = max(lower_band[i], prev_st)
        else:
            st[i] = min(upper_band[i], prev_st)
    
    df["supertrend_value"] = st
    df["supertrend_direction"] = direction
    return df


def _score_supertrend(df: pd.DataFrame) -> FactorScore:
    """
    SuperTrend 因子评分 (-1.0 ~ +1.0)
    
    当价格高于 SuperTrend 线且方向为 bullish → 正向
    当价格低于 SuperTrend 线且方向为 bearish → 负向
    """
    if df is None or len(df) < 15:
        return FactorScore("supertrend", 0.0, 0.10, "数据不足，无法计算SuperTrend")
    
    st_df = _calc_supertrend(df, period=10, multiplier=3.0)
    if len(st_df) == 0 or "supertrend_direction" not in st_df.columns:
        return FactorScore("supertrend", 0.0, 0.10, "SuperTrend计算失败")
    
    latest = st_df.iloc[-1]
    direction = int(latest["supertrend_direction"])
    close = float(latest["close"])
    st_value = float(latest["supertrend_value"])
    
    # 方向一致性评分
    if direction == 1 and close > st_value:
        score = 0.5
        desc = f"SuperTrend bullish：价格 {close:.2f} 高于趋势线 {st_value:.2f}"
    elif direction == -1 and close < st_value:
        score = -0.5
        desc = f"SuperTrend bearish：价格 {close:.2f} 低于趋势线 {st_value:.2f}"
    else:
        score = 0.0
        desc = f"SuperTrend 中性：价格接近趋势线 {st_value:.2f}"
    
    # 若最近3日方向一致，增强信号
    if len(st_df) >= 4:
        recent_dirs = st_df["supertrend_direction"].iloc[-3:]
        if all(d == 1 for d in recent_dirs) and score > 0:
            score = 0.7
            desc += "，连续3日 bullish"
        elif all(d == -1 for d in recent_dirs) and score < 0:
            score = -0.7
            desc += "，连续3日 bearish"
    
    return FactorScore("supertrend", round(score, 3), 0.10, desc, 
                       {"direction": direction, "value": round(st_value, 3)})


def _check_signal_debounce(symbol: str, signal_type: str, days: int = 5) -> tuple[bool, str]:
    """
    信号防抖：检查最近 N 日内是否有同股票同向信号
    
    Returns:
        (should_hold, reason) — should_hold=True 时建议强制HOLD
    """
    if signal_type == "HOLD":
        return False, ""
    
    try:
        import asyncio
        from backend.models.database import DATABASE_PATH, init_db, get_signals
        
        # 同步执行数据库查询（在异步上下文中可能有问题，但compose_signal是同步的）
        # 使用 sqlite3 直接查询避免异步问题
        import sqlite3
        from datetime import datetime, timedelta
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM signals WHERE symbol = ? AND signal_type = ? AND timestamp >= ? AND status = 'open' ORDER BY timestamp DESC LIMIT 1",
            (symbol, signal_type, cutoff)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return True, f"最近{days}日内已有同向{signal_type}信号（{row['timestamp'][:10]}），避免重复建仓"
    except Exception:
        pass
    
    return False, ""


def _calculate_trailing_stop(entry: float, stop_loss: float, signal_type: str) -> float:
    """
    计算追踪止损（Trailing Stop）
    
    规则：价格移动 1R 后，止损上移至保本价（entry_price）
    后续每移动 1R，止损上移 0.5R
    
    初始值与 stop_loss 相同，后端仅提供计算规则，实际追踪由前端/定时任务执行
    """
    if signal_type == "HOLD" or stop_loss <= 0 or entry <= 0:
        return 0.0
    
    risk = abs(entry - stop_loss)
    if risk <= 0:
        return 0.0
    
    # 保本价 = entry_price（当价格移动1R后）
    # 当前仅返回初始追踪止损 = 保本价（作为参考值）
    # 实际运行时：当 price 达到 entry + risk 时，trailing_stop = entry
    return round(entry, 3)


# ───────────────────────────────────────────────
# 主合成引擎
# ───────────────────────────────────────────────

def compose_signal(
    symbol: str,
    df: pd.DataFrame,
    indicators: Dict[str, Any],
    patterns: List[Dict[str, Any]],
    volume_analysis: List[Dict[str, Any]],
    support_resistance: Dict[str, Any],
    period: str = "daily",
) -> TradingSignal:
    """
    多因子合成：输出完整交易信号
    
    Args:
        symbol: 股票代码
        df: OHLCV DataFrame
        indicators: 最新指标字典
        patterns: 形态识别结果
        volume_analysis: 量价分析结果
        support_resistance: 支撑阻力结果
        period: 周期
    
    Returns:
        TradingSignal 完整交易计划
    """
    from datetime import datetime
    
    # 1. 各因子评分
    factor_indicators = _score_indicators(df, indicators)
    factor_patterns = _score_patterns(patterns)
    factor_volume = _score_volume(df, volume_analysis)
    factor_sr = _score_support_resistance(df, support_resistance)
    factor_supertrend = _score_supertrend(df)
    
    # 2. 波浪因子（可选，数据不足时返回中性）
    from backend.services.wave import detect_wave_structure
    wave_structure = detect_wave_structure(df) if len(df) >= 30 else []
    factor_wave = _score_wave(df, wave_structure)
    
    factors = [factor_indicators, factor_patterns, factor_volume, factor_sr, factor_wave, factor_supertrend]
    
    # 3. 加权合成（6因子：加入SuperTrend 10%，其余权重调整）
    weights = {
        "indicators": 0.30,      # 技术指标权重提升（趋势判断更核心）
        "patterns": 0.15,        # 形态权重降低（避免震荡市过度主导）
        "volume": 0.25,          # 量价权重提升（更直接的信号）
        "support_resistance": 0.15,
        "wave": 0.05,
        "supertrend": 0.10,
    }
    
    total_score = sum(
        f.score * weights.get(f.name, 0.0)
        for f in factors
    )
    
    # 3. 生成信号
    entry_price = float(indicators.get("close", df.iloc[-1]["close"])) if len(df) > 0 else 0.0
    
    # 信号阈值 —— 从 0.7 降低到 0.5，提高信号密度并配合仓位管理
    # 低置信度信号通过 position_pct 自动降仓，而非强制 HOLD
    if total_score > 0.5:
        signal_type = "BUY"
        confidence = min(1.0, total_score)
    elif total_score < -0.5:
        signal_type = "SELL"
        confidence = min(1.0, abs(total_score))
    else:
        signal_type = "HOLD"
        confidence = min(1.0, abs(total_score))
    
    # 4. 信号防抖（Debounce）：最近5日有同向信号则强制HOLD
    should_hold = False
    debounce_reason = ""
    if signal_type != "HOLD":
        should_hold, debounce_reason = _check_signal_debounce(symbol, signal_type, days=5)
        if should_hold:
            signal_type = "HOLD"
            confidence = min(confidence, 0.5)
    
    # 5. 止损/止盈/风险收益比/追踪止损
    if signal_type == "HOLD":
        stop_loss = 0.0
        take_profit = 0.0
        tp1 = 0.0
        tp2 = 0.0
        tp3 = 0.0
        risk_reward_ratio = 0.0
        trailing_stop = 0.0
    else:
        stop_loss = _calculate_stop_loss(df, entry_price, support_resistance, signal_type)
        tp1, tp2, tp3 = _calculate_take_profit(entry_price, stop_loss, signal_type)
        take_profit = tp2  # 主止盈保持为 TP2
        risk_reward_ratio = _calculate_risk_reward_ratio(entry_price, stop_loss, take_profit, signal_type)
        trailing_stop = _calculate_trailing_stop(entry_price, stop_loss, signal_type)
    
    # 6. 仓位建议（基于置信度 + 风险收益比 + 波动率）
    position_pct = _calculate_position_pct(confidence, risk_reward_ratio, signal_type, df, entry_price)
    
    # 7. 综合理由
    bullish_factors = [f.name for f in factors if f.score > 0.2]
    bearish_factors = [f.name for f in factors if f.score < -0.2]
    
    bullish_str = '、'.join(bullish_factors) if bullish_factors else '无'
    bearish_str = '、'.join(bearish_factors) if bearish_factors else '无'
    
    if signal_type == "BUY":
        rationale = f"买入信号（置信度{confidence:.0%}，R:R={risk_reward_ratio:.1f}）：{bullish_str} 共振"
        if bearish_factors:
            rationale += f"，注意 {bearish_str} 偏空"
        if tp1 > 0 and tp2 > 0 and tp3 > 0:
            rationale += f"；目标位 TP1={tp1:.2f} / TP2={tp2:.2f} / TP3={tp3:.2f}"
        if trailing_stop > 0:
            rationale += f"；追踪止损={trailing_stop:.2f}（价格移动1R后上移至保本价）"
    elif signal_type == "SELL":
        rationale = f"卖出信号（置信度{confidence:.0%}，R:R={risk_reward_ratio:.1f}）：{bearish_str} 共振"
        if bullish_factors:
            rationale += f"，注意 {bullish_str} 偏多"
        if tp1 > 0 and tp2 > 0 and tp3 > 0:
            rationale += f"；目标位 TP1={tp1:.2f} / TP2={tp2:.2f} / TP3={tp3:.2f}"
        if trailing_stop > 0:
            rationale += f"；追踪止损={trailing_stop:.2f}（价格移动1R后上移至保本价）"
    else:
        rationale = f"观望：多空因素交织，{bullish_str} 偏多 vs {bearish_str} 偏空"
        # 如果是因为防抖强制HOLD，追加原因
        if should_hold:
            rationale += f"；{debounce_reason}"
    
    # 因子名称中文化映射（用于 rationale 展示）
    factor_name_map = {
        "indicators": "技术指标",
        "patterns": "形态识别",
        "volume": "量价分析",
        "support_resistance": "支撑阻力",
        "wave": "波浪结构",
        "supertrend": "SuperTrend",
    }
    # 按从长到短排序，避免子串替换问题
    for en_name in sorted(factor_name_map.keys(), key=len, reverse=True):
        rationale = rationale.replace(en_name, factor_name_map[en_name])
    
    return TradingSignal(
        type=signal_type,
        confidence=confidence,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        position_pct=position_pct,
        risk_reward_ratio=risk_reward_ratio,
        rationale=rationale,
        factors=factors,
        timestamp=datetime.now().isoformat(),
        symbol=symbol,
        period=period,
        trailing_stop=trailing_stop,
    )


# ───────────────────────────────────────────────
# 便捷接口
# ───────────────────────────────────────────────

def generate_trading_signal(
    symbol: str,
    df: pd.DataFrame,
    indicators: Dict[str, Any],
    patterns: List[Dict[str, Any]],
    volume_analysis: List[Dict[str, Any]],
    support_resistance: Dict[str, Any],
    period: str = "daily",
) -> Dict[str, Any]:
    """便捷接口：直接返回字典格式"""
    signal = compose_signal(symbol, df, indicators, patterns, volume_analysis, support_resistance, period)
    return signal.to_dict()
