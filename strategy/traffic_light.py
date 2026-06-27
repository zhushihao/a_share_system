"""
交通灯引擎 - 候选池分类 + 信号灯判定 + 持仓管理
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime

from data.pattern_recognition import Pattern
from data.sector_calculation import SectorResult


@dataclass
class TrafficLightResult:
    code: str
    name: str
    signal: str                    # 绿灯/黄灯/红灯
    category: str                  # 趋势池/观察池/风险池
    
    # 原因
    reasons: List[str] = field(default_factory=list)
    
    # 交易建议
    action: str = ""
    position_size: float = 0.0
    
    # 风险参数
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    risk_rate: Optional[float] = None
    reward_rate: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "name": self.name,
            "signal": self.signal,
            "category": self.category,
            "reasons": self.reasons,
            "action": self.action,
            "position_size": self.position_size,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "risk_rate": self.risk_rate,
            "reward_rate": self.reward_rate,
        }


def calculate_ma(df: pd.DataFrame, window: int) -> pd.Series:
    """计算移动平均线"""
    return df["close"].rolling(window=window).mean()


def calculate_ma_slope(df: pd.DataFrame, window: int) -> float:
    """计算MA斜率（百分比）"""
    ma = calculate_ma(df, window)
    if len(ma) < 2:
        return 0.0
    return (ma.iloc[-1] - ma.iloc[-2]) / ma.iloc[-2] if ma.iloc[-2] != 0 else 0.0


def check_trend_rules(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    检查第二章 7项趋势规则
    返回: (是否全部满足, 不满足的规则列表)
    """
    violations = []
    
    # 规则1: 收盘价 > 20日均线，20日均线斜率 > 0
    ma20 = calculate_ma(df, 20)
    if df["close"].iloc[-1] <= ma20.iloc[-1]:
        violations.append("R1: 收盘价未站上20日均线")
    ma20_slope = calculate_ma_slope(df, 20)
    if ma20_slope <= 0:
        violations.append("R1: 20日均线斜率<=0")
    
    # 规则2: 创20日新高
    high_20d = df["high"].iloc[-20:].max() if len(df) >= 20 else df["high"].max()
    if df["high"].iloc[-1] < high_20d * 0.99 and df["close"].iloc[-1] < high_20d * 0.99:
        violations.append("R2: 未创20日新高")
    
    # 规则4: 成交量验证
    vol_20d_avg = df["volume"].iloc[-20:].mean()
    if vol_20d_avg > 0 and df["volume"].iloc[-1] < vol_20d_avg * 1.2:
        vol_5d_avg = df["volume"].iloc[-5:].mean()
        if vol_5d_avg < vol_20d_avg * 1.1:
            violations.append("R4: 成交量未放量")
    
    # 规则6: 非ST，股价>2元
    if df["close"].iloc[-1] <= 2:
        violations.append("R6: 股价<=2元")
    
    return len(violations) == 0, violations


def classify_candidate_pool(
    df: pd.DataFrame, 
    code: str, 
    name: str,
    pattern: Optional[Pattern],
    sector_result: Optional[SectorResult],
    market_regime: str
) -> TrafficLightResult:
    """
    候选池分类：趋势池/观察池/风险池
    """
    result = TrafficLightResult(code=code, name=name, signal="", category="", reasons=[])
    
    if len(df) < 60:
        result.category = "观察池"
        result.reasons.append("数据不足60天")
        result.signal = "黄灯"
        result.action = "观察"
        return result
    
    # 检查趋势规则
    trend_ok, violations = check_trend_rules(df)
    
    # 检查风险信号
    risk_signals = []
    
    # 跌破20日线
    ma20 = calculate_ma(df, 20)
    if df["close"].iloc[-1] < ma20.iloc[-1] * 0.97:
        risk_signals.append("跌破20日均线3%")
    
    # 异常大量不涨
    vol_20d_avg = df["volume"].iloc[-20:].mean()
    if vol_20d_avg > 0 and df["volume"].iloc[-1] >= vol_20d_avg * 3.0 and df["pct_change"].iloc[-1] < 3:
        risk_signals.append("异常大量不涨")
    
    # 头部型态
    if pattern and pattern.direction == "空头" and pattern.status in ["已跌破", "已失效"]:
        risk_signals.append(f"头部型态: {pattern.pattern_type}")
    
    # 分类逻辑
    if risk_signals:
        result.category = "风险池"
        result.signal = "红灯"
        result.reasons = risk_signals
        result.action = "禁止买入/止损"
        return result
    
    if trend_ok and pattern and pattern.direction == "多头" and pattern.status in ["已突破", "待突破"]:
        # 检查板块
        if sector_result and sector_result.lifecycle in ["发酵期", "高潮期"] and sector_result.rule_3plus2:
            # 检查市场状态
            if market_regime in ["强趋势", "结构性趋势"]:
                # 检查风险报酬比
                if pattern.breakout_price and pattern.target_1:
                    entry = pattern.breakout_price
                    stop = entry * 0.93
                    target = pattern.target_1
                    risk_rate = (entry - stop) / entry
                    reward_rate = (target - entry) / entry
                    
                    if risk_rate <= 0.07 and reward_rate >= 0.20 and risk_rate / reward_rate <= 1/3:
                        result.category = "趋势池"
                        result.signal = "绿灯"
                        result.reasons = ["全部趋势规则满足", f"型态: {pattern.pattern_type}", "板块确认"]
                        result.action = "可买入"
                        result.entry_price = entry
                        result.stop_loss = stop
                        result.target_1 = target
                        result.target_2 = pattern.target_2
                        result.risk_rate = risk_rate
                        result.reward_rate = reward_rate
                        
                        # 动态仓位
                        if market_regime == "强趋势":
                            result.position_size = 0.10
                        elif market_regime == "结构性趋势":
                            result.position_size = 0.05
                        else:
                            result.position_size = 0.03
                        
                        return result
    
    # 观察池
    result.category = "观察池"
    result.signal = "黄灯"
    result.reasons = violations if violations else ["趋势条件未完全满足"]
    if pattern:
        result.reasons.append(f"型态: {pattern.pattern_type} ({pattern.status})")
    if sector_result:
        result.reasons.append(f"板块: {sector_result.lifecycle}")
    result.action = "跟踪观察，不买入"
    return result


