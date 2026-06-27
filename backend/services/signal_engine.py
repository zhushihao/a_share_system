# -*- coding: utf-8 -*-
"""
Signal Engine - 信号引擎

职责：
1. 日线信号检测（蔡森12招、白大右侧、量价突破、均线金叉）
2. 日内信号检测（突破均价、放量滞涨、开盘八法）
3. 信号扫描、过滤、统计

设计模式：Strategy Pattern，每个策略独立实现 detect() 方法
"""

import sys
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import warnings

import pandas as pd
import numpy as np

# 复用 indicators 引擎
from backend.services.indicators import (
    calculate_all_indicators,
    calc_ma,
    calc_macd,
    calc_kdj,
    calc_rsi,
    calc_boll,
)


# ───────────────────────────────────────────────
# 数据模型
# ───────────────────────────────────────────────

class SignalType(str, Enum):
    """信号类型"""
    BUY = "BUY"          # 买入信号
    SELL = "SELL"        # 卖出信号
    WATCH = "WATCH"      # 关注信号
    ALERT = "ALERT"      # 预警


class SignalCategory(str, Enum):
    """信号分类"""
    DAILY = "daily"          # 日线信号
    INTRADAY = "intraday"    # 日内信号


class SignalStrategy(str, Enum):
    """信号策略"""
    # 日线
    MA_GOLDEN_CROSS = "ma_golden_cross"      # 均线金叉
    MA_DEATH_CROSS = "ma_death_cross"        # 均线死叉
    VOL_PRICE_BREAKOUT = "vol_price_breakout"  # 量价突破
    VOL_PRICE_COLLAPSE = "vol_price_collapse"  # 量价崩溃
    CAI_SEN_W_BOTTOM = "cai_sen_w_bottom"    # 蔡森 W 底
    CAI_SEN_HEAD_SHOULDER = "cai_sen_head_shoulder"  # 蔡森头肩底
    BAI_DA_RIGHT_SIDE = "bai_da_right_side"  # 白大右侧
    SIGNAL_COMPOSER = "signal_composer"  # 多因子合成策略
    # 日内
    VWAP_BREAK = "vwap_break"                # 突破均价
    VOL_SURGE_STAGNATION = "vol_surge_stagnation"  # 放量滞涨
    OPENING_EIGHT = "opening_eight"          # 开盘八法


@dataclass
class SignalResult:
    """信号检测结果"""
    symbol: str
    name: str
    timestamp: datetime
    signal_type: SignalType
    strategy: SignalStrategy
    category: SignalCategory
    description: str
    confidence: int = 50          # 0-100
    price: float = 0.0
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)


# ───────────────────────────────────────────────
# 策略基类
# ───────────────────────────────────────────────

class SignalStrategyBase(ABC):
    """信号策略基类"""
    
    @property
    @abstractmethod
    def name(self) -> SignalStrategy:
        pass
    
    @property
    @abstractmethod
    def category(self) -> SignalCategory:
        pass
    
    @abstractmethod
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        """
        检测信号
        
        Args:
            df: OHLCV DataFrame（含指标列）
            symbol: 股票代码
            name: 股票名称
        
        Returns:
            SignalResult 列表（空列表表示无信号）
        """
        pass
    
    def _get_timestamp(self, df: pd.DataFrame, idx: int) -> datetime:
        """从 DataFrame 提取时间戳"""
        if "date" in df.columns:
            val = df.iloc[idx]["date"]
            if isinstance(val, str):
                return pd.to_datetime(val)
            return val if isinstance(val, datetime) else datetime.now()
        if "time" in df.columns:
            val = df.iloc[idx]["time"]
            if isinstance(val, str):
                return pd.to_datetime(val)
            return val if isinstance(val, datetime) else datetime.now()
        return datetime.now()


# ───────────────────────────────────────────────
# 日线策略
# ───────────────────────────────────────────────

