# -*- coding: utf-8 -*-
"""
Backtest Engine - 回测引擎

事件驱动、逐日遍历回测框架。

支持的预设策略：
  - 双均线 (dual_ma): MA5 上穿/下穿 MA20
  - MACD (macd): MACD 金叉/死叉
  - KD (kd): K 上穿/下穿 D
  - 蔡森 W底 (cai_sen_w): 简化W底形态
  - 白大右侧 (bai_da_right): MA 多头 + MACD 金叉 + 回调反弹
  - 多因子合成 (signal_composer): 指标+形态+量价+支撑阻力合成信号

自定义策略：
  - 用户输入 JSON 声明式 DSL（无代码执行）
  - DSL 由 rules / condition / action 组成，后端解释执行
  - 支持的数值节点：col / param / const；支持 lag 偏移
  - 支持的条件：cross_up / cross_down / gt / gte / lt / lte / eq / and / or / not / in_range

绩效指标：
  - 总收益率、年化收益率、最大回撤、夏普比率、胜率、盈亏比
  - 权益曲线、月度收益矩阵、交易记录
"""

import sys
import os
import json
import math
import operator
import traceback
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field, asdict

from backend.services.indicators import calculate_all_indicators

# 尝试导入 DataProviderService，如果失败则提供简单 fallback
try:
    from backend.services.data_provider import get_data_provider_service
except ImportError:
    get_data_provider_service = None


# ───────────────────────────────────────────────
# 数据模型
# ───────────────────────────────────────────────

@dataclass
class TradeRecord:
    """交易记录"""
    date: str
    action: str          # BUY / SELL
    symbol: str
    price: float
    size: int
    amount: float        # 成交金额（含手续费）
    commission: float
    reason: str = ""
    cash_after: float = 0.0
    position_after: int = 0


@dataclass
class DailySnapshot:
    """每日权益快照"""
    date: str
    cash: float
    position: int
    close_price: float
    market_value: float
    total_value: float
    equity_return: float = 0.0


@dataclass
class BacktestResult:
    """回测结果"""
    strategy_name: str
    symbols: List[str]
    start_date: str
    end_date: str
    initial_cash: float
    final_value: float
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    profit_loss_ratio: float
    total_trades: int
    win_trades: int
    loss_trades: int
    avg_holding_days: float
    equity_curve: List[DailySnapshot] = field(default_factory=list)
    trades: List[TradeRecord] = field(default_factory=list)
    monthly_returns: Dict[str, float] = field(default_factory=dict)
    error: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)


# ───────────────────────────────────────────────
# 预设策略
# ───────────────────────────────────────────────

def _dual_ma_strategy(df: pd.DataFrame, position: int, cash: float, params: Dict) -> Dict:
    """
    双均线策略
    参数：short_ma (5), long_ma (20)
    买入：MA5 上穿 MA20
    卖出：MA5 下穿 MA20
    """
    short = params.get("short_ma", 5)
    long = params.get("long_ma", 20)
    if len(df) < long + 1:
        return {"action": "HOLD", "reason": "数据不足"}
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    ma_s = curr.get(f"ma{short}")
    ma_l = curr.get(f"ma{long}")
    prev_ma_s = prev.get(f"ma{short}")
    prev_ma_l = prev.get(f"ma{long}")
    
    if ma_s is None or ma_l is None or prev_ma_s is None or prev_ma_l is None:
        return {"action": "HOLD", "reason": "指标缺失"}
    
    # 金叉买入
    if prev_ma_s <= prev_ma_l and ma_s > ma_l and position == 0 and cash > 0:
        price = curr["close"]
        size = int(cash * 0.99 / price)
        if size > 0:
            return {"action": "BUY", "price": price, "size": size, "reason": f"MA{short}上穿MA{long}"}
    
    # 死叉卖出
    if prev_ma_s >= prev_ma_l and ma_s < ma_l and position > 0:
        price = curr["close"]
        return {"action": "SELL", "price": price, "size": position, "reason": f"MA{short}下穿MA{long}"}
    
    return {"action": "HOLD", "reason": "无信号"}


def _macd_strategy(df: pd.DataFrame, position: int, cash: float, params: Dict) -> Dict:
    """
    MACD策略
    买入：MACD 金叉（DIF 上穿 DEA）
    卖出：MACD 死叉（DIF 下穿 DEA）
    """
    if len(df) < 2:
        return {"action": "HOLD", "reason": "数据不足"}
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    if not all(k in df.columns for k in ["macd_dif", "macd_dea"]):
        return {"action": "HOLD", "reason": "指标缺失"}
    
    prev_dif = prev["macd_dif"]
    prev_dea = prev["macd_dea"]
    curr_dif = curr["macd_dif"]
    curr_dea = curr["macd_dea"]
    
    # 金叉买入
    if prev_dif <= prev_dea and curr_dif > curr_dea and position == 0 and cash > 0:
        price = curr["close"]
        size = int(cash * 0.99 / price)
        if size > 0:
            return {"action": "BUY", "price": price, "size": size, "reason": "MACD金叉"}
    
    # 死叉卖出
    if prev_dif >= prev_dea and curr_dif < curr_dea and position > 0:
        price = curr["close"]
        return {"action": "SELL", "price": price, "size": position, "reason": "MACD死叉"}
    
    return {"action": "HOLD", "reason": "无信号"}


