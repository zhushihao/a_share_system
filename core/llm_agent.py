"""
LLM Agent v4.0 - 智能增强模块

核心能力：
1. 型态识别增强：LLM 分析 K线+技术指标，输出型态信号
2. 交易建议生成：基于多个信号生成自然语言交易报告
3. 批量分析：支持一次分析多只股票（降低成本）
4. 缓存：LLM 结果缓存，避免重复调用
5. 降级：LLM 不可用时自动降级到规则引擎
6. 可观测性：记录每次 LLM 调用耗时、Token 数、成本

使用方式：
    agent = LLMAnalyzer()
    
    # 单股分析
    signal = agent.analyze_stock(code="000001", klines=df, indicators=indicators)
    
    # 批量分析
    signals = agent.analyze_batch({"000001": df1, "300750": df2})
    
    # 生成交易报告
    report = agent.generate_report(signals, market_regime="强趋势")

降级策略：
    LLM API 失败 → 规则引擎（基于技术指标的决策树）→ 返回基础信号
"""

import json
import time
import threading
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import numpy as np

from core.observability import get_obs
from core.cache import MultiLevelCache


@dataclass
class LLMSignal:
    """LLM 分析型态信号"""
    code: str = ""
    pattern_type: str = ""           # uptrend, downtrend, consolidation, breakout, breakdown
    confidence: float = 0.0          # 0-1
    direction: str = ""              # bullish, bearish, neutral
    reasons: List[str] = field(default_factory=list)
    key_levels: Dict[str, float] = field(default_factory=dict)  # support, resistance, entry, stop_loss
    indicators: Dict[str, Any] = field(default_factory=dict)   # RSI, MACD, MA 等
    llm_used: bool = False           # 是否使用了 LLM
    llm_model: str = ""              # 使用的模型
    llm_cost: float = 0.0            # 调用成本（USD）
    error: str = ""                  # 错误信息
    
    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "pattern_type": self.pattern_type,
            "confidence": round(self.confidence, 2),
            "direction": self.direction,
            "reasons": self.reasons,
            "key_levels": {k: round(v, 2) for k, v in self.key_levels.items()},
            "indicators": self.indicators,
            "llm_used": self.llm_used,
            "llm_model": self.llm_model,
        }


@dataclass
class LLMReport:
    """LLM 生成的交易报告"""
    title: str = ""
    summary: str = ""
    top_signals: List[Dict] = field(default_factory=list)
    market_view: str = ""
    risk_alerts: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)
    llm_used: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "top_signals": self.top_signals,
            "market_view": self.market_view,
            "risk_alerts": self.risk_alerts,
            "opportunities": self.opportunities,
            "llm_used": self.llm_used,
        }


