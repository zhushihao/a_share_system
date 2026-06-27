# -*- coding: utf-8 -*-
"""
MultiPeriodResonance - 多周期共振分析引擎

核心逻辑：同时分析日/周/月三个周期的趋势方向，
判断三周期是否同向（共振 = 高置信度）。

规则：
  - 大周期定方向（月/周趋势）
  - 中周期找位置（日线形态/支撑阻力）
  - 小周期定时机（分钟/日突破点）
"""

from typing import Dict, Any
import pandas as pd


class MultiPeriodResonance:
    """多周期共振分析器"""
    
    def __init__(self, platform):
        self._platform = platform
    
    def analyze(self, symbol: str) -> Dict[str, Any]:
        """
        多周期共振分析
        
        Returns:
            {
                "daily_trend": "bull" | "bear" | "neutral",
                "weekly_trend": "bull" | "bear" | "neutral",
                "monthly_trend": "bull" | "bear" | "neutral",
                "resonance": bool,  # 三周期同向
                "confidence": float,  # 0-1
                "direction": "bull" | "bear" | "neutral",
                "description": str,
            }
        """
        # 获取三个周期的指标数据
        daily = self._get_trend(symbol, "daily")
        weekly = self._get_trend(symbol, "weekly")
        monthly = self._get_trend(symbol, "monthly")
        
        trends = [daily, weekly, monthly]
        
        # 共振判断
        bull_count = sum(1 for t in trends if t == "bull")
        bear_count = sum(1 for t in trends if t == "bear")
        neutral_count = sum(1 for t in trends if t == "neutral")
        
        resonance = (bull_count == 3) or (bear_count == 3)
        
        if bull_count >= 2:
            direction = "bull"
        elif bear_count >= 2:
            direction = "bear"
        else:
            direction = "neutral"
        
        # 置信度：三周期同向 = 0.95，两周期同向 = 0.7，一周期 = 0.4
        if resonance:
            confidence = 0.95
        elif bull_count >= 2 or bear_count >= 2:
            confidence = 0.7
        elif bull_count == 1 or bear_count == 1:
            confidence = 0.4
        else:
            confidence = 0.2
        
        # 描述
        def trend_label(t):
            return '涨' if t == 'bull' else '跌' if t == 'bear' else '平'
        
        if resonance:
            desc = f"三周期共振：日{trend_label(daily)} + 周{trend_label(weekly)} + 月{trend_label(monthly)}，高置信度"
        elif direction == "bull":
            desc = f"两周期偏多：日{trend_label(daily)} + 周{trend_label(weekly)} + 月{trend_label(monthly)}，中等置信度"
        elif direction == "bear":
            desc = f"两周期偏空：日{trend_label(daily)} + 周{trend_label(weekly)} + 月{trend_label(monthly)}，中等置信度"
        else:
            desc = f"周期分歧：日{trend_label(daily)} + 周{trend_label(weekly)} + 月{trend_label(monthly)}，观望"
        
        return {
            "daily_trend": daily,
            "weekly_trend": weekly,
            "monthly_trend": monthly,
            "resonance": resonance,
            "confidence": confidence,
            "direction": direction,
            "description": desc,
        }
    
    def _get_trend(self, symbol: str, period: str) -> str:
        """
        获取单个周期的趋势方向（增强版 v2）
        
        综合判断指标：
        1. MA排列（MA5>MA20>MA60 = 强多头）
        2. MA60方向（MA60 向上/向下 = 大周期趋势）
        3. MACD柱状图趋势（>0 且上升 = 动能增强）
        4. RSI趋势（>50 偏多，<50 偏空，趋势方向）
        5. KDJ金叉/死叉
        6. 价格 vs BOLL中轨（>中轨 = 偏多）
        7. 动量（价格 vs 20日高点/低点）
        
        评分 >= 2 → bull, <= -1 → bear, else → neutral
        （阈值降低，提高信号密度）
        """
        import numpy as np
        try:
            indicators_df = self._platform.get_indicators(symbol, period=period)
            if indicators_df is None or len(indicators_df) == 0:
                return "neutral"
            
            # 需要至少20条数据才判断趋势
            if len(indicators_df) < 20:
                return "neutral"
            
            latest = indicators_df.iloc[-1]
            prev = indicators_df.iloc[-2] if len(indicators_df) >= 2 else latest
            prev2 = indicators_df.iloc[-3] if len(indicators_df) >= 3 else prev
            close = latest.get("close", np.nan)
            
            score = 0
            
            # 1. MA排列（权重+2）
            ma5 = latest.get("ma5", np.nan)
            ma20 = latest.get("ma20", np.nan)
            ma60 = latest.get("ma60", np.nan)
            if pd.notna(ma5) and pd.notna(ma20) and pd.notna(ma60):
                if ma5 > ma20 > ma60:
                    score += 2
                elif ma5 > ma20:
                    score += 1
                elif ma20 < ma60:
                    score -= 2
                elif ma5 < ma20:
                    score -= 1
            elif pd.notna(ma5) and pd.notna(ma20):
                if ma5 > ma20:
                    score += 1
                elif ma5 < ma20:
                    score -= 1
            
            # 2. MA60方向（新增，权重±1）
            if pd.notna(ma60) and len(indicators_df) >= 10:
                ma60_5ago = indicators_df.iloc[-6].get("ma60", np.nan)
                ma60_10ago = indicators_df.iloc[-11].get("ma60", np.nan) if len(indicators_df) >= 11 else np.nan
                if pd.notna(ma60_5ago) and ma60 > ma60_5ago:
                    score += 1
                elif pd.notna(ma60_5ago) and ma60 < ma60_5ago:
                    score -= 1
                elif pd.notna(ma60_10ago) and ma60 > ma60_10ago:
                    score += 1
                elif pd.notna(ma60_10ago) and ma60 < ma60_10ago:
                    score -= 1
            
            # 3. MACD（权重+1，增强柱状图趋势）
            macd_dif = latest.get("macd_dif", np.nan)
            macd_dea = latest.get("macd_dea", np.nan)
            macd_bar = latest.get("macd_bar", np.nan)
            prev_dif = prev.get("macd_dif", np.nan)
            prev_dea = prev.get("macd_dea", np.nan)
            prev_bar = prev.get("macd_bar", np.nan)
            prev2_bar = prev2.get("macd_bar", np.nan)
            if pd.notna(macd_dif) and pd.notna(macd_dea):
                if macd_dif > macd_dea:
                    score += 1
                    # MACD柱状图扩大 = 动能增强
                    if pd.notna(prev_dif) and pd.notna(prev_dea) and (macd_dif - macd_dea) > (prev_dif - prev_dea):
                        score += 1
                    # MACD柱状图连续扩大（新增）
                    if pd.notna(macd_bar) and pd.notna(prev_bar) and pd.notna(prev2_bar):
                        if macd_bar > prev_bar > prev2_bar and macd_bar > 0:
                            score += 1
                        elif macd_bar < prev_bar < prev2_bar and macd_bar < 0:
                            score -= 1
                elif macd_dif < macd_dea:
                    score -= 1
            
            # 4. RSI（权重+1，增强趋势方向）
            rsi6 = latest.get("rsi6", np.nan)
            prev_rsi6 = prev.get("rsi6", np.nan)
            if pd.notna(rsi6):
                if rsi6 > 55:
                    score += 1
                elif rsi6 < 45:
                    score -= 1
                # RSI 趋势方向（新增）
                if pd.notna(prev_rsi6):
                    if rsi6 > prev_rsi6 and rsi6 > 50:
                        score += 1
                    elif rsi6 < prev_rsi6 and rsi6 < 50:
                        score -= 1
            
            # 5. KDJ（权重+1）
            kdj_k = latest.get("kdj_k", np.nan)
            kdj_d = latest.get("kdj_d", np.nan)
            prev_k = prev.get("kdj_k", np.nan)
            prev_d = prev.get("kdj_d", np.nan)
            if pd.notna(kdj_k) and pd.notna(kdj_d):
                if kdj_k > kdj_d and kdj_k < 80:
                    score += 1
                elif kdj_k < kdj_d and kdj_k > 20:
                    score -= 1
            
            # 6. BOLL（权重+1）
            boll_mid = latest.get("boll_mid", np.nan)
            if pd.notna(close) and pd.notna(boll_mid):
                if close > boll_mid:
                    score += 1
                elif close < boll_mid:
                    score -= 1
            
            # 7. 动量（价格 vs 20日高点/低点）
            if len(indicators_df) >= 20:
                recent_high = indicators_df["high"].iloc[-20:].max()
                recent_low = indicators_df["low"].iloc[-20:].min()
                if pd.notna(close) and pd.notna(recent_high) and pd.notna(recent_low):
                    if close > recent_high * 0.98:  # 接近20日高点
                        score += 1
                    elif close < recent_low * 1.02:  # 接近20日低点
                        score -= 1
            
            # 8. 成交量确认（新增，权重±1）
            if len(indicators_df) >= 5:
                recent_vol = indicators_df["volume"].iloc[-5:].mean()
                prev_vol = indicators_df["volume"].iloc[-10:-5].mean() if len(indicators_df) >= 10 else recent_vol
                if prev_vol > 0:
                    vol_ratio = recent_vol / prev_vol
                    if vol_ratio > 1.5 and score > 0:
                        score += 1
                    elif vol_ratio > 1.5 and score < 0:
                        score -= 1
            
            # 趋势判定（阈值降低，提高信号密度）
            if score >= 2:
                return "bull"
            elif score <= -1:
                return "bear"
            else:
                return "neutral"
        except Exception:
            return "neutral"


# 便捷函数
def analyze_resonance(symbol: str, platform) -> Dict[str, Any]:
    """便捷接口：分析多周期共振"""
    analyzer = MultiPeriodResonance(platform)
    return analyzer.analyze(symbol)