class MAGoldenCrossStrategy(SignalStrategyBase):
    """均线金叉策略：MA5 上穿 MA20"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.MA_GOLDEN_CROSS
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.DAILY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 22:
            return results
        
        df = calc_ma(df, [5, 10, 20])
        
        # 检测金叉：昨天 MA5 <= MA20，今天 MA5 > MA20
        for i in range(21, len(df)):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]
            
            if (pd.notna(prev["ma5"]) and pd.notna(prev["ma20"]) and
                pd.notna(curr["ma5"]) and pd.notna(curr["ma20"])):
                
                if prev["ma5"] <= prev["ma20"] and curr["ma5"] > curr["ma20"]:
                    # 计算置信度
                    confidence = 60
                    if curr["ma10"] > curr["ma20"]:
                        confidence += 15
                    if curr["close"] > curr["ma5"]:
                        confidence += 10
                    
                    price = float(curr["close"])
                    target = price * 1.05
                    stop = min(price * 0.97, float(curr["ma20"]) * 0.98)
                    
                    ts = self._get_timestamp(df, i)
                    results.append(SignalResult(
                        symbol=symbol,
                        name=name,
                        timestamp=ts,
                        signal_type=SignalType.BUY,
                        strategy=self.name,
                        category=self.category,
                        description=f"MA5({curr['ma5']:.2f}) 上穿 MA20({curr['ma20']:.2f})",
                        confidence=min(confidence, 100),
                        price=price,
                        target_price=round(target, 2),
                        stop_loss=round(stop, 2),
                        extra_data={"ma5": curr["ma5"], "ma20": curr["ma20"]},
                    ))
        
        # 只返回最近的一个信号
        return results[-1:] if results else []


class MADeathCrossStrategy(SignalStrategyBase):
    """均线死叉策略：MA5 下穿 MA20"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.MA_DEATH_CROSS
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.DAILY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 22:
            return results
        
        df = calc_ma(df, [5, 10, 20])
        
        for i in range(21, len(df)):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]
            
            if (pd.notna(prev["ma5"]) and pd.notna(prev["ma20"]) and
                pd.notna(curr["ma5"]) and pd.notna(curr["ma20"])):
                
                if prev["ma5"] >= prev["ma20"] and curr["ma5"] < curr["ma20"]:
                    confidence = 60
                    if curr["ma10"] < curr["ma20"]:
                        confidence += 15
                    if curr["close"] < curr["ma5"]:
                        confidence += 10
                    
                    price = float(curr["close"])
                    stop = price * 1.03
                    
                    ts = self._get_timestamp(df, i)
                    results.append(SignalResult(
                        symbol=symbol,
                        name=name,
                        timestamp=ts,
                        signal_type=SignalType.SELL,
                        strategy=self.name,
                        category=self.category,
                        description=f"MA5({curr['ma5']:.2f}) 下穿 MA20({curr['ma20']:.2f})",
                        confidence=min(confidence, 100),
                        price=price,
                        stop_loss=round(stop, 2),
                    ))
        
        return results[-1:] if results else []


class VolPriceBreakoutStrategy(SignalStrategyBase):
    """量价突破策略：放量突破均线/前高"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.VOL_PRICE_BREAKOUT
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.DAILY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 25:
            return results
        
        df = calc_ma(df, [20])
        df["vol_ma20"] = df["volume"].rolling(20, min_periods=20).mean()
        df["high_20"] = df["high"].rolling(20, min_periods=20).max()
        
        for i in range(24, len(df)):
            curr = df.iloc[i]
            
            if pd.isna(curr["ma20"]) or pd.isna(curr["vol_ma20"]):
                continue
            
            # 条件：1. 收盘 > MA20；2. 成交量 > 1.5 * MA20 成交量；3. 创 20 日新高
            vol_ratio = curr["volume"] / curr["vol_ma20"] if curr["vol_ma20"] > 0 else 0
            price_break = curr["close"] > curr["ma20"] and curr["high"] >= curr["high_20"]
            vol_surge = vol_ratio > 1.5
            
            if price_break and vol_surge:
                confidence = 60 + min(int(vol_ratio * 10), 25)
                if curr["close"] > curr["open"]:
                    confidence += 10
                
                price = float(curr["close"])
                target = price * 1.08
                stop = price * 0.95
                
                ts = self._get_timestamp(df, i)
                results.append(SignalResult(
                    symbol=symbol,
                    name=name,
                    timestamp=ts,
                    signal_type=SignalType.BUY,
                    strategy=self.name,
                    category=self.category,
                    description=f"放量突破：量{vol_ratio:.1f}倍，价创20日新高",
                    confidence=min(confidence, 100),
                    price=price,
                    target_price=round(target, 2),
                    stop_loss=round(stop, 2),
                    extra_data={"vol_ratio": round(vol_ratio, 2), "high_20": curr["high_20"]},
                ))
        
        return results[-1:] if results else []


class VolPriceCollapseStrategy(SignalStrategyBase):
    """量价崩溃策略：放量跌破均线/前低"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.VOL_PRICE_COLLAPSE
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.DAILY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 25:
            return results
        
        df = calc_ma(df, [20])
        df["vol_ma20"] = df["volume"].rolling(20, min_periods=20).mean()
        df["low_20"] = df["low"].rolling(20, min_periods=20).min()
        
        for i in range(24, len(df)):
            curr = df.iloc[i]
            
            if pd.isna(curr["ma20"]) or pd.isna(curr["vol_ma20"]):
                continue
            
            vol_ratio = curr["volume"] / curr["vol_ma20"] if curr["vol_ma20"] > 0 else 0
            price_break = curr["close"] < curr["ma20"] and curr["low"] <= curr["low_20"]
            vol_surge = vol_ratio > 1.5
            
            if price_break and vol_surge:
                confidence = 60 + min(int(vol_ratio * 10), 25)
                if curr["close"] < curr["open"]:
                    confidence += 10
                
                price = float(curr["close"])
                
                ts = self._get_timestamp(df, i)
                results.append(SignalResult(
                    symbol=symbol,
                    name=name,
                    timestamp=ts,
                    signal_type=SignalType.SELL,
                    strategy=self.name,
                    category=self.category,
                    description=f"放量崩溃：量{vol_ratio:.1f}倍，跌破20日新低",
                    confidence=min(confidence, 100),
                    price=price,
                    stop_loss=round(price * 1.05, 2),
                    extra_data={"vol_ratio": round(vol_ratio, 2)},
                ))
        
        return results[-1:] if results else []