class LLMAnalyzer:
    """
    LLM 型态分析器
    
    设计：
    1. 如果 API key 可用，调用 LLM 进行深度分析
    2. 如果 API 失败或不可用，降级到规则引擎（基于技术指标的决策树）
    3. 所有结果缓存（基于输入数据的 hash）
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "kimi-latest",
                 max_tokens: int = 1000, temperature: float = 0.3):
        self.api_key = api_key or self._get_api_key_from_env()
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._cache = MultiLevelCache()
        self._obs = get_obs()
        self._llm_available = self._check_llm_available()
    
    def _get_api_key_from_env(self) -> Optional[str]:
        """从环境变量获取 API key"""
        import os
        return os.environ.get("KIMI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    
    def _check_llm_available(self) -> bool:
        """检查 LLM API 是否可用"""
        return self.api_key is not None and len(self.api_key) > 10
    
    def _generate_cache_key(self, code: str, data_hash: str) -> str:
        """生成缓存 key"""
        return f"llm:signal:{code}:{data_hash}"
    
    def _compute_data_hash(self, klines: pd.DataFrame, indicators: Optional[Dict] = None) -> str:
        """计算数据 hash（用于缓存）"""
        # 取最近 20 天的收盘价计算 hash
        if len(klines) >= 20:
            closes = klines["close"].tail(20).round(2).tolist()
        else:
            closes = klines["close"].round(2).tolist()
        hash_str = f"{closes}"
        if indicators:
            hash_str += str(sorted(indicators.items()))
        return hashlib.md5(hash_str.encode()).hexdigest()[:16]
    
    # ========================================================================
    # 单股分析
    # ========================================================================
    
    def analyze_stock(self, code: str, klines: pd.DataFrame,
                      indicators: Optional[Dict] = None) -> LLMSignal:
        """
        分析单只股票的型态
        
        Args:
            code: 股票代码
            klines: DataFrame[date, open, high, low, close, volume]
            indicators: 可选，已计算的技术指标
        
        Returns:
            LLMSignal
        """
        # 1. 检查缓存
        data_hash = self._compute_data_hash(klines, indicators)
        cache_key = self._generate_cache_key(code, data_hash)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._obs.log("INFO", f"LLM cache hit for {code}", "LLMAnalyzer")
            return LLMSignal(**cached)
        
        # 2. 计算技术指标（如果没有传入）
        if indicators is None:
            indicators = self._compute_indicators(klines)
        
        # 3. 尝试 LLM 分析
        if self._llm_available:
            try:
                signal = self._call_llm_analyze(code, klines, indicators)
                self._cache.set(cache_key, signal.__dict__, ttl_seconds=3600)
                self._obs.log("INFO", f"LLM analysis completed for {code}, confidence={signal.confidence}", "LLMAnalyzer")
                return signal
            except Exception as e:
                self._obs.log("WARN", f"LLM analysis failed for {code}: {str(e)}, falling back to rule engine", "LLMAnalyzer")
        
        # 4. 降级到规则引擎
        signal = self._rule_engine_analyze(code, klines, indicators)
        self._cache.set(cache_key, signal.__dict__, ttl_seconds=3600)
        self._obs.log("INFO", f"Rule engine analysis for {code}, confidence={signal.confidence}", "LLMAnalyzer")
        return signal
    
    # ========================================================================
    # 批量分析
    # ========================================================================
    
    def analyze_batch(self, stock_dict: Dict[str, pd.DataFrame],
                      max_workers: int = 4) -> Dict[str, LLMSignal]:
        """
        批量分析多只股票
        
        Args:
            stock_dict: {code: klines_df}
            max_workers: 并行工作线程数
        
        Returns:
            {code: LLMSignal}
        """
        import concurrent.futures
        
        results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {
                executor.submit(self.analyze_stock, code, df): code
                for code, df in stock_dict.items()
            }
            
            for future in concurrent.futures.as_completed(future_to_code):
                code = future_to_code[future]
                try:
                    signal = future.result(timeout=60)
                    results[code] = signal
                except Exception as e:
                    self._obs.log("ERROR", f"Batch analysis failed for {code}: {str(e)}", "LLMAnalyzer")
                    results[code] = LLMSignal(code=code, error=str(e))
        
        return results
    
    # ========================================================================
    # 生成交易报告
    # ========================================================================
    
    def generate_report(self, signals: Dict[str, LLMSignal],
                        market_regime: str = "未知") -> LLMReport:
        """
        基于多个信号生成交易报告
        
        Args:
            signals: {code: LLMSignal}
            market_regime: 市场状态
        
        Returns:
            LLMReport
        """
        # 1. 过滤有效信号
        valid_signals = [s for s in signals.values() if s.confidence > 0.5]
        
        # 2. 排序（按置信度）
        valid_signals.sort(key=lambda x: x.confidence, reverse=True)
        top_10 = valid_signals[:10]
        
        # 3. 尝试 LLM 生成报告
        if self._llm_available and len(valid_signals) > 0:
            try:
                return self._call_llm_report(top_10, market_regime)
            except Exception as e:
                self._obs.log("WARN", f"LLM report generation failed: {str(e)}", "LLMAnalyzer")
        
        # 4. 降级到规则引擎生成报告
        return self._rule_engine_report(top_10, market_regime)
    
    # ========================================================================
    # LLM API 调用（实际实现）
    # ========================================================================
    
    def _call_llm_analyze(self, code: str, klines: pd.DataFrame,
                          indicators: Dict) -> LLMSignal:
        """调用 LLM API 分析型态"""
        start_time = time.time()
        
        # 构建 prompt
        prompt = self._build_analyze_prompt(code, klines, indicators)
        
        # 调用 LLM（这里使用 OpenAI 兼容接口）
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key, base_url="https://api.moonshot.cn/v1")
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的A股型态分析师。请基于K线数据和技术指标，分析股票型态并输出JSON格式结果。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            duration = (time.time() - start_time) * 1000
            
            signal = LLMSignal(
                code=code,
                pattern_type=result.get("pattern_type", "unknown"),
                confidence=result.get("confidence", 0.5),
                direction=result.get("direction", "neutral"),
                reasons=result.get("reasons", []),
                key_levels=result.get("key_levels", {}),
                indicators=indicators,
                llm_used=True,
                llm_model=self.model,
                llm_cost=0.0,  # 可计算实际成本
            )
            
            self._obs.record_histogram("llm_analyze_duration_ms", duration, {"code": code})
            return signal
            
        except ImportError:
            raise RuntimeError("openai library not available")
        except Exception as e:
            raise RuntimeError(f"LLM API error: {str(e)}")
    
    def _call_llm_report(self, top_signals: List[LLMSignal],
                         market_regime: str) -> LLMReport:
        """调用 LLM API 生成报告"""
        # 构建 prompt
        signals_summary = "\n".join([
            f"{s.code}: {s.pattern_type} (confidence={s.confidence:.2f}), direction={s.direction}"
            for s in top_signals[:10]
        ])
        
        prompt = f"""基于以下A股型态分析信号，生成一份专业的交易报告。