def _kd_strategy(df: pd.DataFrame, position: int, cash: float, params: Dict) -> Dict:
    """
    KD策略
    买入：K 上穿 D（金叉）且 K < 80
    卖出：K 下穿 D（死叉）或 K > 80
    """
    if len(df) < 2:
        return {"action": "HOLD", "reason": "数据不足"}
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    if not all(k in df.columns for k in ["kdj_k", "kdj_d"]):
        return {"action": "HOLD", "reason": "指标缺失"}
    
    prev_k = prev["kdj_k"]
    prev_d = prev["kdj_d"]
    curr_k = curr["kdj_k"]
    curr_d = curr["kdj_d"]
    
    # 金叉买入（K 在低位上穿 D）
    if prev_k <= prev_d and curr_k > curr_d and curr_k < 80 and position == 0 and cash > 0:
        price = curr["close"]
        size = int(cash * 0.99 / price)
        if size > 0:
            return {"action": "BUY", "price": price, "size": size, "reason": "KD金叉"}
    
    # 死叉卖出（K 在高位下穿 D）
    if prev_k >= prev_d and curr_k < curr_d and position > 0:
        price = curr["close"]
        return {"action": "SELL", "price": price, "size": position, "reason": "KD死叉"}
    
    return {"action": "HOLD", "reason": "无信号"}


def _cai_sen_strategy(df: pd.DataFrame, position: int, cash: float, params: Dict) -> Dict:
    """
    蔡森简化策略（W底 / 颈线突破）
    参数：lookback (20)
    买入：近期两个低点 + 突破颈线
    """
    lookback = params.get("lookback", 20)
    if len(df) < lookback + 5:
        return {"action": "HOLD", "reason": "数据不足"}
    
    recent = df.iloc[-lookback:]
    
    # 找局部低点（简化：最近20日最低的两个点）
    lows = recent["low"].values
    # 找到最近两个明显低点（间隔至少5日）
    min_idx = np.argmin(lows)
    min_val = lows[min_idx]
    
    # 第二个低点（排除 min_idx 附近）
    mask = np.ones(len(lows), dtype=bool)
    mask[max(0, min_idx-3):min(len(lows), min_idx+4)] = False
    if mask.sum() == 0:
        return {"action": "HOLD", "reason": "无形态"}
    
    second_min_idx = np.argmin(lows[mask])
    second_min_val = lows[mask][second_min_idx]
    
    # 简化：两底接近（差 < 5%），且当前价格突破颈线（两底之间的高点）
    if abs(min_val - second_min_val) / max(min_val, second_min_val) < 0.05:
        # 找颈线（两底之间的高点）
        between_start = min(min_idx, np.where(mask)[0][second_min_idx])
        between_end = max(min_idx, np.where(mask)[0][second_min_idx])
        if between_end > between_start:
            neck = np.max(lows[between_start:between_end+1])
            curr_price = df.iloc[-1]["close"]
            if curr_price > neck * 1.02 and position == 0 and cash > 0:
                price = curr_price
                size = int(cash * 0.99 / price)
                if size > 0:
                    return {"action": "BUY", "price": price, "size": size, "reason": "W底颈线突破"}
    
    return {"action": "HOLD", "reason": "无形态"}


def _bai_da_strategy(df: pd.DataFrame, position: int, cash: float, params: Dict) -> Dict:
    """
    白大右侧策略
    参数：short_ma (5), long_ma (20)
    买入：MA 多头排列 + MACD 金叉 + 回调不创新低
    卖出：MA 空头排列或 MACD 死叉
    """
    if len(df) < 30:
        return {"action": "HOLD", "reason": "数据不足"}
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 检查指标
    if not all(k in df.columns for k in ["ma5", "ma10", "ma20", "macd_dif", "macd_dea"]):
        return {"action": "HOLD", "reason": "指标缺失"}
    
    # MA 多头排列
    ma_bull = curr["ma5"] > curr["ma10"] > curr["ma20"]
    # MACD 金叉
    macd_golden = prev["macd_dif"] <= prev["macd_dea"] and curr["macd_dif"] > curr["macd_dea"]
    # 回调不创新低（今日低点 >= 昨日低点）
    pullback = curr["low"] >= prev["low"] * 0.99
    
    if ma_bull and macd_golden and pullback and position == 0 and cash > 0:
        price = curr["close"]
        size = int(cash * 0.99 / price)
        if size > 0:
            return {"action": "BUY", "price": price, "size": size, "reason": "白大右侧：MA多头+MACD金叉+回调"}
    
    # 卖出条件：MA 空头或 MACD 死叉
    ma_bear = curr["ma5"] < curr["ma10"] < curr["ma20"]
    macd_death = prev["macd_dif"] >= prev["macd_dea"] and curr["macd_dif"] < curr["macd_dea"]
    
    if (ma_bear or macd_death) and position > 0:
        return {"action": "SELL", "price": curr["close"], "size": position, "reason": "白大右侧卖出"}
    
    return {"action": "HOLD", "reason": "无信号"}