class CaiSenWBottomStrategy(SignalStrategyBase):
    """蔡森 W 底策略：双底形态"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.CAI_SEN_W_BOTTOM
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.DAILY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 30:
            return results
        
        # W 底检测：寻找两个相近低点 + 中间一个高点
        window = 30
        recent = df.tail(window)
        
        # 找局部低点（5日窗口）
        local_lows = []
        for i in range(2, len(recent) - 2):
            if (recent.iloc[i]["low"] <= recent.iloc[i-1]["low"] and
                recent.iloc[i]["low"] <= recent.iloc[i-2]["low"] and
                recent.iloc[i]["low"] <= recent.iloc[i+1]["low"] and
                recent.iloc[i]["low"] <= recent.iloc[i+2]["low"]):
                local_lows.append((i, recent.iloc[i]["low"]))
        
        if len(local_lows) >= 2:
            # 检查最后两个低点是否形成 W 底
            low1_idx, low1_val = local_lows[-2]
            low2_idx, low2_val = local_lows[-1]
            
            # 第二个低点不低于第一个的 98%
            if low2_val >= low1_val * 0.98 and low2_idx > low1_idx + 3:
                # 检查颈线（中间高点）
                mid_high = recent.iloc[low1_idx:low2_idx]["high"].max()
                last_close = recent.iloc[-1]["close"]
                
                # 突破颈线
                if last_close > mid_high * 0.98:
                    price = float(last_close)
                    target = price + (mid_high - low1_val) * 1.0  # 等幅测量
                    
                    ts = self._get_timestamp(df, len(df) - 1)
                    results.append(SignalResult(
                        symbol=symbol,
                        name=name,
                        timestamp=ts,
                        signal_type=SignalType.BUY,
                        strategy=self.name,
                        category=self.category,
                        description=f"W底形态：两低点 {low1_val:.2f}/{low2_val:.2f}，突破颈线 {mid_high:.2f}",
                        confidence=70,
                        price=price,
                        target_price=round(target, 2),
                        stop_loss=round(low2_val * 0.98, 2),
                        extra_data={"low1": low1_val, "low2": low2_val, "neckline": mid_high},
                    ))
        
        return results


class CaiSenHeadShoulderStrategy(SignalStrategyBase):
    """蔡森头肩底策略：头肩底形态"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.CAI_SEN_HEAD_SHOULDER
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.DAILY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 40:
            return results
        
        recent = df.tail(40)
        
        # 找局部低点
        local_lows = []
        for i in range(2, len(recent) - 2):
            if (recent.iloc[i]["low"] <= recent.iloc[i-1]["low"] and
                recent.iloc[i]["low"] <= recent.iloc[i-2]["low"] and
                recent.iloc[i]["low"] <= recent.iloc[i+1]["low"] and
                recent.iloc[i]["low"] <= recent.iloc[i+2]["low"]):
                local_lows.append((i, recent.iloc[i]["low"]))
        
        if len(local_lows) >= 3:
            # 检查头肩底：左肩、头、右肩
            low1_idx, low1_val = local_lows[-3]
            low2_idx, low2_val = local_lows[-2]  # head
            low3_idx, low3_val = local_lows[-1]
            
            # 头是最低点，左右肩相近且高于头
            if (low2_val < low1_val and low2_val < low3_val and
                low1_idx < low2_idx < low3_idx and
                abs(low1_val - low3_val) / max(low1_val, low3_val) < 0.05 and  # 肩高相近
                low3_idx > low2_idx + 3):
                
                # 颈线：左右肩之间的高点
                neckline = recent.iloc[low1_idx:low3_idx]["high"].max()
                last_close = recent.iloc[-1]["close"]
                
                if last_close > neckline * 0.98:
                    price = float(last_close)
                    target = price + (neckline - low2_val) * 1.0
                    
                    ts = self._get_timestamp(df, len(df) - 1)
                    results.append(SignalResult(
                        symbol=symbol,
                        name=name,
                        timestamp=ts,
                        signal_type=SignalType.BUY,
                        strategy=self.name,
                        category=self.category,
                        description=f"头肩底：左肩{low1_val:.2f} 头{low2_val:.2f} 右肩{low3_val:.2f} 颈线{neckline:.2f}",
                        confidence=75,
                        price=price,
                        target_price=round(target, 2),
                        stop_loss=round(low3_val * 0.98, 2),
                        extra_data={"left": low1_val, "head": low2_val, "right": low3_val, "neckline": neckline},
                    ))
        
        return results