市场状态: {market_regime}

Top 信号:
{signals_summary}

请输出以下JSON格式:
{{
    "title": "报告标题",
    "summary": "市场综述（100字以内）",
    "market_view": "市场观点（bullish/bearish/neutral）",
    "risk_alerts": ["风险1", "风险2"],
    "opportunities": ["机会1", "机会2"]
}}"""
        
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key, base_url="https://api.moonshot.cn/v1")
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的A股交易分析师。请基于型态信号生成交易报告。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            return LLMReport(
                title=result.get("title", "交易报告"),
                summary=result.get("summary", ""),
                top_signals=[s.to_dict() for s in top_signals[:5]],
                market_view=result.get("market_view", "neutral"),
                risk_alerts=result.get("risk_alerts", []),
                opportunities=result.get("opportunities", []),
                llm_used=True,
            )
            
        except ImportError:
            raise RuntimeError("openai library not available")
        except Exception as e:
            raise RuntimeError(f"LLM report API error: {str(e)}")
    
    # ========================================================================
    # 规则引擎（降级方案）
    # ========================================================================
    
    def _rule_engine_analyze(self, code: str, klines: pd.DataFrame,
                             indicators: Dict) -> LLMSignal:
        """基于技术指标的决策树型态分析"""
        signal = LLMSignal(code=code, indicators=indicators, llm_used=False)
        
        if not indicators:
            signal.pattern_type = "unknown"
            signal.confidence = 0.3
            signal.direction = "neutral"
            signal.reasons = ["指标数据不足"]
            return signal
        
        # 提取关键指标
        ma20 = indicators.get("ma20", 0)
        ma60 = indicators.get("ma60", 0)
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        macd_signal = indicators.get("macd_signal", 0)
        close = indicators.get("close", 0)
        
        # 多头排列判定
        bullish_score = 0
        reasons = []
        
        # 1. 均线趋势
        if ma20 > ma60:
            bullish_score += 2
            reasons.append("短期均线在长期均线上方，趋势偏多")
        elif ma20 < ma60:
            bullish_score -= 2
            reasons.append("短期均线在长期均线下方，趋势偏空")
        
        # 2. RSI
        if rsi > 70:
            bullish_score -= 1
            reasons.append(f"RSI超买({rsi:.1f})")
        elif rsi < 30:
            bullish_score += 1
            reasons.append(f"RSI超卖({rsi:.1f})")
        elif 40 < rsi < 60:
            bullish_score += 0.5
            reasons.append(f"RSI中性({rsi:.1f})")
        
        # 3. MACD
        if macd > macd_signal and macd > 0:
            bullish_score += 2
            reasons.append("MACD金叉且正值，动能偏多")
        elif macd < macd_signal and macd < 0:
            bullish_score -= 2
            reasons.append("MACD死叉且负值，动能偏空")
        
        # 4. 价格位置
        if close > ma20:
            bullish_score += 1
            reasons.append("价格站上20日均线")
        else:
            bullish_score -= 1
            reasons.append("价格低于20日均线")
        
        # 5. 近期涨幅
        if len(klines) >= 5:
            recent_return = (klines["close"].iloc[-1] / klines["close"].iloc[-5] - 1) * 100
            if recent_return > 5:
                bullish_score += 1
                reasons.append(f"近5日涨幅{recent_return:.1f}%")
            elif recent_return < -5:
                bullish_score -= 1
                reasons.append(f"近5日跌幅{abs(recent_return):.1f}%")
        
        # 判定型态
        if bullish_score >= 3:
            signal.pattern_type = "uptrend"
            signal.direction = "bullish"
            signal.confidence = min(0.5 + bullish_score * 0.08, 0.95)
        elif bullish_score <= -3:
            signal.pattern_type = "downtrend"
            signal.direction = "bearish"
            signal.confidence = min(0.5 + abs(bullish_score) * 0.08, 0.95)
        elif -1 <= bullish_score <= 1:
            signal.pattern_type = "consolidation"
            signal.direction = "neutral"
            signal.confidence = 0.5
        else:
            signal.pattern_type = "mixed"
            signal.direction = "neutral" if bullish_score > 0 else "bearish"
            signal.confidence = 0.55
        
        signal.reasons = reasons
        
        # 关键价位
        if len(klines) >= 10:
            signal.key_levels = {
                "support": round(klines["low"].tail(10).min(), 2),
                "resistance": round(klines["high"].tail(10).max(), 2),
                "current": round(close, 2),
            }
        
        return signal
    
    def _rule_engine_report(self, top_signals: List[LLMSignal],
                            market_regime: str) -> LLMReport:
        """基于规则引擎生成报告"""
        bullish_count = sum(1 for s in top_signals if s.direction == "bullish")
        bearish_count = sum(1 for s in top_signals if s.direction == "bearish")
        neutral_count = len(top_signals) - bullish_count - bearish_count
        
        # 市场观点
        if bullish_count > bearish_count * 2:
            market_view = "bullish"
            summary = f"市场情绪偏多，Top {len(top_signals)} 中看涨 {bullish_count} 只，看跌 {bearish_count} 只。"
        elif bearish_count > bullish_count * 2:
            market_view = "bearish"
            summary = f"市场情绪偏空，Top {len(top_signals)} 中看跌 {bearish_count} 只，看涨 {bullish_count} 只。"
        else:
            market_view = "neutral"
            summary = f"市场分歧较大，多空均衡。Top {len(top_signals)} 中看涨 {bullish_count} 只，看跌 {bearish_count} 只。"
        
        # 风险与机会
        risk_alerts = []
        opportunities = []
        
        for s in top_signals[:5]:
            if s.direction == "bearish" and s.confidence > 0.7:
                risk_alerts.append(f"{s.code}: {s.pattern_type} (conf={s.confidence:.2f})")
            elif s.direction == "bullish" and s.confidence > 0.7:
                opportunities.append(f"{s.code}: {s.pattern_type} (conf={s.confidence:.2f})")
        
        return LLMReport(
            title=f"A股市场型态分析报告 ({market_regime})",
            summary=summary,
            top_signals=[s.to_dict() for s in top_signals[:5]],
            market_view=market_view,
            risk_alerts=risk_alerts,
            opportunities=opportunities,
            llm_used=False,
        )
    
    # ========================================================================
    # 技术指标计算
    # ========================================================================
    
    def _compute_indicators(self, klines: pd.DataFrame) -> Dict[str, float]:
        """计算技术指标"""
        if len(klines) == 0:
            return {}
        
        close = klines["close"]
        high = klines["high"]
        low = klines["low"]
        volume = klines["volume"] if "volume" in klines.columns else None
        
        indicators = {
            "close": close.iloc[-1],
            "ma5": close.tail(5).mean() if len(close) >= 5 else close.iloc[-1],
            "ma10": close.tail(10).mean() if len(close) >= 10 else close.iloc[-1],
            "ma20": close.tail(20).mean() if len(close) >= 20 else close.iloc[-1],
            "ma60": close.tail(60).mean() if len(close) >= 60 else close.iloc[-1],
        }
        
        # RSI
        indicators["rsi"] = self._compute_rsi(close)
        
        # MACD
        macd, macd_signal, macd_hist = self._compute_macd(close)
        indicators["macd"] = macd
        indicators["macd_signal"] = macd_signal
        indicators["macd_hist"] = macd_hist
        
        # 波动率
        if len(close) >= 10:
            indicators["volatility"] = close.tail(10).std() / close.tail(10).mean() * 100
        
        # 成交量
        if volume is not None and len(volume) >= 5:
            indicators["volume_ratio"] = volume.tail(5).mean() / volume.tail(20).mean() if len(volume) >= 20 else 1.0
        
        return indicators
    
    def _compute_rsi(self, close: pd.Series, period: int = 14) -> float:
        """计算 RSI"""
        if len(close) < period + 1:
            return 50.0
        
        delta = close.diff()
        gain = delta.where(delta > 0, 0).tail(period)
        loss = (-delta.where(delta < 0, 0)).tail(period)
        
        avg_gain = gain.mean()
        avg_loss = loss.mean()
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _compute_macd(self, close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """计算 MACD"""
        if len(close) < slow + signal:
            return 0.0, 0.0, 0.0
        
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]
    
    # ========================================================================
    # Prompt 构建
    # ========================================================================
    
    def _build_analyze_prompt(self, code: str, klines: pd.DataFrame,
                              indicators: Dict) -> str:
        """构建 LLM 分析 prompt"""
        # 取最近 20 天数据
        recent = klines.tail(20)
        data_summary = "\n".join([
            f"日期: {row['date'] if 'date' in row else i}, "
            f"开: {row['open']:.2f}, 高: {row['high']:.2f}, "
            f"低: {row['low']:.2f}, 收: {row['close']:.2f}, 量: {int(row['volume'])}"
            for i, (_, row) in enumerate(recent.iterrows())
        ])
        
        indicators_str = "\n".join([f"{k}: {v:.2f}" for k, v in indicators.items()])
        
        return f"""请分析股票 {code} 的型态。