def evaluate_position_signal(
    df: pd.DataFrame,
    code: str,
    name: str,
    entry_price: float,
    current_position_pct: float,
    pattern: Optional[Pattern],
    sector_result: Optional[SectorResult],
    market_regime: str
) -> TrafficLightResult:
    """
    持仓信号灯判定
    """
    result = TrafficLightResult(code=code, name=name, signal="绿灯", category="持仓", reasons=[])
    current_price = df["close"].iloc[-1]
    pnl = (current_price - entry_price) / entry_price
    
    # 红灯检查
    red_signals = []
    
    # RED1: 跌破止损
    stop_loss = entry_price * 0.93
    if current_price < stop_loss:
        red_signals.append(f"跌破止损({stop_loss:.2f})")
    
    # RED2: 假突破
    if pattern and pattern.pattern_type == "假突破" and pattern.status == "已失效":
        red_signals.append("假突破")
    
    # RED3: 板块衰退
    if sector_result and sector_result.lifecycle == "衰退期":
        red_signals.append("板块衰退")
    
    # RED7: 满足区背离
    if pattern and pattern.target_1:
        if current_price >= pattern.target_1 * 0.95:
            # 检查5日不创新高
            if len(df) >= 5:
                recent_high = df["high"].iloc[-5:].max()
                if recent_high <= current_price * 1.01:  # 基本没创新高
                    red_signals.append("满足区背离")
    
    # RED10: 市场状态风险
    if market_regime == "风险市":
        red_signals.append("市场状态风险市")
    
    if red_signals:
        result.signal = "红灯"
        result.reasons = red_signals
        result.action = "清仓/止损"
        return result
    
    # 黄灯检查
    yellow_signals = []
    
    # Y1: 接近满足点
    if pattern and pattern.target_1:
        if current_price >= pattern.target_1 * 0.90:
            yellow_signals.append(f"接近满足点({pattern.target_1:.2f})")
    
    # Y2: 异常大量
    vol_20d_avg = df["volume"].iloc[-20:].mean()
    if vol_20d_avg > 0 and df["volume"].iloc[-1] >= vol_20d_avg * 3.0 and df["pct_change"].iloc[-1] < 3:
        yellow_signals.append("异常大量不涨")
    
    # Y8: 市场状态降级
    if market_regime == "震荡":
        yellow_signals.append("市场状态震荡")
    
    if yellow_signals:
        result.signal = "黄灯"
        result.reasons = yellow_signals
        result.action = "减仓"
        return result
    
    # 绿灯
    result.reasons = [f"浮盈{pnl*100:.1f}%", "趋势健康"]
    if pattern and pattern.target_1:
        result.reasons.append(f"目标1: {pattern.target_1:.2f}")
    result.action = "持有"
    
    return result


def run_traffic_light_system(
    stock_data: Dict[str, pd.DataFrame],
    stock_patterns: Dict[str, List[Pattern]],
    sector_results: List[SectorResult],
    market_regime: str,
    current_positions: Optional[Dict] = None
) -> Dict[str, List[TrafficLightResult]]:
    """
    运行完整的交通灯系统
    返回: {"趋势池": [...], "观察池": [...], "风险池": [...], "持仓": [...]}
    """
    # 构建板块映射
    sector_map = {s.sector_name: s for s in sector_results}
    
    trend_pool = []
    watch_pool = []
    risk_pool = []
    position_signals = []
    
    for code, df in stock_data.items():
        if len(df) < 20:
            continue
        
        name = code  # 简化
        
        # 获取型态
        patterns = stock_patterns.get(code, [])
        best_pattern = max(patterns, key=lambda p: p.confidence) if patterns else None
        
        # 获取板块（简化：假设板块名称可以从某处获取）
        sector_result = None
        
        # 候选池分类
        result = classify_candidate_pool(df, code, name, best_pattern, sector_result, market_regime)
        
        if result.category == "趋势池":
            trend_pool.append(result)
        elif result.category == "风险池":
            risk_pool.append(result)
        else:
            watch_pool.append(result)
        
        # 持仓信号灯
        if current_positions and code in current_positions:
            pos = current_positions[code]
            pos_signal = evaluate_position_signal(
                df, code, name, pos["entry_price"], pos["position_pct"],
                best_pattern, sector_result, market_regime
            )
            position_signals.append(pos_signal)
    
    return {
        "趋势池": trend_pool,
        "观察池": watch_pool,
        "风险池": risk_pool,
        "持仓": position_signals,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")
    from utils.data_fetcher import fetch_daily_kline
    from data.pattern_recognition import scan_patterns
    
    print("Testing traffic light system...")
    df = fetch_daily_kline("000001", "20240601", "20250619")
    patterns = scan_patterns(df, "000001", "平安银行", min_history=80)
    best_pattern = max(patterns, key=lambda p: p.confidence) if patterns else None
    
    result = classify_candidate_pool(df, "000001", "平安银行", best_pattern, None, "结构性趋势")
    print(f"\nResult: {result.to_dict()}")