class BaiDaRightSideStrategy(SignalStrategyBase):
    """白大右侧策略：趋势确认后右侧入场"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.BAI_DA_RIGHT_SIDE
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.DAILY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 30:
            return results
        
        df = calc_ma(df, [5, 10, 20])
        df = calc_macd(df)
        
        # 右侧条件：
        # 1. MA 多头排列（MA5 > MA10 > MA20）
        # 2. MACD DIF > DEA 且 BAR 为正
        # 3. 价格回调到 MA5/MA10 附近后再次向上
        
        for i in range(22, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            
            if pd.isna(curr["ma5"]) or pd.isna(curr["ma10"]) or pd.isna(curr["ma20"]):
                continue
            
            ma_bull = curr["ma5"] > curr["ma10"] > curr["ma20"]
            macd_bull = False
            if pd.notna(curr["macd_dif"]) and pd.notna(curr["macd_dea"]):
                macd_bull = curr["macd_dif"] > curr["macd_dea"] and curr["macd_bar"] > 0
            
            # 右侧：前一天回调（close <= ma5），当天再次向上（close > ma5 且 close > open）
            pullback = prev["close"] <= prev["ma5"] if pd.notna(prev["ma5"]) else False
            bounce = curr["close"] > curr["ma5"] and curr["close"] > curr["open"]
            
            if ma_bull and macd_bull and pullback and bounce:
                confidence = 70
                if curr["close"] > curr["ma10"]:
                    confidence += 15
                
                price = float(curr["close"])
                target = price * 1.06
                stop = curr["ma10"] * 0.98
                
                ts = self._get_timestamp(df, i)
                results.append(SignalResult(
                    symbol=symbol,
                    name=name,
                    timestamp=ts,
                    signal_type=SignalType.BUY,
                    strategy=self.name,
                    category=self.category,
                    description=f"右侧买入：多头回调后反弹，MA5={curr['ma5']:.2f}",
                    confidence=min(confidence, 100),
                    price=price,
                    target_price=round(target, 2),
                    stop_loss=round(stop, 2),
                ))
        
        return results[-1:] if results else []


class SignalComposerStrategy(SignalStrategyBase):
    """多因子合成策略：综合技术指标+形态+量价+支撑阻力+波浪+SuperTrend"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.SIGNAL_COMPOSER
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.DAILY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 30:
            return results
        
        try:
            from backend.services.indicators import calculate_all_indicators
            from backend.services.patterns import detect_all_patterns
            from backend.services.volume_analysis import detect_volume_nodes, calculate_support_resistance
            from backend.services.signal_composer import compose_signal
            
            # 计算指标
            df_ind = calculate_all_indicators(df)
            latest_indicators = {}
            if len(df_ind) > 0:
                latest = df_ind.iloc[-1]
                for col in ["ma5", "ma10", "ma20", "ma60", "macd_dif", "macd_dea", "macd_bar",
                            "kdj_k", "kdj_d", "kdj_j", "rsi6", "rsi12", "rsi24",
                            "boll_mid", "boll_up", "boll_down", "obv", "dmi_pdi", "dmi_mdi", "dmi_adx"]:
                    if col in latest.index:
                        latest_indicators[col] = float(latest[col]) if pd.notna(latest[col]) else None
                latest_indicators["close"] = float(latest["close"]) if "close" in latest.index else None
            
            # 形态识别
            patterns = detect_all_patterns(df)
            
            # 量价分析
            volume_nodes = detect_volume_nodes(df)
            
            # 支撑阻力
            sr = calculate_support_resistance(df)
            
            # 合成信号
            signal = compose_signal(
                symbol=symbol,
                df=df,
                indicators=latest_indicators,
                patterns=patterns,
                volume_analysis=volume_nodes,
                support_resistance=sr,
                period="daily",
            )
            
            if signal.type != "HOLD":
                st = signal.type
                stype = SignalType.BUY if st == "BUY" else SignalType.SELL
                results.append(SignalResult(
                    symbol=symbol,
                    name=name,
                    timestamp=datetime.now(),
                    signal_type=stype,
                    strategy=self.name,
                    category=self.category,
                    description=signal.rationale,
                    confidence=min(int(signal.confidence * 100), 100),
                    price=round(signal.entry_price, 2),
                    target_price=round(signal.take_profit, 2) if signal.take_profit > 0 else None,
                    stop_loss=round(signal.stop_loss, 2) if signal.stop_loss > 0 else None,
                ))
        except Exception as e:
            import warnings
            warnings.warn(f"SignalComposerStrategy failed for {symbol}: {e}")
        
        return results


