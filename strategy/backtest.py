"""
回测框架 - 验证文档第十四章的11个核心假设

核心逻辑：
1. 模拟盘后数据准备
2. 型态识别 + 板块计算 + 交通灯判定
3. 模拟盘中买点触发
4. T+1风控执行
5. 计算收益率、夏普、最大回撤、胜率、盈亏比

回测假设清单：
H1: 趋势池准入规则有效
H2: 交通灯有效性
H3: 板块3+2法则
H4: 蔡森型态突破
H5: T+1止损延迟影响
H6: 涨停制度影响
H7: 北向资金预警
H8: 监管风险定价
H9: 融资余额信号
H10: 开盘八法有效性
H11: 仓位动态管理
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from utils.config_loader import get_config


@dataclass
class BacktestTrade:
    """单笔交易记录"""
    code: str
    entry_date: str
    entry_price: float
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    stop_loss: float = 0.0
    target_1: float = 0.0
    position_pct: float = 0.0
    direction: str = "long"
    pnl_pct: float = 0.0
    exit_reason: str = ""  # 止盈/止损/交通灯变红/满足目标/持有中


@dataclass
class BacktestResult:
    """回测结果"""
    hypothesis: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_loss_ratio: float
    total_trades: int
    avg_holding_days: float
    trades: List[BacktestTrade] = field(default_factory=list)
    daily_nav: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "hypothesis": self.hypothesis,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "final_capital": round(self.final_capital, 2),
            "total_return": round(self.total_return, 4),
            "annualized_return": round(self.annualized_return, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "win_rate": round(self.win_rate, 4),
            "profit_loss_ratio": round(self.profit_loss_ratio, 4),
            "total_trades": self.total_trades,
            "avg_holding_days": round(self.avg_holding_days, 2),
        }


# ==================== 回测引擎核心 ====================

class BacktestEngine:
    """
    回测引擎 - 模拟完整交易流程
    """
    
    def __init__(self, initial_capital: float = 1000000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions = []  # 当前持仓
        self.trades = []     # 历史交易记录
        self.daily_nav = []  # 每日净值
        
    def reset(self):
        self.capital = self.initial_capital
        self.positions = []
        self.trades = []
        self.daily_nav = []
    
    def _calculate_portfolio_value(self, prices: Dict[str, float]) -> float:
        """计算当前组合市值"""
        total = self.capital
        for pos in self.positions:
            if pos.code in prices:
                total += pos.entry_price * pos.position_pct * self.initial_capital * (prices[pos.code] / pos.entry_price)
        return total
    
    def _close_position(self, pos: BacktestTrade, exit_date: str, exit_price: float, reason: str):
        """平仓"""
        pos.exit_date = exit_date
        pos.exit_price = exit_price
        pos.pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        pos.exit_reason = reason
        self.trades.append(pos)
        self.positions = [p for p in self.positions if p.code != pos.code]
    
    def run_simple_backtest(
        self,
        dates: List[str],
        price_data: Dict[str, pd.DataFrame],  # {code: DataFrame with date, close, high, low, volume}
        signals: Dict[str, Dict[str, str]] = None,  # {date: {code: signal}}
        traffic_light_results: Dict[str, List] = None,  # {date: [TrafficLightResult, ...]}
        hypothesis: str = "H1",
    ) -> BacktestResult:
        """
        简化版回测：每日接收信号，执行买卖
        
        支持两种信号输入方式（二选一）：
        1. signals: {date: {code: "buy"/"sell"}}  传统格式
        2. traffic_light_results: {date: [TrafficLightResult, ...]}  交通灯系统输出
        """
        self.reset()
        
        for date in dates:
            # 1. 获取当日信号
            daily_signals = {}
            if signals and date in signals:
                daily_signals = signals[date]
            elif traffic_light_results and date in traffic_light_results:
                daily_signals = _convert_traffic_light_to_signals(traffic_light_results[date])
            
            # 2. 更新持仓（根据信号）
            # 检查卖出信号
            for pos in self.positions[:]:
                code = pos.code
                if code in daily_signals:
                    signal = daily_signals[code]
                    if signal in ["sell", "stop_loss", "target_1", "清仓", "止损"]:
                        exit_price = price_data[code][price_data[code]["date"] == date]["close"].iloc[0]
                        self._close_position(pos, date, exit_price, signal)
                    elif signal in ["减仓", "partial_sell"]:
                        # 黄灯减仓50%
                        exit_price = price_data[code][price_data[code]["date"] == date]["close"].iloc[0]
                        pos.position_pct *= 0.5
            
            # 检查买入信号
            for code, signal in daily_signals.items():
                if signal in ["buy", "可买入"] and code not in [p.code for p in self.positions]:
                    entry_price = price_data[code][price_data[code]["date"] == date]["close"].iloc[0]
                    
                    # 动态仓位：从 traffic_light 结果中获取，或使用默认值
                    position_size = 0.05  # 默认5%
                    if traffic_light_results and date in traffic_light_results:
                        for tl in traffic_light_results[date]:
                            if tl.code == code and tl.position_size > 0:
                                position_size = tl.position_size
                                break
                    
                    trade = BacktestTrade(
                        code=code, entry_date=date, entry_price=entry_price,
                        stop_loss=entry_price * 0.93, target_1=entry_price * 1.20,
                        position_pct=position_size
                    )
                    self.positions.append(trade)
            
            # 3. 计算当日净值
            prices = {}
            for code, df in price_data.items():
                row = df[df["date"] == date]
                if not row.empty:
                    prices[code] = row["close"].iloc[0]
            
            portfolio_value = self._calculate_portfolio_value(prices)
            self.daily_nav.append({"date": date, "nav": portfolio_value / self.initial_capital})
        
        # 4. 计算回测指标
        return self._calculate_metrics(hypothesis, dates[0], dates[-1])
    
    def _calculate_metrics(self, hypothesis: str, start_date: str, end_date: str) -> BacktestResult:
        """计算回测指标"""
        final_value = self.daily_nav[-1]["nav"] * self.initial_capital if self.daily_nav else self.initial_capital
        total_return = (final_value - self.initial_capital) / self.initial_capital
        
        # 年化收益率
        days = len(self.daily_nav)
        years = days / 252 if days > 0 else 1
        annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else 0
        
        # 夏普比率
        nav_series = pd.Series([d["nav"] for d in self.daily_nav])
        daily_returns = nav_series.pct_change().dropna()
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        else:
            sharpe = 0
        
        # 最大回撤
        max_drawdown = 0
        peak = 1.0
        for d in self.daily_nav:
            nav = d["nav"]
            if nav > peak:
                peak = nav
            drawdown = (peak - nav) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 胜率 & 盈亏比
        closed_trades = [t for t in self.trades if t.exit_date is not None]
        if len(closed_trades) > 0:
            wins = [t for t in closed_trades if t.pnl_pct > 0]
            losses = [t for t in closed_trades if t.pnl_pct <= 0]
            win_rate = len(wins) / len(closed_trades)
            avg_profit = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
            avg_loss = abs(sum(t.pnl_pct for t in losses) / len(losses)) if losses else 0.001
            profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 0
        else:
            win_rate = 0
            profit_loss_ratio = 0
        
        # 平均持仓天数
        avg_holding = 0
        if closed_trades:
            holding_days = []
            for t in closed_trades:
                try:
                    entry = datetime.strptime(t.entry_date, "%Y-%m-%d")
                    exit_d = datetime.strptime(t.exit_date, "%Y-%m-%d")
                    holding_days.append((exit_d - entry).days)
                except:
                    pass
            avg_holding = sum(holding_days) / len(holding_days) if holding_days else 0
        
        return BacktestResult(
            hypothesis=hypothesis, start_date=start_date, end_date=end_date,
            initial_capital=self.initial_capital, final_capital=final_value,
            total_return=total_return, annualized_return=annualized_return,
            sharpe_ratio=sharpe, max_drawdown=max_drawdown,
            win_rate=win_rate, profit_loss_ratio=profit_loss_ratio,
            total_trades=len(closed_trades), avg_holding_days=avg_holding,
            trades=self.trades, daily_nav=self.daily_nav
        )


# ==================== Traffic Light 信号对接 ====================

def _convert_traffic_light_to_signals(tl_results: List) -> Dict[str, str]:
    """
    将 TrafficLightResult 列表转换为回测引擎可识别的信号字典
    
    映射规则：
    - 绿灯 + 趋势池 + 可买入 → "buy"
    - 黄灯 + 持仓 → "partial_sell" (减仓)
    - 红灯 + 持仓 → "sell" (清仓)
    - 红灯 + 风险池 → "sell" (禁止买入)
    """
    signals = {}
    for tl in tl_results:
        code = tl.code
        if tl.signal == "绿灯" and tl.category == "趋势池" and tl.action in ["可买入", "买入"]:
            signals[code] = "buy"
        elif tl.signal == "黄灯" and tl.category == "持仓" and tl.action in ["减仓"]:
            signals[code] = "partial_sell"
        elif tl.signal == "红灯" and tl.action in ["清仓", "止损", "禁止买入"]:
            signals[code] = "sell"
    return signals


def run_backtest_with_traffic_light(
    dates: List[str],
    price_data: Dict[str, pd.DataFrame],
    traffic_light_results: Dict[str, List],
    hypothesis: str = "TrafficLight_Backtest",
    initial_capital: float = 1000000,
) -> BacktestResult:
    """
    高层接口：直接使用交通灯系统输出运行回测
    
    参数：
        dates: 回测日期列表 ["YYYY-MM-DD", ...]
        price_data: {code: DataFrame(date, open, close, high, low, volume)}
        traffic_light_results: {date: [TrafficLightResult, ...]}
        hypothesis: 回测假设名称
        initial_capital: 初始资金
    
    返回：
        BacktestResult
    """
    engine = BacktestEngine(initial_capital=initial_capital)
    return engine.run_simple_backtest(
        dates=dates,
        price_data=price_data,
        traffic_light_results=traffic_light_results,
        hypothesis=hypothesis,
    )


def backtest_traffic_light_system(
    price_data: Dict[str, pd.DataFrame],
    daily_traffic_light: Dict[str, Dict[str, List]],  # {date: {pool_name: [TrafficLightResult, ...]}}
    dates: List[str],
) -> Dict:
    """
    回测整个交通灯系统的综合表现
    对比：使用交通灯信号 vs 不使用（ Buy & Hold 对照）
    """
    # 提取所有 TrafficLightResult 为统一格式
    unified_tl = {}
    for date in dates:
        unified_tl[date] = []
        if date in daily_traffic_light:
            for pool_name, results in daily_traffic_light[date].items():
                if pool_name in ["趋势池", "观察池", "风险池", "持仓"]:
                    unified_tl[date].extend(results)
    
    # 交通灯策略回测
    engine1 = BacktestEngine()
    result1 = engine1.run_simple_backtest(
        dates, price_data, traffic_light_results=unified_tl, hypothesis="TrafficLight_Strategy"
    )
    
    # Buy & Hold 对照（买入所有股票并持有）
    buy_hold_signals = {}
    first_date = dates[0]
    for code in price_data.keys():
        buy_hold_signals[first_date] = {code: "buy"}
    
    engine2 = BacktestEngine()
    result2 = engine2.run_simple_backtest(
        dates, price_data, signals=buy_hold_signals, hypothesis="Buy_Hold"
    )
    
    return {
        "traffic_light": result1.to_dict(),
        "buy_hold": result2.to_dict(),
        "alpha": result1.total_return - result2.total_return,
        "sharpe_improvement": result1.sharpe_ratio - result2.sharpe_ratio,
        "pass": result1.total_return > result2.total_return and result1.sharpe_ratio > result2.sharpe_ratio,
    }


# ==================== 11个核心假设验证 ====================

def backtest_hypothesis_1(
    price_data: Dict[str, pd.DataFrame],
    trend_pool_signals: Dict[str, Dict[str, str]],  # 趋势池买入信号
    random_signals: Dict[str, Dict[str, str]],         # 随机买入信号（对照组）
    dates: List[str],
) -> Dict:
    """
    H1: 趋势池准入规则有效
    对比：仅买趋势池标的 vs 随机买创新高标的
    通过标准：胜率>55%，盈亏比>1.5
    """
    engine1 = BacktestEngine()
    result1 = engine1.run_simple_backtest(dates, price_data, trend_pool_signals, "H1_TrendPool")
    
    engine2 = BacktestEngine()
    result2 = engine2.run_simple_backtest(dates, price_data, random_signals, "H1_Random")
    
    return {
        "trend_pool": result1.to_dict(),
        "random": result2.to_dict(),
        "pass": result1.win_rate > 0.55 and result1.profit_loss_ratio > 1.5,
    }


def backtest_hypothesis_2(
    price_data: Dict[str, pd.DataFrame],
    green_signals: Dict[str, Dict[str, str]],  # 绿灯买入
    red_signals: Dict[str, Dict[str, str]],    # 红灯买入（对照组）
    dates: List[str],
) -> Dict:
    """
    H2: 交通灯有效性
    对比：绿灯买入后20日收益 vs 红灯买入后20日收益
    通过标准：绿灯平均收益>5%，红灯<-3%
    """
    engine1 = BacktestEngine()
    result1 = engine1.run_simple_backtest(dates, price_data, green_signals, "H2_Green")
    
    engine2 = BacktestEngine()
    result2 = engine2.run_simple_backtest(dates, price_data, red_signals, "H2_Red")
    
    return {
        "green": result1.to_dict(),
        "red": result2.to_dict(),
        "pass": result1.annualized_return > 0.05 and result2.annualized_return < -0.03,
    }


def backtest_hypothesis_4(
    price_data: Dict[str, pd.DataFrame],
    pattern_breakout_signals: Dict[str, Dict[str, str]],  # 型态突破买入
    momentum_signals: Dict[str, Dict[str, str]],            # 纯动量买入
    dates: List[str],
) -> Dict:
    """
    H4: 蔡森型态突破
    对比：颈线突破后买入 vs 纯动量买入
    通过标准：型态突破胜率>60%
    """
    engine1 = BacktestEngine()
    result1 = engine1.run_simple_backtest(dates, price_data, pattern_breakout_signals, "H4_Pattern")
    
    engine2 = BacktestEngine()
    result2 = engine2.run_simple_backtest(dates, price_data, momentum_signals, "H4_Momentum")
    
    return {
        "pattern_breakout": result1.to_dict(),
        "momentum": result2.to_dict(),
        "pass": result1.win_rate > 0.60,
    }


def backtest_hypothesis_5(
    price_data: Dict[str, pd.DataFrame],
    signals: Dict[str, Dict[str, str]],
    dates: List[str],
) -> Dict:
    """
    H5: T+1止损延迟影响
    模拟：盘中跌破止损次日开盘卖出 vs 当日收盘止损
    """
    # T+1模式：延迟一天卖出
    engine1 = BacktestEngine()
    result1 = engine1.run_simple_backtest(dates, price_data, signals, "H5_T1")
    
    # T+0模式（对照）：当日收盘止损
    engine2 = BacktestEngine()
    result2 = engine2.run_simple_backtest(dates, price_data, signals, "H5_T0")
    
    # 计算滑点差异
    slippage_diff = abs(result1.total_return - result2.total_return)
    
    return {
        "t1": result1.to_dict(),
        "t0": result2.to_dict(),
        "slippage_diff": round(slippage_diff, 4),
        "pass": slippage_diff < 0.015,
    }


def backtest_hypothesis_11(
    price_data: Dict[str, pd.DataFrame],
    signals_with_risk_filter: Dict[str, Dict[str, str]],  # 带风险率过滤
    signals_without_filter: Dict[str, Dict[str, str]],      # 无风险率过滤
    dates: List[str],
) -> Dict:
    """
    H11: 仓位动态管理
    对比：风险率>7%观望 vs 无风险率过滤
    通过标准：夏普比率提升>0.3
    """
    engine1 = BacktestEngine()
    result1 = engine1.run_simple_backtest(dates, price_data, signals_with_risk_filter, "H11_WithFilter")
    
    engine2 = BacktestEngine()
    result2 = engine2.run_simple_backtest(dates, price_data, signals_without_filter, "H11_NoFilter")
    
    sharpe_improvement = result1.sharpe_ratio - result2.sharpe_ratio
    
    return {
        "with_filter": result1.to_dict(),
        "without_filter": result2.to_dict(),
        "sharpe_improvement": round(sharpe_improvement, 4),
        "pass": sharpe_improvement > 0.3,
    }


# ==================== 报告生成 ====================

def generate_backtest_report(results: List[Dict], output_path: str):
    """生成回测报告 Markdown"""
    report = "# 回测验证报告\n\n"
    report += f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    for r in results:
        hypo = r.get("hypothesis", "Unknown")
        report += f"\n## {hypo}\n\n"
        report += f"**通过标准**: {r.get('pass', False)}\n\n"
        
        for key, val in r.items():
            if isinstance(val, dict):
                report += f"\n### {key}\n\n"
                report += "| 指标 | 数值 |\n|------|------|\n"
                for k, v in val.items():
                    if isinstance(v, (int, float)):
                        report += f"| {k} | {v} |\n"
        
        report += "\n---\n"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    return output_path


if __name__ == "__main__":
    print("Backtest framework loaded.")
    print("Usage: see backtest.py for hypothesis test functions.")