最近20日K线数据:
{data_summary}

技术指标:
{indicators_str}

请输出以下JSON格式:
{{
    "pattern_type": "uptrend/downtrend/consolidation/breakout/breakdown",
    "confidence": 0.0-1.0,
    "direction": "bullish/bearish/neutral",
    "reasons": ["理由1", "理由2"],
    "key_levels": {{
        "support": 支撑位价格,
        "resistance": 阻力位价格,
        "entry": 建议入场价格,
        "stop_loss": 建议止损价格
    }}
}}"""


# ========================================================================
# 便捷函数
# ========================================================================

_analyzer_instance: Optional[LLMAnalyzer] = None
_analyzer_lock = threading.Lock()


def get_analyzer() -> LLMAnalyzer:
    """获取全局 LLM Analyzer 实例"""
    global _analyzer_instance
    if _analyzer_instance is None:
        with _analyzer_lock:
            if _analyzer_instance is None:
                _analyzer_instance = LLMAnalyzer()
    return _analyzer_instance


if __name__ == "__main__":
    # 快速测试（使用真实数据，禁用合成数据 per 系统政策）
    print("=== LLM Analyzer Test ===")
    print("System policy: no synthetic data. Loading real data via mootdx...")
    
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend.services.data_provider import DataProviderService
    
    svc = DataProviderService()
    test_df = svc.get_kline_latest("000001", n=60)
    if test_df is None or len(test_df) == 0:
        print("ERROR: No real data available. Cannot proceed with synthetic data (system policy: no fake data).")
        sys.exit(1)
    
    analyzer = LLMAnalyzer()
    
    # 测试单股分析
    signal = analyzer.analyze_stock("000001", test_df)
    print(f"\nSignal: {signal.to_dict()}")
    
    # 测试批量分析
    stock_dict = {
        "000001": test_df,
    }
    signals = analyzer.analyze_batch(stock_dict)
    print(f"\nBatch signals: {len(signals)} stocks analyzed")
    
    # 测试报告生成
    report = analyzer.generate_report(signals, market_regime="震荡")
    print(f"\nReport: {report.to_dict()}")