# ───────────────────────────────────────────────
# 日内策略
# ───────────────────────────────────────────────

class VWAPBreakStrategy(SignalStrategyBase):
    """VWAP 突破策略：价格突破成交量加权均价"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.VWAP_BREAK
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.INTRADAY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 10:
            return results
        
        # 计算 VWAP：累计 (price * volume) / 累计 volume
        # 使用 close 作为价格代表
        df = df.copy()
        df["cum_vol"] = df["volume"].cumsum()
        df["cum_pv"] = (df["close"] * df["volume"]).cumsum()
        df["vwap"] = df["cum_pv"] / df["cum_vol"].replace(0, np.nan)
        
        for i in range(5, len(df)):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]
            
            if pd.isna(curr["vwap"]):
                continue
            
            # 突破：前一分钟 <= VWAP，当前 > VWAP，且放量
            prev_below = prev["close"] <= prev["vwap"] if pd.notna(prev["vwap"]) else True
            curr_above = curr["close"] > curr["vwap"]
            vol_increase = curr["volume"] > prev["volume"] * 1.2 if prev["volume"] > 0 else False
            
            if prev_below and curr_above and vol_increase:
                confidence = 65
                if curr["close"] > curr["open"]:
                    confidence += 15
                
                price = float(curr["close"])
                
                ts = self._get_timestamp(df, i)
                results.append(SignalResult(
                    symbol=symbol,
                    name=name,
                    timestamp=ts,
                    signal_type=SignalType.BUY,
                    strategy=self.name,
                    category=self.category,
                    description=f"突破均价：价格 {price:.2f} 上穿 VWAP {curr['vwap']:.2f}",
                    confidence=min(confidence, 100),
                    price=price,
                    extra_data={"vwap": round(curr["vwap"], 2)},
                ))
        
        return results[-1:] if results else []


class VolSurgeStagnationStrategy(SignalStrategyBase):
    """放量滞涨策略：成交量放大但价格涨幅小（出货信号）"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.VOL_SURGE_STAGNATION
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.INTRADAY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 10:
            return results
        
        df = df.copy()
        df["vol_ma5"] = df["volume"].rolling(5, min_periods=5).mean()
        
        for i in range(5, len(df)):
            curr = df.iloc[i]
            
            if pd.isna(curr["vol_ma5"]) or curr["vol_ma5"] <= 0:
                continue
            
            vol_ratio = curr["volume"] / curr["vol_ma5"]
            price_change = (curr["close"] - curr["open"]) / curr["open"] * 100 if curr["open"] > 0 else 0
            
            # 放量滞涨：量放大 2 倍以上，但价格涨幅 < 1%
            if vol_ratio > 2.0 and abs(price_change) < 1.0:
                confidence = 60 + min(int(vol_ratio * 5), 30)
                
                signal_type = SignalType.SELL if price_change < 0 else SignalType.WATCH
                
                price = float(curr["close"])
                
                ts = self._get_timestamp(df, i)
                results.append(SignalResult(
                    symbol=symbol,
                    name=name,
                    timestamp=ts,
                    signal_type=signal_type,
                    strategy=self.name,
                    category=self.category,
                    description=f"放量滞涨：量{vol_ratio:.1f}倍，价格仅{price_change:.2f}%",
                    confidence=min(confidence, 100),
                    price=price,
                    extra_data={"vol_ratio": round(vol_ratio, 2), "price_change": round(price_change, 2)},
                ))
        
        return results[-1:] if results else []