def _signal_composer_strategy(df: pd.DataFrame, position: int, cash: float, params: Dict) -> Dict:
    """
    多因子合成信号策略（回测版）
    
    基于技术指标+量价数据合成买卖信号，简化版（不含形态识别，计算开销大）。
    
    买入：综合评分 > 0.7 且 MA 多头排列
    卖出：价格跌破止损或到达止盈，或评分转负
    
    参数：
      - stop_loss_pct: 止损比例（默认 3%）
      - take_profit_pct: 止盈比例（默认 6%）
      - position_pct: 仓位比例（默认 80%）
    """
    if len(df) < 30:
        return {"action": "HOLD", "reason": "数据不足"}
    
    curr = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else curr
    close = curr["close"]
    
    # 检查必要指标
    required = ["ma5", "ma20", "ma60", "macd_dif", "macd_dea", "kdj_k", "kdj_d", "rsi6", "boll_up", "boll_mid", "boll_down"]
    missing = [k for k in required if k not in df.columns]
    if missing:
        return {"action": "HOLD", "reason": f"指标缺失: {missing}"}
    
    # 提取最新指标
    indicators = {
        "ma5": curr["ma5"], "ma20": curr["ma20"], "ma60": curr["ma60"],
        "macd_dif": curr["macd_dif"], "macd_dea": curr["macd_dea"], "macd_bar": curr.get("macd_bar", 0),
        "kdj_k": curr["kdj_k"], "kdj_d": curr["kdj_d"], "kdj_j": curr.get("kdj_j", 0),
        "rsi6": curr["rsi6"], "rsi12": curr.get("rsi12", 0), "rsi24": curr.get("rsi24", 0),
        "boll_up": curr["boll_up"], "boll_mid": curr["boll_mid"], "boll_down": curr["boll_down"],
    }
    
    stop_loss_pct = params.get("stop_loss_pct", 0.03)
    take_profit_pct = params.get("take_profit_pct", 0.06)
    position_pct = params.get("position_pct", 0.8)
    
    # 如果有持仓，检查止损/止盈
    if position > 0 and hasattr(_signal_composer_strategy, "_entry_price") and _signal_composer_strategy._entry_price > 0:
        entry_price = _signal_composer_strategy._entry_price
        if close <= entry_price * (1 - stop_loss_pct):
            return {"action": "SELL", "price": close, "size": position, "reason": f"触及止损 ({stop_loss_pct*100:.0f}%)"}
        if close >= entry_price * (1 + take_profit_pct):
            return {"action": "SELL", "price": close, "size": position, "reason": f"触及止盈 ({take_profit_pct*100:.0f}%)"}
    
    # 计算综合评分（简化版，只使用指标和量价）
    score = 0.0
    reasons = []
    
    # 1. 趋势 (±0.35)
    if curr["ma5"] > curr["ma20"] > curr["ma60"]:
        score += 0.35
        reasons.append("MA多头排列")
    elif curr["ma5"] < curr["ma20"] < curr["ma60"]:
        score -= 0.35
        reasons.append("MA空头排列")
    
    # 2. MACD (±0.25)
    if prev["macd_dif"] <= prev["macd_dea"] and curr["macd_dif"] > curr["macd_dea"]:
        score += 0.25
        reasons.append("MACD金叉")
    elif prev["macd_dif"] >= prev["macd_dea"] and curr["macd_dif"] < curr["macd_dea"]:
        score -= 0.25
        reasons.append("MACD死叉")
    elif curr["macd_dif"] > curr["macd_dea"]:
        score += 0.1
        reasons.append("MACD多头")
    elif curr["macd_dif"] < curr["macd_dea"]:
        score -= 0.1
        reasons.append("MACD空头")
    
    # 3. KDJ (±0.2)
    if prev["kdj_k"] <= prev["kdj_d"] and curr["kdj_k"] > curr["kdj_d"] and curr["kdj_k"] < 80:
        score += 0.2
        reasons.append("KDJ金叉")
    elif prev["kdj_k"] >= prev["kdj_d"] and curr["kdj_k"] < curr["kdj_d"] and curr["kdj_k"] > 20:
        score -= 0.2
        reasons.append("KDJ死叉")
    
    # 4. RSI (±0.1)
    if curr["rsi6"] < 30:
        score += 0.1
        reasons.append("RSI超卖")
    elif curr["rsi6"] > 70:
        score -= 0.1
        reasons.append("RSI超买")
    
    # 5. BOLL (±0.1)
    if close > curr["boll_mid"]:
        score += 0.1
        reasons.append("BOLL中轨上方")
    else:
        score -= 0.1
        reasons.append("BOLL中轨下方")
    
    # 6. 量价 (±0.2) - 放量上涨加分
    if len(df) >= 20:
        avg_vol = df["volume"].iloc[-20:].mean()
        if curr["volume"] > avg_vol * 1.5 and close > prev["close"]:
            score += 0.2
            reasons.append("放量上涨")
        elif curr["volume"] > avg_vol * 1.5 and close < prev["close"]:
            score -= 0.2
            reasons.append("放量下跌")
    
    # 信号阈值
    BUY_THRESHOLD = 0.7
    SELL_THRESHOLD = -0.5
    
    if score >= BUY_THRESHOLD and position == 0 and cash > 0:
        price = close
        size = int(cash * position_pct / price)
        if size > 0:
            _signal_composer_strategy._entry_price = price
            return {
                "action": "BUY",
                "price": price,
                "size": size,
                "reason": f"多因子合成买入 (评分: +{score:.2f}) | {' + '.join(reasons)}",
            }
    
    if score <= SELL_THRESHOLD and position > 0:
        _signal_composer_strategy._entry_price = 0.0
        return {
            "action": "SELL",
            "price": close,
            "size": position,
            "reason": f"多因子合成卖出 (评分: {score:.2f}) | {' + '.join(reasons)}",
        }
    
    return {"action": "HOLD", "reason": f"评分: {score:+.2f} | {' + '.join(reasons[:3])}"}


# 策略注册表
PRESET_STRATEGIES = {
    "dual_ma": _dual_ma_strategy,
    "macd": _macd_strategy,
    "kd": _kd_strategy,
    "cai_sen": _cai_sen_strategy,
    "bai_da": _bai_da_strategy,
    "signal_composer": _signal_composer_strategy,
}


# ───────────────────────────────────────────────
# 自定义策略 DSL（无代码执行）
# ───────────────────────────────────────────────

# 支持的数值节点：
#   { "col": "ma5", "lag": 0 }          读取列，lag 表示向前偏移的 bar 数
#   { "param": "short_ma", "default": 5 } 读取 params，可给默认值
#   { "const": 20 }                       常量
#
# 支持的条件：
#   { "cross_up": [v1, v2] }              v1 上穿 v2
#   { "cross_down": [v1, v2] }            v1 下穿 v2
#   { "gt"/"gte"/"lt"/"lte"/"eq": [v1, v2] }
#   { "and": [cond1, cond2, ...] }
#   { "or": [cond1, cond2, ...] }
#   { "not": cond }
#   { "in_range": { "value": v, "min": lo, "max": hi } }
#
# 动作规则：
#   { "condition": cond, "action": "BUY"/"SELL"/"HOLD",
#     "position_pct": 0.99, "reason": "..." }

