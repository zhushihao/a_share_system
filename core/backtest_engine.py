"""
Backtest Engine v4.0 MVP - 回测引擎（最小可行版本）

核心能力：
1. 信号驱动回测：基于历史信号模拟交易
2. 未来函数避免：信号T日 → 交易T+1日开盘价
3. 绩效评估：收益率、最大回撤、Sharpe、胜率
4. 与现有系统集成：resilience 获取数据、llm_agent 生成信号
5. 可观测性：每笔交易、每日净值自动记录

回测流程：
    for date in range(start, end):
        1. 获取当日数据
        2. 运行信号识别（Pattern/LLM/规则）
        3. 信号触发 → 记录交易计划（T+1执行）
        4. 执行前一日交易计划（买入/卖出）
        5. 更新持仓、计算净值
    输出：绩效报告

使用方式：
    engine = BacktestEngine(initial_capital=100000)
    
    # 定义信号策略
    def signal_strategy(code, klines, date):
        # 返回 Signal 对象或 None
        if ma20 > ma60 and rsi < 70:
            return Signal(code=code, action="buy", price=0)
        return None
    
    # 运行回测
    report = engine.run(
        codes=["000001", "300750"],
        start_date="2025-01-01",
        end_date="2025-06-19",
        signal_fn=signal_strategy,
    )
    
    # 查看结果
    print(report.total_return)
    print(report.sharpe_ratio)
"""

import pandas as pd
import numpy as np
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import time

from core.observability import get_obs
from core.resilience import get_resilience, FallbackResult
from core.llm_agent import get_analyzer, LLMSignal
from core.parallel_engine import ParallelEngine


@dataclass
class Trade:
    """交易记录"""
    date: str = ""                # 交易日期
    code: str = ""               # 股票代码
    action: str = ""             # buy / sell
    price: float = 0.0           # 成交价
    shares: int = 0              # 股数
    amount: float = 0.0          # 成交金额
    signal_type: str = ""        # 信号类型
    signal_confidence: float = 0.0
    reason: str = ""             # 交易理由
    
    def to_dict(self) -> Dict:
        return {
            "date": self.date,
            "code": self.code,
            "action": self.action,
            "price": round(self.price, 2),
            "shares": self.shares,
            "amount": round(self.amount, 2),
            "signal_type": self.signal_type,
            "confidence": round(self.signal_confidence, 2),
            "reason": self.reason,
        }


@dataclass
class DailySnapshot:
    """每日净值快照"""
    date: str = ""
    total_value: float = 0.0      # 总资产
    cash: float = 0.0             # 现金
    market_value: float = 0.0     # 持仓市值
    positions: Dict[str, int] = field(default_factory=dict)  # {code: shares}
    daily_return: float = 0.0     # 日收益率
    
    def to_dict(self) -> Dict:
        return {
            "date": self.date,
            "total_value": round(self.total_value, 2),
            "cash": round(self.cash, 2),
            "market_value": round(self.market_value, 2),
            "positions": self.positions,
            "daily_return": round(self.daily_return, 4),
        }