class OpeningEightStrategy(SignalStrategyBase):
    """开盘八法策略：根据开盘前 N 根 K 线判断当日走势"""
    
    @property
    def name(self) -> SignalStrategy:
        return SignalStrategy.OPENING_EIGHT
    
    @property
    def category(self) -> SignalCategory:
        return SignalCategory.INTRADAY
    
    def detect(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> List[SignalResult]:
        results = []
        if len(df) < 5:
            return results
        
        # 取开盘前 5 根 K 线
        opening = df.head(5)
        
        up_count = 0
        down_count = 0
        for _, row in opening.iterrows():
            if row["close"] > row["open"]:
                up_count += 1
            elif row["close"] < row["open"]:
                down_count += 1
        
        # 开盘八法简化：三↑为强，三↓为弱，十字星为震荡
        if up_count >= 4:
            price = float(df.iloc[4]["close"])
            ts = self._get_timestamp(df, 4)
            results.append(SignalResult(
                symbol=symbol,
                name=name,
                timestamp=ts,
                signal_type=SignalType.BUY,
                strategy=self.name,
                category=self.category,
                description=f"开盘强势：前5分钟 {up_count} 阳 {down_count} 阴",
                confidence=65,
                price=price,
            ))
        elif down_count >= 4:
            price = float(df.iloc[4]["close"])
            ts = self._get_timestamp(df, 4)
            results.append(SignalResult(
                symbol=symbol,
                name=name,
                timestamp=ts,
                signal_type=SignalType.SELL,
                strategy=self.name,
                category=self.category,
                description=f"开盘弱势：前5分钟 {up_count} 阳 {down_count} 阴",
                confidence=65,
                price=price,
            ))
        elif up_count == 3 and down_count == 2:
            # 三阳开泰，但需看是否带量
            avg_vol = df.head(5)["volume"].mean()
            last_vol = df.iloc[4]["volume"]
            if last_vol > avg_vol * 1.3:
                price = float(df.iloc[4]["close"])
                ts = self._get_timestamp(df, 4)
                results.append(SignalResult(
                    symbol=symbol,
                    name=name,
                    timestamp=ts,
                    signal_type=SignalType.BUY,
                    strategy=self.name,
                    category=self.category,
                    description=f"三阳开泰带量：前5分钟 3阳2阴，量增{last_vol/avg_vol:.1f}倍",
                    confidence=70,
                    price=price,
                ))
        
        return results


# ───────────────────────────────────────────────
# 信号引擎主类
# ───────────────────────────────────────────────

DAILY_STRATEGIES: List[SignalStrategyBase] = [
    MAGoldenCrossStrategy(),
    MADeathCrossStrategy(),
    VolPriceBreakoutStrategy(),
    VolPriceCollapseStrategy(),
    CaiSenWBottomStrategy(),
    CaiSenHeadShoulderStrategy(),
    BaiDaRightSideStrategy(),
    SignalComposerStrategy(),
]

INTRADAY_STRATEGIES: List[SignalStrategyBase] = [
    VWAPBreakStrategy(),
    VolSurgeStagnationStrategy(),
    OpeningEightStrategy(),
]

ALL_STRATEGIES: List[SignalStrategyBase] = DAILY_STRATEGIES + INTRADAY_STRATEGIES


class SignalEngine:
    """信号引擎主类"""
    
    def __init__(self, data_provider=None):
        self.data_provider = data_provider
        self.daily_strategies = DAILY_STRATEGIES
        self.intraday_strategies = INTRADAY_STRATEGIES
    
    def detect_daily(self, df: pd.DataFrame, symbol: str = "", name: str = "",
                     strategies: Optional[List[SignalStrategy]] = None) -> List[SignalResult]:
        """
        检测日线信号
        
        Args:
            df: OHLCV DataFrame
            symbol: 股票代码
            name: 股票名称
            strategies: 指定策略列表（None=全部）
        
        Returns:
            SignalResult 列表
        """
        results = []
        for strategy in self.daily_strategies:
            if strategies is None or strategy.name in strategies:
                try:
                    sigs = strategy.detect(df, symbol, name)
                    results.extend(sigs)
                except Exception as e:
                    warnings.warn(f"Strategy {strategy.name} failed for {symbol}: {e}")
        return results
    
    def detect_intraday(self, df: pd.DataFrame, symbol: str = "", name: str = "",
                        strategies: Optional[List[SignalStrategy]] = None) -> List[SignalResult]:
        """检测日内信号"""
        results = []
        for strategy in self.intraday_strategies:
            if strategies is None or strategy.name in strategies:
                try:
                    sigs = strategy.detect(df, symbol, name)
                    results.extend(sigs)
                except Exception as e:
                    warnings.warn(f"Strategy {strategy.name} failed for {symbol}: {e}")
        return results
    
    def scan_daily(self, symbols: List[Tuple[str, str]], 
                   strategies: Optional[List[SignalStrategy]] = None) -> List[SignalResult]:
        """
        批量扫描日线信号
        
        Args:
            symbols: [(symbol, name), ...]
            strategies: 指定策略列表
        
        Returns:
            所有信号列表
        """
        if self.data_provider is None:
            raise ValueError("Data provider required for scanning")
        
        all_results = []
        for symbol, name in symbols:
            df = self.data_provider.get_kline_latest(symbol, n=60, period="daily")
            if df is not None and len(df) >= 30:
                results = self.detect_daily(df, symbol, name, strategies)
                all_results.extend(results)
        
        return all_results
    
    def scan_intraday(self, symbol: str, name: str = "",
                      strategies: Optional[List[SignalStrategy]] = None) -> List[SignalResult]:
        """
        扫描日内信号（需要分钟级数据）
        
        Args:
            symbol: 股票代码
            name: 股票名称
            strategies: 指定策略列表
        
        Returns:
            日内信号列表
        """
        if self.data_provider is None:
            raise ValueError("Data provider required for scanning")
        
        # 尝试获取分钟数据
        df = self.data_provider.fetch_ohlcv(symbol, period="minute")
        if df is not None and len(df) >= 10:
            return self.detect_intraday(df, symbol, name, strategies)
        
        return []
    
    def get_strategy_list(self) -> List[Dict[str, str]]:
        """获取所有策略列表"""
        return [
            {
                "name": s.name.value,
                "category": s.category.value,
                "display_name": self._get_display_name(s.name),
            }
            for s in ALL_STRATEGIES
        ]
    
    def _get_display_name(self, strategy: SignalStrategy) -> str:
        """获取策略中文名"""
        names = {
            SignalStrategy.MA_GOLDEN_CROSS: "均线金叉",
            SignalStrategy.MA_DEATH_CROSS: "均线死叉",
            SignalStrategy.VOL_PRICE_BREAKOUT: "量价突破",
            SignalStrategy.VOL_PRICE_COLLAPSE: "量价崩溃",
            SignalStrategy.CAI_SEN_W_BOTTOM: "蔡森 W 底",
            SignalStrategy.CAI_SEN_HEAD_SHOULDER: "蔡森头肩底",
            SignalStrategy.BAI_DA_RIGHT_SIDE: "白大右侧",
            SignalStrategy.SIGNAL_COMPOSER: "多因子合成",
            SignalStrategy.VWAP_BREAK: "VWAP 突破",
            SignalStrategy.VOL_SURGE_STAGNATION: "放量滞涨",
            SignalStrategy.OPENING_EIGHT: "开盘八法",
        }
        return names.get(strategy, strategy.value)


# ───────────────────────────────────────────────
# 便捷函数
# ───────────────────────────────────────────────

def get_signal_engine(data_provider=None) -> SignalEngine:
    """获取信号引擎实例"""
    return SignalEngine(data_provider=data_provider)


# ───────────────────────────────────────────────
# 测试
# ───────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    
    from backend.services.data_provider import DataProviderService
    
    print("=== Signal Engine Test ===")
    
    # 1. 测试策略列表
    print("\n[1] Strategy List")
    engine = get_signal_engine()
    strategies = engine.get_strategy_list()
    for s in strategies:
        print(f"  {s['name']} ({s['category']}) - {s['display_name']}")
    print(f"  Total: {len(strategies)} strategies")
    
    # 2. 测试数据（使用真实数据，禁用合成数据 per 系统政策）
    print("\n[2] Real Data Test (synthetic data disabled per policy)")
    svc = DataProviderService()
    df = svc.get_kline_latest("000001", n=60)
    if df is None or len(df) == 0:
        print("ERROR: No real data available. Cannot proceed with synthetic data (system policy: no fake data).")
        sys.exit(1)
    test_symbol = "000001"
    test_name = "平安银行"
    
    # 2.1 均线金叉测试
    print("\n[2.1] MA Golden Cross")
    ma_strat = MAGoldenCrossStrategy()
    sigs = ma_strat.detect(df, test_symbol, test_name)
    print(f"  Signals found: {len(sigs)}")
    for s in sigs:
        print(f"  {s.timestamp.strftime('%Y-%m-%d')} {s.signal_type.value} {s.description} conf={s.confidence}")
    
    # 2.2 量价突破测试
    print("\n[2.2] Vol-Price Breakout")
    vol_strat = VolPriceBreakoutStrategy()
    sigs = vol_strat.detect(df, test_symbol, test_name)
    print(f"  Signals found: {len(sigs)}")
    for s in sigs:
        print(f"  {s.timestamp.strftime('%Y-%m-%d')} {s.signal_type.value} {s.description} conf={s.confidence}")
    
    # 2.3 白大右侧测试
    print("\n[2.3] Bai Da Right Side")
    bai_strat = BaiDaRightSideStrategy()
    sigs = bai_strat.detect(df, test_symbol, test_name)
    print(f"  Signals found: {len(sigs)}")
    for s in sigs:
        print(f"  {s.timestamp.strftime('%Y-%m-%d')} {s.signal_type.value} {s.description} conf={s.confidence}")
    
    # 2.4 全策略检测
    print("\n[2.4] Full Daily Detection")
    all_sigs = engine.detect_daily(df, test_symbol, test_name)
    print(f"  Total signals: {len(all_sigs)}")
    for s in all_sigs:
        print(f"  [{s.strategy.value}] {s.timestamp.strftime('%Y-%m-%d')} {s.signal_type.value} conf={s.confidence}")
    
    # 3. 日内测试（使用真实分钟数据，禁用合成数据）
    print("\n[3] Intraday Test (synthetic data disabled)")
    df_min = svc.get_kline_latest("000001", n=240, period="1m")
    if df_min is not None and len(df_min) >= 30:
        intraday_sigs = engine.detect_intraday(df_min, test_symbol, test_name)
        print(f"  Intraday signals: {len(intraday_sigs)}")
        for s in intraday_sigs:
            print(f"  [{s.strategy.value}] {s.timestamp} {s.signal_type.value} conf={s.confidence}")
    else:
        print("  Skipped: real minute data not available")
    
    # 4. 真实数据测试（如果可用）
    print("\n[4] Real Data Test")
    svc = DataProviderService()
    health = svc.health_check()
    if health.get("tdxdir_exists") or health.get("realtime_available"):
        df_real = svc.get_kline_latest("000001", n=60)
        if df_real is not None and len(df_real) >= 30:
            real_sigs = engine.detect_daily(df_real, "000001", "平安银行")
            print(f"  Real signals for 000001: {len(real_sigs)}")
            for s in real_sigs:
                print(f"  [{s.strategy.value}] {s.timestamp.strftime('%Y-%m-%d')} {s.signal_type.value} {s.description}")
        else:
            print("  No real data available")
    else:
        print("  No data source available, skipping real data test")
    
    # 5. Edge case: 空数据
    print("\n[5] Edge case - empty DataFrame")
    df_empty = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
    sigs = engine.detect_daily(df_empty, "EMPTY", "空")
    assert len(sigs) == 0
    print("  Empty data handled: PASSED")
    
    # 6. Edge case: 数据不足
    print("\n[6] Edge case - insufficient data")
    df_small = pd.DataFrame({
        "open": [10, 11, 12], "high": [11, 12, 13], "low": [9, 10, 11],
        "close": [10.5, 11.5, 12.5], "volume": [1000, 2000, 3000],
    })
    sigs = engine.detect_daily(df_small, "SMALL", "小")
    assert len(sigs) == 0
    print("  Insufficient data handled: PASSED")
    
    print("\n=== All Signal Engine Tests PASSED ===")