_COMPARATORS = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "eq": operator.eq,
}


def _lag_value_node(node: Dict[str, Any], n: int) -> Dict[str, Any]:
    """为列节点增加 n 个 bar 的 lag，用于 cross 条件判断上一根 K 线。"""
    if not isinstance(node, dict) or "col" not in node:
        raise ValueError("cross_up / cross_down 只能作用于列数据节点（{\"col\": ...}）")
    lagged = dict(node)
    lagged["lag"] = node.get("lag", 0) + n
    return lagged


def _eval_value_node(node: Any, df: pd.DataFrame, params: Dict[str, Any]) -> float:
    """解释数值节点。"""
    if isinstance(node, bool):
        raise ValueError("布尔值不能作为数值节点")
    if isinstance(node, (int, float)):
        return float(node)
    if not isinstance(node, dict):
        raise ValueError(f"非法数值节点: {node!r}")

    if "const" in node:
        return float(node["const"])

    if "param" in node:
        key = node["param"]
        if key not in params and "default" not in node:
            raise ValueError(f"缺少参数: {key}")
        return float(params.get(key, node.get("default")))

    if "col" in node:
        col = node["col"]
        lag = int(node.get("lag", 0))
        if col not in df.columns:
            raise ValueError(f"数据列缺失: {col}")
        idx = len(df) - 1 - lag
        if idx < 0:
            raise ValueError(f"数据不足，无法读取 {col}[lag={lag}]")
        return float(df[col].iloc[idx])

    raise ValueError(f"无法识别的数值节点: {node!r}")


def _eval_condition(cond: Any, df: pd.DataFrame, position: int, cash: float,
                    params: Dict[str, Any]) -> bool:
    """解释条件节点。"""
    if not isinstance(cond, dict):
        raise ValueError("condition 必须是对象")

    op = next(iter(cond))
    val = cond[op]

    if op in ("cross_up", "cross_down"):
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"{op} 需要两个操作数")
        a_now = _eval_value_node(val[0], df, params)
        b_now = _eval_value_node(val[1], df, params)
        a_prev = _eval_value_node(_lag_value_node(val[0], 1), df, params)
        b_prev = _eval_value_node(_lag_value_node(val[1], 1), df, params)
        if op == "cross_up":
            return a_prev <= b_prev and a_now > b_now
        return a_prev >= b_prev and a_now < b_now

    if op in _COMPARATORS:
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"{op} 需要两个操作数")
        a = _eval_value_node(val[0], df, params)
        b = _eval_value_node(val[1], df, params)
        return _COMPARATORS[op](a, b)

    if op == "and":
        if not isinstance(val, list):
            raise ValueError("'and' 需要条件数组")
        return all(_eval_condition(c, df, position, cash, params) for c in val)

    if op == "or":
        if not isinstance(val, list):
            raise ValueError("'or' 需要条件数组")
        return any(_eval_condition(c, df, position, cash, params) for c in val)

    if op == "not":
        return not _eval_condition(val, df, position, cash, params)

    if op == "in_range":
        if not isinstance(val, dict):
            raise ValueError("in_range 需要对象")
        v = _eval_value_node(val.get("value"), df, params)
        lo = _eval_value_node(val.get("min"), df, params)
        hi = _eval_value_node(val.get("max"), df, params)
        return lo <= v <= hi

    raise ValueError(f"未知条件操作符: {op}")


def _eval_rule(rule: Dict[str, Any], df: pd.DataFrame, position: int, cash: float,
               params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """解释单条动作规则，若条件不满足返回 None。"""
    cond = rule.get("condition")
    if cond is not None and not _eval_condition(cond, df, position, cash, params):
        return None

    action = rule.get("action")
    if action == "HOLD":
        return {"action": "HOLD", "reason": rule.get("reason", "无信号")}

    if action not in ("BUY", "SELL"):
        raise ValueError(f"非法 action: {action}")

    # 状态过滤：已有持仓不能买，空仓不能卖
    if action == "BUY" and (position != 0 or cash <= 0):
        return None
    if action == "SELL" and position <= 0:
        return None

    price = float(df["close"].iloc[-1])
    reason = rule.get("reason", action)

    if action == "BUY":
        pct = float(rule.get("position_pct", 0.99))
        if not 0 < pct <= 1:
            raise ValueError("BUY 的 position_pct 必须在 (0, 1] 之间")
        size = int(cash * pct / price)
        if size <= 0:
            return None
        return {"action": "BUY", "price": price, "size": size, "reason": reason}

    # SELL
    size = int(rule.get("size", position))
    if size <= 0 or size > position:
        size = position
    return {"action": "SELL", "price": price, "size": size, "reason": reason}


def _eval_custom_dsl(dsl: Dict[str, Any], df: pd.DataFrame, position: int, cash: float,
                     params: Dict[str, Any]) -> Dict[str, Any]:
    """解释完整 DSL，按 rules 顺序匹配，第一个非 None 结果生效。"""
    rules = dsl.get("rules", [])
    for rule in rules:
        signal = _eval_rule(rule, df, position, cash, params)
        if signal is not None:
            return signal
    return {"action": "HOLD", "reason": "无信号"}


def _validate_value_node(node: Any, path: str = "value") -> None:
    if isinstance(node, (int, float)):
        return
    if not isinstance(node, dict):
        raise ValueError(f"{path} 必须是数值、列引用、参数引用或常量")
    keys = set(node.keys())
    if "const" in keys:
        return
    if "param" in keys:
        return
    if "col" in keys:
        if not isinstance(node["col"], str):
            raise ValueError(f"{path}.col 必须是字符串")
        return
    raise ValueError(f"{path} 必须是 {{col, lag?}} / {{param, default?}} / {{const}} / 数值")


def _validate_condition(cond: Any, path: str = "condition") -> None:
    if not isinstance(cond, dict):
        raise ValueError(f"{path} 必须是对象")
    if not cond:
        raise ValueError(f"{path} 不能为空对象")
    op = next(iter(cond))
    val = cond[op]

    if op in ("cross_up", "cross_down"):
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"{path}.{op} 需要两个数值节点")
        _validate_value_node(val[0], f"{path}.{op}[0]")
        _validate_value_node(val[1], f"{path}.{op}[1]")
        return

    if op in _COMPARATORS:
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"{path}.{op} 需要两个数值节点")
        _validate_value_node(val[0], f"{path}.{op}[0]")
        _validate_value_node(val[1], f"{path}.{op}[1]")
        return

    if op in ("and", "or"):
        if not isinstance(val, list):
            raise ValueError(f"{path}.{op} 需要条件数组")
        for i, c in enumerate(val):
            _validate_condition(c, f"{path}.{op}[{i}]")
        return

    if op == "not":
        _validate_condition(val, f"{path}.not")
        return

    if op == "in_range":
        if not isinstance(val, dict):
            raise ValueError(f"{path}.in_range 必须是对象")
        for key in ("value", "min", "max"):
            if key not in val:
                raise ValueError(f"{path}.in_range 缺少 {key}")
            _validate_value_node(val[key], f"{path}.in_range.{key}")
        return

    raise ValueError(f"{path} 包含未知操作符: {op}")