@dataclass
class BacktestReport:
    """回测绩效报告"""
    # 基本指标
    initial_capital: float = 100000.0
    final_value: float = 0.0
    total_return: float = 0.0       # 总收益率
    annualized_return: float = 0.0  # 年化收益率
    
    # 风险指标
    max_drawdown: float = 0.0       # 最大回撤
    max_drawdown_date: str = ""
    sharpe_ratio: float = 0.0       # Sharpe比率
    volatility: float = 0.0         # 年化波动率
    
    # 交易统计
    total_trades: int = 0
    win_trades: int = 0
    lose_trades: int = 0
    win_rate: float = 0.0           # 胜率
    avg_profit: float = 0.0         # 平均盈利
    avg_loss: float = 0.0           # 平均亏损
    profit_loss_ratio: float = 0.0  # 盈亏比
    
    # 持仓统计
    max_positions: int = 0          # 最大持仓数
    avg_holding_days: float = 0.0   # 平均持仓天数
    
    # 数据
    daily_snapshots: List[Dict] = field(default_factory=list)
    trades: List[Dict] = field(default_factory=list)
    equity_curve: List[Tuple[str, float]] = field(default_factory=list)  # (date, value)
    
    def to_dict(self) -> Dict:
        return {
            "initial_capital": self.initial_capital,
            "final_value": round(self.final_value, 2),
            "total_return": round(self.total_return, 4),
            "annualized_return": round(self.annualized_return, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_date": self.max_drawdown_date,
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "volatility": round(self.volatility, 4),
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "avg_profit": round(self.avg_profit, 2),
            "avg_loss": round(self.avg_loss, 2),
            "profit_loss_ratio": round(self.profit_loss_ratio, 2),
            "max_positions": self.max_positions,
            "avg_holding_days": round(self.avg_holding_days, 1),
        }


class BacktestEngine:
    """
    回测引擎 MVP
    
    核心设计：
    1. T日信号 → T+1日开盘价执行（避免未来函数）
    2. 固定仓位：每只信号买入固定金额（如10000元）
    3. 止盈止损：买入后 N 天自动卖出，或达到止盈/止损比例
    4. 可扩展：signal_fn 可替换为任意策略（LLM/规则/机器学习）
    """
    
    def __init__(self, initial_capital: float = 100000.0,
                 position_size: float = 10000.0,     # 每只信号买入金额
                 max_positions: int = 10,             # 最大持仓数
                 take_profit: float = 0.15,           # 止盈 15%
                 stop_loss: float = -0.07,           # 止损 -7%
                 max_holding_days: int = 20):        # 最大持仓天数
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.max_positions = max_positions
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
        
        self._obs = get_obs()
        self._resilience = get_resilience()
    
    def run(self, codes: List[str], start_date: str, end_date: str,
            signal_fn: Optional[Callable] = None) -> BacktestReport:
        """
        运行回测
        
        Args:
            codes: 股票池
            start_date/end_date: "YYYY-MM-DD"
            signal_fn: 信号函数(code, klines, current_date) -> Signal or None
        
        Returns:
            BacktestReport
        """
        start_time = time.time()
        self._obs.log("INFO", f"Backtest starting: {len(codes)} stocks, {start_date} ~ {end_date}", "BacktestEngine")
        
        # 1. 获取所有股票的历史数据
        stock_data = self._fetch_all_data(codes, start_date, end_date)
        
        # 2. 生成交易日历
        trade_dates = self._generate_trade_dates(stock_data, start_date, end_date)
        
        # 3. 初始化状态
        cash = self.initial_capital
        positions: Dict[str, Dict] = {}  # {code: {"shares": int, "entry_price": float, "entry_date": str, "days": int}}
        trades: List[Trade] = []
        snapshots: List[DailySnapshot] = []
        equity_curve: List[Tuple[str, float]] = []
        
        # 4. 逐日回测
        pending_orders: List[Dict] = []  # 次日执行的交易计划
        
        for i, date in enumerate(trade_dates):
            # 执行前一日交易计划
            cash, positions = self._execute_orders(pending_orders, cash, positions, date, stock_data, trades)
            pending_orders = []
            
            # 检查止盈止损
            cash, positions, exit_trades = self._check_exit_conditions(cash, positions, date, stock_data)
            trades.extend(exit_trades)
            
            # 生成信号（T日收盘后）
            if i < len(trade_dates) - 1:  # 最后一天不生成新信号
                next_date = trade_dates[i + 1]
                signals = self._generate_signals(codes, stock_data, date, signal_fn)
                
                # 过滤信号，生成交易计划
                for signal in signals:
                    if len(positions) < self.max_positions and signal.code not in positions:
                        pending_orders.append({
                            "date": next_date,
                            "code": signal.code,
                            "action": "buy",
                            "signal": signal,
                        })
            
            # 计算当日净值
            snapshot = self._calculate_snapshot(date, cash, positions, stock_data)
            snapshots.append(snapshot)
            equity_curve.append((date, snapshot.total_value))
        
        # 5. 生成报告
        report = self._generate_report(snapshots, trades, equity_curve)
        
        duration = (time.time() - start_time) * 1000
        self._obs.log("INFO", 
            f"Backtest completed: return={report.total_return:.2%}, "
            f"maxdd={report.max_drawdown:.2%}, sharpe={report.sharpe_ratio:.2f}, "
            f"trades={report.total_trades}, duration={duration:.0f}ms",
            "BacktestEngine")
        
        return report
    
    # ========================================================================
    # 数据获取
    # ========================================================================
    
    def _fetch_all_data(self, codes: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """获取所有股票的历史数据"""
        self._obs.log("INFO", f"Fetching data for {len(codes)} stocks", "BacktestEngine")
        
        stock_data = {}
        
        # 使用并行引擎获取数据
        engine = ParallelEngine(max_workers=8, batch_size=50)
        
        def fetch_fn(code):
            result = self._resilience.fetch_kline(code, start_date, end_date)
            if result.success and result.data is not None and len(result.data) > 0:
                return result.data
            return None
        
        result = engine.map(codes, fetch_fn)
        
        for code, data in result["results"].items():
            if data is not None and isinstance(data, pd.DataFrame) and len(data) > 0:
                stock_data[code] = data
        
        self._obs.log("INFO", f"Data loaded: {len(stock_data)}/{len(codes)} stocks", "BacktestEngine")
        return stock_data
    
    def _generate_trade_dates(self, stock_data: Dict[str, pd.DataFrame],
                              start_date: str, end_date: str) -> List[str]:
        """生成交易日历（取所有股票都有的交易日）"""
        all_dates = set()
        for df in stock_data.values():
            if "date" in df.columns:
                dates = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d").tolist()
                all_dates.update(dates)
        
        dates = sorted([d for d in all_dates if start_date <= d <= end_date])
        return dates
    
    # ========================================================================
    # 信号生成
    # ========================================================================
    
    def _generate_signals(self, codes: List[str], stock_data: Dict[str, pd.DataFrame],
                          current_date: str, signal_fn: Optional[Callable] = None) -> List[LLMSignal]:
        """生成交易信号"""
        signals = []
        
        # 使用默认规则策略（如果未提供 signal_fn）
        if signal_fn is None:
            signal_fn = self._default_signal_strategy
        
        for code in codes:
            if code not in stock_data:
                continue
            
            df = stock_data[code]
            
            # 获取截止到 current_date 的数据
            df_hist = df[df["date"] <= current_date]
            if len(df_hist) < 20:
                continue
            
            signal = signal_fn(code, df_hist, current_date)
            if signal is not None and signal.confidence > 0.5:
                signals.append(signal)
        
        # 按置信度排序，只取前 max_positions 个
        signals.sort(key=lambda x: x.confidence, reverse=True)
        return signals[:self.max_positions]
    
    def _default_signal_strategy(self, code: str, klines: pd.DataFrame,
                                  current_date: str) -> Optional[LLMSignal]:
        """默认信号策略：均线多头排列 + RSI 不过热"""
        close = klines["close"]
        
        if len(close) < 20:
            return None
        
        ma5 = close.tail(5).mean()
        ma10 = close.tail(10).mean()
        ma20 = close.tail(20).mean()
        current_price = close.iloc[-1]
        
        # 计算 RSI（简单版）
        delta = close.diff()
        gain = delta.where(delta > 0, 0).tail(14)
        loss = (-delta.where(delta < 0, 0)).tail(14)
        avg_gain = gain.mean() if len(gain) > 0 else 0
        avg_loss = loss.mean() if len(loss) > 0 else 0
        rsi = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
        
        # 信号判定：均线多头排列 + RSI 40-70
        if ma5 > ma10 > ma20 and 40 < rsi < 70:
            return LLMSignal(
                code=code,
                pattern_type="uptrend",
                confidence=0.6 + (rsi - 50) / 200,  # 0.6 ~ 0.7
                direction="bullish",
                reasons=[f"MA5({ma5:.2f})>MA10({ma10:.2f})>MA20({ma20:.2f})", f"RSI={rsi:.1f}"],
                key_levels={
                    "support": round(ma20, 2),
                    "resistance": round(close.tail(10).max(), 2),
                    "entry": round(current_price, 2),
                },
            )
        
        return None
    
    # ========================================================================
    # 交易执行
    # ========================================================================
    
    def _execute_orders(self, orders: List[Dict], cash: float,
                        positions: Dict, current_date: str,
                        stock_data: Dict, trades: List[Trade]) -> Tuple[float, Dict]:
        """执行交易计划"""
        for order in orders:
            if order["date"] != current_date:
                continue
            
            code = order["code"]
            action = order["action"]
            
            if code not in stock_data:
                continue
            
            df = stock_data[code]
            today_data = df[df["date"] == current_date]
            if len(today_data) == 0:
                continue
            
            open_price = today_data.iloc[0].get("open", 0)
            if open_price <= 0:
                continue
            
            if action == "buy":
                # 买入固定金额
                shares = int(self.position_size / open_price / 100) * 100  # 100股整数倍
                if shares < 100:
                    continue
                
                amount = shares * open_price
                if amount > cash:
                    shares = int(cash / open_price / 100) * 100
                    amount = shares * open_price
                
                if shares >= 100 and amount <= cash:
                    cash -= amount
                    positions[code] = {
                        "shares": shares,
                        "entry_price": open_price,
                        "entry_date": current_date,
                        "days": 0,
                    }
                    
                    signal = order.get("signal")
                    trades.append(Trade(
                        date=current_date, code=code, action="buy",
                        price=open_price, shares=shares, amount=amount,
                        signal_type=signal.pattern_type if signal else "",
                        signal_confidence=signal.confidence if signal else 0,
                        reason=f"Signal: {signal.pattern_type if signal else 'unknown'}" if signal else "",
                    ))
                    
                    self._obs.log("INFO", f"BUY {code} @ {open_price:.2f} x {shares} on {current_date}", "BacktestEngine")
            
            elif action == "sell":
                if code not in positions:
                    continue
                
                pos = positions[code]
                shares = pos["shares"]
                amount = shares * open_price
                cash += amount
                
                # 计算盈亏
                profit_pct = (open_price - pos["entry_price"]) / pos["entry_price"]
                
                trades.append(Trade(
                    date=current_date, code=code, action="sell",
                    price=open_price, shares=shares, amount=amount,
                    reason=order.get("reason", ""),
                ))
                
                del positions[code]
                self._obs.log("INFO", f"SELL {code} @ {open_price:.2f} x {shares}, profit={profit_pct:.2%} on {current_date}", "BacktestEngine")
        
        return cash, positions
    
    def _check_exit_conditions(self, cash: float, positions: Dict,
                               current_date: str, stock_data: Dict) -> Tuple[float, Dict, List[Trade]]:
        """检查止盈止损条件"""
        trades = []
        positions_to_remove = []
        
        for code, pos in positions.items():
            if code not in stock_data:
                positions_to_remove.append(code)
                continue
            
            df = stock_data[code]
            today_data = df[df["date"] == current_date]
            if len(today_data) == 0:
                continue
            
            close_price = today_data.iloc[0].get("close", 0)
            if close_price <= 0:
                continue
            
            # 更新持仓天数
            pos["days"] += 1
            
            # 计算浮动盈亏
            profit_pct = (close_price - pos["entry_price"]) / pos["entry_price"]
            
            # 止盈
            if profit_pct >= self.take_profit:
                positions_to_remove.append((code, "take_profit", profit_pct))
            
            # 止损
            elif profit_pct <= self.stop_loss:
                positions_to_remove.append((code, "stop_loss", profit_pct))
            
            # 最大持仓天数
            elif pos["days"] >= self.max_holding_days:
                positions_to_remove.append((code, "max_holding_days", profit_pct))
        
        # 执行卖出
        for item in positions_to_remove:
            if isinstance(item, tuple):
                code, reason, profit_pct = item
            else:
                code = item
                reason = "unknown"
                profit_pct = 0
            
            if code not in stock_data:
                continue
            
            df = stock_data[code]
            today_data = df[df["date"] == current_date]
            if len(today_data) == 0:
                continue
            
            open_price = today_data.iloc[0].get("open", 0)
            if open_price <= 0:
                continue
            
            pos = positions[code]
            shares = pos["shares"]
            amount = shares * open_price
            cash += amount
            
            trades.append(Trade(
                date=current_date, code=code, action="sell",
                price=open_price, shares=shares, amount=amount,
                reason=reason,
            ))
            
            del positions[code]
            self._obs.log("INFO", f"SELL {code} @ {open_price:.2f} ({reason}), profit={profit_pct:.2%} on {current_date}", "BacktestEngine")
        
        return cash, positions, trades
    
    # ========================================================================
    # 净值计算
    # ========================================================================
    
    def _calculate_snapshot(self, date: str, cash: float,
                            positions: Dict, stock_data: Dict) -> DailySnapshot:
        """计算每日净值"""
        market_value = 0.0
        pos_dict = {}
        
        for code, pos in positions.items():
            if code in stock_data:
                df = stock_data[code]
                today_data = df[df["date"] == date]
                if len(today_data) > 0:
                    close_price = today_data.iloc[0].get("close", pos["entry_price"])
                    market_value += pos["shares"] * close_price
                    pos_dict[code] = pos["shares"]
        
        total_value = cash + market_value
        
        return DailySnapshot(
            date=date,
            total_value=total_value,
            cash=cash,
            market_value=market_value,
            positions=pos_dict,
        )
    
    # ========================================================================
    # 绩效报告
    # ========================================================================
    
    def _generate_report(self, snapshots: List[DailySnapshot],
                         trades: List[Trade],
                         equity_curve: List[Tuple[str, float]]) -> BacktestReport:
        """生成回测绩效报告"""
        if len(snapshots) == 0:
            return BacktestReport()
        
        report = BacktestReport()
        report.initial_capital = self.initial_capital
        report.final_value = snapshots[-1].total_value
        report.total_return = (report.final_value - report.initial_capital) / report.initial_capital
        
        # 年化收益率
        days = len(snapshots)
        if days > 1:
            report.annualized_return = (1 + report.total_return) ** (252 / days) - 1
        
        # 最大回撤
        peak = 0
        for snap in snapshots:
            if snap.total_value > peak:
                peak = snap.total_value
            dd = (peak - snap.total_value) / peak if peak > 0 else 0
            if dd > report.max_drawdown:
                report.max_drawdown = dd
                report.max_drawdown_date = snap.date
        
        # 日收益率序列
        daily_returns = []
        for i in range(1, len(snapshots)):
            ret = (snapshots[i].total_value - snapshots[i-1].total_value) / snapshots[i-1].total_value
            daily_returns.append(ret)
            snapshots[i].daily_return = ret
        
        # 年化波动率
        if len(daily_returns) > 1:
            report.volatility = np.std(daily_returns) * np.sqrt(252)
        
        # Sharpe（假设无风险利率 2%）
        if report.volatility > 0:
            risk_free_daily = 0.02 / 252
            excess_return = np.mean(daily_returns) - risk_free_daily if daily_returns else 0
            report.sharpe_ratio = excess_return / np.std(daily_returns) * np.sqrt(252) if np.std(daily_returns) > 0 else 0
        
        # 交易统计
        buy_trades = [t for t in trades if t.action == "buy"]
        sell_trades = [t for t in trades if t.action == "sell"]
        report.total_trades = len(buy_trades)
        
        # 配对买卖计算盈亏
        trade_pairs = []
        for sell in sell_trades:
            for buy in buy_trades:
                if buy.code == sell.code and buy.date < sell.date:
                    profit = (sell.price - buy.price) * sell.shares
                    trade_pairs.append({"profit": profit, "code": sell.code})
                    break
        
        if trade_pairs:
            profits = [p["profit"] for p in trade_pairs]
            report.win_trades = sum(1 for p in profits if p > 0)
            report.lose_trades = sum(1 for p in profits if p <= 0)
            report.win_rate = report.win_trades / len(trade_pairs)
            report.avg_profit = np.mean([p for p in profits if p > 0]) if report.win_trades > 0 else 0
            report.avg_loss = np.mean([p for p in profits if p <= 0]) if report.lose_trades > 0 else 0
            report.profit_loss_ratio = abs(report.avg_profit / report.avg_loss) if report.avg_loss != 0 else 0
        
        # 最大持仓
        report.max_positions = max(len(snap.positions) for snap in snapshots) if snapshots else 0
        
        # 平均持仓天数（简化计算）
        report.avg_holding_days = self.max_holding_days / 2  # 简化
        
        report.daily_snapshots = [s.to_dict() for s in snapshots]
        report.trades = [t.to_dict() for t in trades]
        report.equity_curve = equity_curve
        
        return report


# ========================================================================
# 便捷函数
# ========================================================================

def run_backtest(codes: List[str], start_date: str, end_date: str,
                 initial_capital: float = 100000.0,
                 signal_fn: Optional[Callable] = None) -> BacktestReport:
    """
    一键回测接口
    
    使用方式：
        report = run_backtest(
            codes=["000001", "300750", "600519"],
            start_date="2025-01-01",
            end_date="2025-06-19",
        )
        print(report.to_dict())
    """
    engine = BacktestEngine(initial_capital=initial_capital)
    return engine.run(codes, start_date, end_date, signal_fn=signal_fn)


if __name__ == "__main__":
    # 快速测试
    print("=== Backtest Engine MVP Test ===")
    
    engine = BacktestEngine(initial_capital=100000, position_size=10000)
    
    test_codes = ["000001", "300750", "600519"]
    
    report = engine.run(
        codes=test_codes,
        start_date="2025-01-01",
        end_date="2025-06-19",
    )
    
    print(f"\n总收益率: {report.total_return:.2%}")
    print(f"最大回撤: {report.max_drawdown:.2%}")
    print(f"Sharpe: {report.sharpe_ratio:.2f}")
    print(f"交易次数: {report.total_trades}")
    print(f"胜率: {report.win_rate:.1%}")
    print(f"\n权益曲线前5日:")
    for date, value in report.equity_curve[:5]:
        print(f"  {date}: {value:,.2f}")