def validate_custom_dsl(dsl: Any) -> None:
    """
    校验自定义策略 DSL 结构。

    Raises:
        ValueError: 当 DSL 结构非法时抛出。
    """
    if not isinstance(dsl, dict):
        raise ValueError("DSL 必须是 JSON 对象")

    rules = dsl.get("rules")
    if not isinstance(rules, list):
        raise ValueError("DSL 必须包含 rules 数组")

    for i, rule in enumerate(rules):
        path = f"rules[{i}]"
        if not isinstance(rule, dict):
            raise ValueError(f"{path} 必须是对象")
        if "action" not in rule:
            raise ValueError(f"{path} 缺少 action")
        if rule["action"] not in ("BUY", "SELL", "HOLD"):
            raise ValueError(f"{path}.action 必须是 BUY / SELL / HOLD")
        if "condition" in rule:
            _validate_condition(rule["condition"], f"{path}.condition")
        if rule["action"] == "BUY":
            pct = rule.get("position_pct", 0.99)
            if not isinstance(pct, (int, float)) or not 0 < pct <= 1:
                raise ValueError(f"{path}.position_pct 必须是 (0, 1] 之间的数值")


# ───────────────────────────────────────────────
# 回测引擎核心
# ───────────────────────────────────────────────

class BacktestEngine:
    """
    回测引擎
    
    单股票、逐日遍历回测框架。
    特点：
    1. 支持预设策略和自定义策略
    2. 考虑手续费和滑点
    3. 完整的绩效评估（收益率、夏普、回撤、胜率等）
    4. 不依赖 core/ 目录，使用 print 或简单日志
    """
    
    def __init__(self):
        self.logs = []
    
    def _log(self, msg: str):
        """记录日志"""
        self.logs.append(msg)
        print(f"[BacktestEngine] {msg}")
    
    def run(self, symbol: str, strategy_name: str, start_date: str, end_date: str,
            initial_cash: float = 100000.0, commission_rate: float = 0.0003,
            slippage: float = 0.001, params: Optional[Dict[str, Any]] = None,
            custom_code: Optional[str] = None, adjust: str = "qfq") -> BacktestResult:
        """
        运行单股回测
        
        Args:
            symbol: 股票代码（如 000001, 600519）
            strategy_name: 策略名称（dual_ma/macd/kd/cai_sen/bai_da/signal_composer/custom）
            start_date: 起始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            initial_cash: 初始资金，默认 100000
            commission_rate: 手续费率，默认 0.0003（万3）
            slippage: 滑点率，默认 0.001（0.1%）
            params: 策略参数字典
            custom_code: 自定义策略代码（strategy_name=custom 时必需）
            adjust: 复权方式（qfq/hfq/none），默认 qfq（前复权）
        
        Returns:
            BacktestResult 对象
        """
        self.logs = []
        params = params or {}
        
        self._log(f"开始回测: {symbol} | {strategy_name} | {start_date} ~ {end_date}")
        
        try:
            # 1. 获取历史数据
            df = self._fetch_data(symbol, start_date, end_date, adjust)
            if df is None or len(df) == 0:
                return self._error_result(
                    strategy_name, symbol, start_date, end_date,
                    initial_cash, params, "无法获取数据或数据为空"
                )
            
            # 2. 计算技术指标
            try:
                df = calculate_all_indicators(df)
            except Exception as e:
                self._log(f"指标计算失败: {e}")
                return self._error_result(
                    strategy_name, symbol, start_date, end_date,
                    initial_cash, params, f"指标计算失败: {e}"
                )
            
            # 3. 确定策略函数
            strategy_fn = self._resolve_strategy(strategy_name, custom_code)
            if strategy_fn is None:
                return self._error_result(
                    strategy_name, symbol, start_date, end_date,
                    initial_cash, params, f"未知策略: {strategy_name}"
                )
            
            # 4. 运行回测核心
            result = self._backtest(
                symbol, df, strategy_fn, initial_cash,
                commission_rate, slippage, params
            )
            
            # 5. 填充元数据
            result.strategy_name = strategy_name
            result.symbols = [symbol]
            result.start_date = start_date
            result.end_date = end_date
            result.initial_cash = initial_cash
            result.params = params
            result.logs = self.logs
            
            self._log(
                f"回测完成: 总收益={result.total_return:.2%}, "
                f"最大回撤={result.max_drawdown:.2%}, "
                f"Sharpe={result.sharpe_ratio:.2f}, "
                f"交易次数={result.total_trades}"
            )
            
            return result
            
        except Exception as e:
            traceback_str = traceback.format_exc()
            self._log(f"回测异常: {e}\n{traceback_str}")
            return self._error_result(
                strategy_name, symbol, start_date, end_date,
                initial_cash, params, str(e)
            )
    
    # ─────────────────────────────────────────
    # 数据获取
    # ─────────────────────────────────────────
    
    def _fetch_data(self, symbol: str, start_date: str, end_date: str, adjust: str) -> Optional[pd.DataFrame]:
        """获取历史K线数据"""
        if get_data_provider_service is None:
            self._log("DataProviderService 不可用，无法获取数据")
            return None
        
        try:
            svc = get_data_provider_service()
            # 将 YYYY-MM-DD 格式转换为 YYYYMMDD
            start_fmt = start_date.replace("-", "")
            end_fmt = end_date.replace("-", "")
            
            df = svc.fetch_ohlcv(
                symbol,
                start_date=start_fmt,
                end_date=end_fmt,
                period="daily",
                adjust=adjust,
            )
            
            if df is None or len(df) == 0:
                self._log(f"未获取到数据: {symbol}")
                return None
            
            # 统一日期格式为 YYYY-MM-DD
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            
            # 过滤日期范围（确保只包含 start_date ~ end_date）
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)].reset_index(drop=True)
            
            self._log(f"数据获取成功: {symbol}, {len(df)} 条记录, 范围 {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
            return df
            
        except Exception as e:
            self._log(f"数据获取失败: {e}")
            return None
    
    # ─────────────────────────────────────────
    # 策略解析
    # ─────────────────────────────────────────
    
    def _resolve_strategy(self, strategy_name: str, custom_code: Optional[str]) -> Optional[Callable]:
        """解析并返回策略函数"""
        if strategy_name == "custom":
            if not custom_code:
                self._log("自定义策略 DSL 为空")
                return None
            return self._load_custom_strategy(custom_code)
        
        if strategy_name in PRESET_STRATEGIES:
            return PRESET_STRATEGIES[strategy_name]
        
        self._log(f"未找到策略: {strategy_name}")
        return None
    
    def _load_custom_strategy(self, custom_code: str) -> Optional[Callable]:
        """
        加载自定义策略 DSL
        
        将 JSON DSL 解析并编译为可执行的策略函数，不调用任何代码执行。
        """
        try:
            dsl = json.loads(custom_code)
        except json.JSONDecodeError as e:
            self._log(f"自定义策略 DSL 不是合法 JSON: {e}")
            return None
        
        try:
            validate_custom_dsl(dsl)
        except ValueError as e:
            self._log(f"自定义策略 DSL 校验失败: {e}")
            return None
        
        def strategy_fn(df: pd.DataFrame, position: int, cash: float, params: Dict[str, Any]) -> Dict[str, Any]:
            return _eval_custom_dsl(dsl, df, position, cash, params)
        
        self._log("自定义策略 DSL 加载成功")
        return strategy_fn
    
    # ─────────────────────────────────────────
    # 回测核心逻辑
    # ─────────────────────────────────────────
    
    def _backtest(self, symbol: str, df: pd.DataFrame, strategy_fn: Callable,
                  initial_cash: float, commission_rate: float,
                  slippage: float, params: Dict[str, Any]) -> BacktestResult:
        """
        执行逐日回测核心逻辑
        
        流程：
        1. 从第 min_bars 天开始逐日遍历
        2. 每日调用策略函数获取交易信号
        3. 执行买入/卖出（考虑滑点和手续费）
        4. 记录每日净值快照
        5. 计算绩效指标
        """
        cash = initial_cash
        position = 0
        trades = []
        snapshots = []
        
        # 最小数据长度（策略函数通常需要至少60日数据以计算完整指标）
        min_bars = 60
        if len(df) < min_bars:
            self._log(f"数据不足: {len(df)} 条，需要至少 {min_bars} 条")
            return self._empty_result(initial_cash)
        
        # 逐日遍历
        for i in range(min_bars, len(df)):
            today = df.iloc[i]
            date = str(today["date"])
            close_price = float(today["close"])
            
            # 获取截至今日的历史数据给策略函数
            df_hist = df.iloc[:i + 1].copy()
            
            # 调用策略函数获取信号
            try:
                signal = strategy_fn(df_hist, position, cash, params)
            except Exception as e:
                self._log(f"策略函数异常 ({date}): {e}")
                signal = {"action": "HOLD", "reason": f"策略异常: {e}"}
            
            if signal is None:
                signal = {"action": "HOLD", "reason": "无信号"}
            
            action = signal.get("action", "HOLD")
            price = float(signal.get("price", close_price))
            size = int(signal.get("size", 0))
            reason = signal.get("reason", "")
            
            # ── 执行交易 ──
            if action == "BUY" and size > 0 and position == 0 and cash > 0:
                # 买入：执行价格 = 信号价格 * (1 + 滑点)
                execution_price = price * (1 + slippage)
                
                # A股最小交易单位100股（一手）
                size = (size // 100) * 100
                if size <= 0:
                    size = 100
                
                raw_amount = execution_price * size
                commission = raw_amount * commission_rate
                total_cost = raw_amount + commission
                
                if cash >= total_cost:
                    cash -= total_cost
                    position += size
                    trades.append(TradeRecord(
                        date=date,
                        action="BUY",
                        symbol=symbol,
                        price=round(execution_price, 4),
                        size=size,
                        amount=round(total_cost, 2),
                        commission=round(commission, 2),
                        reason=reason,
                        cash_after=round(cash, 2),
                        position_after=position,
                    ))
                    self._log(f"{date} BUY {symbol} @ {execution_price:.2f} x {size}, 成本={total_cost:.2f}")
                else:
                    # 尝试用剩余现金买入尽可能多的一手
                    max_size = int(cash / (execution_price * (1 + commission_rate)) / 100) * 100
                    if max_size >= 100:
                        raw_amount = execution_price * max_size
                        commission = raw_amount * commission_rate
                        total_cost = raw_amount + commission
                        cash -= total_cost
                        position += max_size
                        trades.append(TradeRecord(
                            date=date,
                            action="BUY",
                            symbol=symbol,
                            price=round(execution_price, 4),
                            size=max_size,
                            amount=round(total_cost, 2),
                            commission=round(commission, 2),
                            reason=reason,
                            cash_after=round(cash, 2),
                            position_after=position,
                        ))
                        self._log(f"{date} BUY {symbol} @ {execution_price:.2f} x {max_size}, 成本={total_cost:.2f}")
            
            elif action == "SELL" and size > 0 and position > 0:
                # 卖出：执行价格 = 信号价格 * (1 - 滑点)
                execution_price = price * (1 - slippage)
                sell_size = min(size, position)
                
                # A股一手整数倍
                sell_size = (sell_size // 100) * 100
                if sell_size <= 0:
                    sell_size = position
                
                raw_amount = execution_price * sell_size
                commission = raw_amount * commission_rate
                net_proceeds = raw_amount - commission
                
                cash += net_proceeds
                position -= sell_size
                
                trades.append(TradeRecord(
                    date=date,
                    action="SELL",
                    symbol=symbol,
                    price=round(execution_price, 4),
                    size=sell_size,
                    amount=round(raw_amount, 2),
                    commission=round(commission, 2),
                    reason=reason,
                    cash_after=round(cash, 2),
                    position_after=position,
                ))
                self._log(f"{date} SELL {symbol} @ {execution_price:.2f} x {sell_size}, 收入={net_proceeds:.2f}")
            
            # ── 计算每日净值 ──
            market_value = position * close_price
            total_value = cash + market_value
            
            snapshots.append(DailySnapshot(
                date=date,
                cash=round(cash, 2),
                position=position,
                close_price=round(close_price, 4),
                market_value=round(market_value, 2),
                total_value=round(total_value, 2),
                equity_return=0.0,
            ))
        
        # 计算日收益率
        for i in range(1, len(snapshots)):
            prev_value = snapshots[i - 1].total_value
            curr_value = snapshots[i].total_value
            if prev_value > 0:
                snapshots[i].equity_return = round((curr_value - prev_value) / prev_value, 6)
        
        # 计算绩效指标
        result = self._calculate_metrics(trades, snapshots, initial_cash)
        result.equity_curve = snapshots
        result.trades = trades
        result.monthly_returns = self._calculate_monthly_returns(snapshots)
        
        return result
    
    # ─────────────────────────────────────────
    # 绩效计算
    # ─────────────────────────────────────────
    
    def _calculate_metrics(self, trades: List[TradeRecord],
                         snapshots: List[DailySnapshot],
                         initial_cash: float) -> BacktestResult:
        """计算回测绩效指标"""
        result = BacktestResult(
            strategy_name="",
            symbols=[],
            start_date="",
            end_date="",
            initial_cash=initial_cash,
            final_value=initial_cash,
            total_return=0.0,
            annual_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            profit_loss_ratio=0.0,
            total_trades=0,
            win_trades=0,
            loss_trades=0,
            avg_holding_days=0.0,
        )
        
        if not snapshots:
            return result
        
        result.final_value = snapshots[-1].total_value
        result.total_return = (result.final_value - initial_cash) / initial_cash if initial_cash > 0 else 0.0
        
        # 年化收益率（假设一年252个交易日）
        days = len(snapshots)
        if days > 1:
            result.annual_return = (1 + result.total_return) ** (252 / days) - 1
        
        # 最大回撤
        peak = 0.0
        max_dd = 0.0
        for snap in snapshots:
            if snap.total_value > peak:
                peak = snap.total_value
            if peak > 0:
                dd = (peak - snap.total_value) / peak
                if dd > max_dd:
                    max_dd = dd
        result.max_drawdown = max_dd
        
        # 日收益率序列（排除首日的0）
        daily_returns = [snap.equity_return for snap in snapshots if abs(snap.equity_return) > 1e-12]
        
        # 夏普比率（假设无风险利率 2%）
        if len(daily_returns) > 1:
            daily_returns_arr = np.array(daily_returns)
            daily_vol = np.std(daily_returns_arr, ddof=1)
            if daily_vol > 0:
                risk_free_daily = 0.02 / 252
                excess_return = np.mean(daily_returns_arr) - risk_free_daily
                result.sharpe_ratio = excess_return / daily_vol * np.sqrt(252)
        
        # 交易统计
        buy_trades = [t for t in trades if t.action == "BUY"]
        sell_trades = [t for t in trades if t.action == "SELL"]
        result.total_trades = len(buy_trades)
        
        # 配对买卖计算盈亏
        trade_pairs = []
        remaining_buys = buy_trades.copy()
        for sell in sell_trades:
            for buy in remaining_buys:
                if buy.date < sell.date:
                    profit = (sell.price - buy.price) * sell.size
                    trade_pairs.append(profit)
                    remaining_buys.remove(buy)
                    break
        
        if trade_pairs:
            profits = np.array(trade_pairs)
            result.win_trades = int(np.sum(profits > 0))
            result.loss_trades = int(np.sum(profits <= 0))
            result.win_rate = result.win_trades / len(trade_pairs)
            
            win_profits = profits[profits > 0]
            loss_profits = profits[profits <= 0]
            avg_profit = float(np.mean(win_profits)) if len(win_profits) > 0 else 0.0
            avg_loss = float(np.mean(loss_profits)) if len(loss_profits) > 0 else 0.0
            result.profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else 0.0
        
        # 平均持仓天数
        holding_days = []
        buys = [t for t in trades if t.action == "BUY"]
        sells = [t for t in trades if t.action == "SELL"]
        for buy in buys:
            matching_sell = next((s for s in sells if s.date > buy.date and s.symbol == buy.symbol), None)
            if matching_sell:
                try:
                    b_date = datetime.strptime(buy.date, "%Y-%m-%d")
                    s_date = datetime.strptime(matching_sell.date, "%Y-%m-%d")
                    holding_days.append((s_date - b_date).days)
                except Exception:
                    pass
        
        if holding_days:
            result.avg_holding_days = round(float(np.mean(holding_days)), 1)
        
        return result
    
    def _calculate_monthly_returns(self, snapshots: List[DailySnapshot]) -> Dict[str, float]:
        """
        计算月度收益率字典
        
        Returns:
            { "YYYY-MM": 月收益率, ... }
        """
        monthly = {}
        for snap in snapshots:
            month = snap.date[:7]  # 提取 "YYYY-MM"
            if month not in monthly:
                monthly[month] = {"start": snap.total_value, "end": snap.total_value}
            monthly[month]["end"] = snap.total_value
        
        result = {}
        for month, vals in monthly.items():
            if vals["start"] > 0:
                result[month] = round((vals["end"] - vals["start"]) / vals["start"], 4)
        return result
    
    def _error_result(self, strategy_name: str, symbol: str, start_date: str,
                      end_date: str, initial_cash: float, params: Dict,
                      error: str) -> BacktestResult:
        """生成错误回测结果"""
        return BacktestResult(
            strategy_name=strategy_name,
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            final_value=initial_cash,
            total_return=0.0,
            annual_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            profit_loss_ratio=0.0,
            total_trades=0,
            win_trades=0,
            loss_trades=0,
            avg_holding_days=0.0,
            error=error,
            params=params,
            logs=self.logs,
        )
    
    def _empty_result(self, initial_cash: float) -> BacktestResult:
        """生成空回测结果"""
        return BacktestResult(
            strategy_name="",
            symbols=[],
            start_date="",
            end_date="",
            initial_cash=initial_cash,
            final_value=initial_cash,
            total_return=0.0,
            annual_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            profit_loss_ratio=0.0,
            total_trades=0,
            win_trades=0,
            loss_trades=0,
            avg_holding_days=0.0,
        )


# ───────────────────────────────────────────────
# 便捷函数
# ───────────────────────────────────────────────

def get_preset_strategies() -> List[str]:
    """获取所有预设策略名称列表"""
    return list(PRESET_STRATEGIES.keys())


def get_strategy_templates() -> List[Dict[str, Any]]:
    """
    获取策略模板列表（用于 API / 前端展示）
    
    Returns:
        包含策略名称、描述、参数定义的字典列表
    """
    return [
        {
            "name": "dual_ma",
            "display_name": "双均线策略",
            "description": "MA5 上穿/下穿 MA20，金叉买入，死叉卖出",
            "params": {
                "short_ma": {"type": "int", "default": 5, "description": "短期均线周期"},
                "long_ma": {"type": "int", "default": 20, "description": "长期均线周期"},
            },
        },
        {
            "name": "macd",
            "display_name": "MACD策略",
            "description": "MACD 金叉买入，死叉卖出",
            "params": {},
        },
        {
            "name": "kd",
            "display_name": "KD策略",
            "description": "K 上穿 D 买入，K 下穿 D 卖出",
            "params": {},
        },
        {
            "name": "cai_sen",
            "display_name": "蔡森W底",
            "description": "简化W底形态识别，颈线突破买入",
            "params": {
                "lookback": {"type": "int", "default": 20, "description": "回溯周期"},
            },
        },
        {
            "name": "bai_da",
            "display_name": "白大右侧",
            "description": "MA多头 + MACD金叉 + 回调不创新低买入",
            "params": {},
        },
        {
            "name": "signal_composer",
            "display_name": "多因子合成",
            "description": "综合技术指标+量价+支撑阻力合成买卖信号",
            "params": {
                "stop_loss_pct": {"type": "float", "default": 0.03, "description": "止损比例"},
                "take_profit_pct": {"type": "float", "default": 0.06, "description": "止盈比例"},
                "position_pct": {"type": "float", "default": 0.8, "description": "仓位比例"},
            },
        },
        {
            "name": "custom",
            "display_name": "自定义策略",
            "description": "用户输入 JSON 声明式 DSL，由后端解释执行（无代码执行）",
            "params": {},
        },
    ]


def get_custom_strategy_template() -> str:
    """
    获取自定义策略 DSL 模板

    Returns:
        JSON 字符串，包含 rules / condition / action 示例
    """
    return '''{
  "rules": [
    {
      "condition": {
        "cross_up": [
          { "col": "ma5" },
          { "col": "ma20" }
        ]
      },
      "action": "BUY",
      "position_pct": 0.99,
      "reason": "MA5 上穿 MA20"
    },
    {
      "condition": {
        "cross_down": [
          { "col": "ma5" },
          { "col": "ma20" }
        ]
      },
      "action": "SELL",
      "reason": "MA5 下穿 MA20"
    }
  ]
}
'''


# ───────────────────────────────────────────────
# 入口测试
# ───────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Backtest Engine - 模块测试")
    print("=" * 60)
    
    # 1. 策略列表
    print("\n[1] 预设策略列表:")
    for name in get_preset_strategies():
        print(f"  - {name}")
    
    # 2. 策略模板
    print("\n[2] 策略模板数:", len(get_strategy_templates()))
    
    # 3. 自定义模板
    print("\n[3] 自定义策略模板:")
    print(get_custom_strategy_template()[:200] + "...")
    
    # 4. 引擎初始化
    print("\n[4] BacktestEngine 初始化:")
    engine = BacktestEngine()
    print("  初始化成功")
    
    # 5. run 方法签名检查
    import inspect
    sig = inspect.signature(engine.run)
    print(f"\n[5] run 方法签名: run{sig}")
    print("  参数列表:", list(sig.parameters.keys()))
    
    print("\n" + "=" * 60)
    print("模块测试完成")
    print("=" * 60)
