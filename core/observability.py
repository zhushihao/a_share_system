"""
Observability System v4.0 - 可观测性引擎

能力：
1. 结构化日志（Structured Logging）- JSON格式，分级输出
2. 指标收集（Metrics）- 延迟/成功率/吞吐量/自定义指标
3. 链路追踪（Tracing）- 跨Harness调用链，瀑布图
4. 数据血缘（Data Lineage）- 每个output记录来源Harness
5. 数据质量评分（Data Quality Score）- 完整性/时效性/一致性

设计理念：在Harness执行流中自动注入，无需修改业务逻辑
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Union
from datetime import datetime, timedelta
from enum import Enum
import json
import time
import threading
import statistics


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"


class MetricType(Enum):
    COUNTER = "counter"      # 累计计数（如总请求数）
    GAUGE = "gauge"          # 瞬时值（如当前内存）
    HISTOGRAM = "histogram"  # 分布值（如延迟分布）
    SUMMARY = "summary"      # 摘要（如平均/分位值）


@dataclass
class Span:
    """链路追踪中的单个跨度（Span）"""
    name: str                    # Harness 名称
    span_id: str
    parent_id: Optional[str] = None
    start_time: float = 0.0    # 时间戳（秒）
    end_time: float = 0.0
    status: str = "ok"         # ok / error / timeout
    tags: Dict[str, str] = field(default_factory=dict)
    
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


@dataclass
class Trace:
    """完整链路追踪"""
    trace_id: str
    pipeline_name: str
    start_time: float
    end_time: float = 0.0
    spans: List[Span] = field(default_factory=list)
    status: str = "ok"
    
    def to_dict(self) -> Dict:
        return {
            "trace_id": self.trace_id,
            "pipeline": self.pipeline_name,
            "duration_ms": round((self.end_time - self.start_time) * 1000, 2),
            "status": self.status,
            "spans": [
                {
                    "name": s.name,
                    "duration_ms": round(s.duration_ms(), 2),
                    "status": s.status,
                    "tags": s.tags,
                }
                for s in self.spans
            ],
        }


@dataclass
class LogEntry:
    """结构化日志条目"""
    timestamp: str
    level: str
    harness: str
    trace_id: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)


@dataclass
class Metric:
    """指标记录"""
    name: str
    type: str
    value: Union[int, float]
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class DataLineage:
    """数据血缘记录"""
    key: str                          # Context key
    produced_by: str                  # 产生该数据的 Harness
    consumed_by: List[str] = field(default_factory=list)  # 消费该数据的 Harnesses
    timestamp: str = ""
    data_type: str = ""              # 数据类型（如 DataFrame, list, dict）
    size_approx: int = 0             # 数据大小（估算）
    
    def to_dict(self) -> Dict:
        return {
            "key": self.key,
            "produced_by": self.produced_by,
            "consumed_by": self.consumed_by,
            "data_type": self.data_type,
            "size_approx": self.size_approx,
        }


@dataclass
class DataQualityReport:
    """数据质量评分报告"""
    harness_name: str
    key: str
    completeness: float = 0.0      # 完整性（0-1，缺失值比例）
    freshness: float = 0.0         # 时效性（0-1，数据最后更新时间）
    consistency: float = 0.0       # 一致性（0-1，多数据源对比）
    availability: float = 0.0      # 可用性（0-1，接口响应时间）
    overall_score: float = 0.0     # 综合评分（0-100）
    issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "harness": self.harness_name,
            "key": self.key,
            "completeness": round(self.completeness, 3),
            "freshness": round(self.freshness, 3),
            "consistency": round(self.consistency, 3),
            "availability": round(self.availability, 3),
            "overall_score": round(self.overall_score, 1),
            "issues": self.issues,
        }


class ObservabilityEngine:
    """
    可观测性引擎 - 单例模式
    
    使用方式：
    1. 在 Runner 中实例化并注入
    2. 自动收集所有 Harness 的执行数据
    3. 提供查询接口用于调试和报告
    """
    
    _instance: Optional["ObservabilityEngine"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "ObservabilityEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance
    
    def _init(self) -> None:
        self._logs: List[LogEntry] = []
        self._metrics: List[Metric] = []
        self._traces: Dict[str, Trace] = {}
        self._lineage: Dict[str, DataLineage] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        
        # 统计摘要
        self._harness_latencies: Dict[str, List[float]] = {}
        self._harness_success_rates: Dict[str, List[bool]] = {}
        
        self._log_lock = threading.Lock()
        self._metric_lock = threading.Lock()
        self._trace_lock = threading.Lock()
    
    # ==================== 日志 ====================
    
    def log(self, level: str, message: str, harness: str = "", 
            trace_id: str = "", context: Dict = None) -> None:
        """记录结构化日志"""
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            harness=harness,
            trace_id=trace_id,
            message=message,
            context=context or {},
        )
        with self._log_lock:
            self._logs.append(entry)
    
    def get_logs(self, harness: str = "", level: str = "", 
                 limit: int = 100) -> List[LogEntry]:
        """查询日志"""
        with self._log_lock:
            logs = self._logs[:]
        if harness:
            logs = [l for l in logs if l.harness == harness]
        if level:
            logs = [l for l in logs if l.level == level]
        return logs[-limit:]
    
    # ==================== 指标 ====================
    
    def record_counter(self, name: str, value: int = 1, 
                       labels: Dict[str, str] = None) -> None:
        """计数器指标"""
        key = self._metric_key(name, labels)
        with self._metric_lock:
            self._counters[key] = self._counters.get(key, 0) + value
            self._metrics.append(Metric(
                name=name, type="counter", value=self._counters[key],
                labels=labels or {}, timestamp=datetime.now().isoformat(),
            ))
    
    def record_gauge(self, name: str, value: float,
                     labels: Dict[str, str] = None) -> None:
        """瞬时值指标"""
        key = self._metric_key(name, labels)
        with self._metric_lock:
            self._gauges[key] = value
            self._metrics.append(Metric(
                name=name, type="gauge", value=value,
                labels=labels or {}, timestamp=datetime.now().isoformat(),
            ))
    
    def record_histogram(self, name: str, value: float,
                         labels: Dict[str, str] = None) -> None:
        """直方图指标（记录分布）"""
        key = self._metric_key(name, labels)
        with self._metric_lock:
            if key not in self._histograms:
                self._histograms[key] = []
            self._histograms[key].append(value)
            self._metrics.append(Metric(
                name=name, type="histogram", value=value,
                labels=labels or {}, timestamp=datetime.now().isoformat(),
            ))
    
    def _metric_key(self, name: str, labels: Dict) -> str:
        """生成指标唯一键"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}#{label_str}"
    
    def get_histogram_stats(self, name: str, labels: Dict = None) -> Dict:
        """获取直方图统计"""
        key = self._metric_key(name, labels)
        with self._metric_lock:
            values = self._histograms.get(key, [])
        if not values:
            return {}
        values.sort()
        return {
            "count": len(values),
            "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "p95": round(values[int(len(values) * 0.95)], 2),
            "p99": round(values[int(len(values) * 0.99)], 2),
            "min": round(values[0], 2),
            "max": round(values[-1], 2),
        }
    
    def get_metric_summary(self, name: str) -> Dict:
        """获取指标汇总"""
        with self._metric_lock:
            metrics = [m for m in self._metrics if m.name == name]
        if not metrics:
            return {}
        return {
            "name": name,
            "count": len(metrics),
            "latest": metrics[-1].value,
            "type": metrics[0].type,
        }
    
    # ==================== 链路追踪 ====================
    
    def start_trace(self, trace_id: str, pipeline_name: str) -> Trace:
        """开始一条追踪链路"""
        trace = Trace(
            trace_id=trace_id,
            pipeline_name=pipeline_name,
            start_time=time.time(),
        )
        with self._trace_lock:
            self._traces[trace_id] = trace
        return trace
    
    def start_span(self, trace_id: str, name: str, 
                   parent_id: Optional[str] = None,
                   tags: Dict[str, str] = None) -> Span:
        """开始一个Span"""
        span = Span(
            name=name,
            span_id=f"{trace_id}-{name}-{time.time()}",
            parent_id=parent_id,
            start_time=time.time(),
            tags=tags or {},
        )
        with self._trace_lock:
            if trace_id in self._traces:
                self._traces[trace_id].spans.append(span)
        return span
    
    def finish_span(self, trace_id: str, span: Span, 
                    status: str = "ok") -> None:
        """完成一个Span"""
        span.end_time = time.time()
        span.status = status
        with self._trace_lock:
            if trace_id in self._traces:
                # 记录延迟到统计
                latency = span.duration_ms()
                self._record_harness_latency(span.name, latency)
                self._record_harness_success(span.name, status == "ok")
    
    def finish_trace(self, trace_id: str, status: str = "ok") -> None:
        """完成一条追踪链路"""
        with self._trace_lock:
            if trace_id in self._traces:
                self._traces[trace_id].end_time = time.time()
                self._traces[trace_id].status = status
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """获取追踪链路"""
        with self._trace_lock:
            return self._traces.get(trace_id)
    
    # ==================== 数据血缘 ====================
    
    def record_lineage(self, key: str, produced_by: str,
                       data_type: str = "", size_approx: int = 0) -> None:
        """记录数据血缘"""
        if key not in self._lineage:
            self._lineage[key] = DataLineage(
                key=key, produced_by=produced_by,
                timestamp=datetime.now().isoformat(),
                data_type=data_type, size_approx=size_approx,
            )
    
    def record_consumption(self, key: str, consumed_by: str) -> None:
        """记录数据消费"""
        if key in self._lineage:
            if consumed_by not in self._lineage[key].consumed_by:
                self._lineage[key].consumed_by.append(consumed_by)
    
    def get_lineage(self, key: str = "") -> List[DataLineage]:
        """获取数据血缘"""
        if key:
            return [self._lineage[key]] if key in self._lineage else []
        return list(self._lineage.values())
    
    def get_lineage_graph(self) -> Dict:
        """获取血缘关系图（用于可视化）"""
        nodes = set()
        edges = []
        for lineage in self._lineage.values():
            nodes.add(lineage.produced_by)
            nodes.add(lineage.key)
            for consumer in lineage.consumed_by:
                nodes.add(consumer)
                edges.append({
                    "from": lineage.produced_by,
                    "to": consumer,
                    "key": lineage.key,
                })
        return {"nodes": list(nodes), "edges": edges}
    
    # ==================== 数据质量 ====================
    
    def evaluate_data_quality(self, harness_name: str, key: str,
                              data: Any) -> DataQualityReport:
        """评估数据质量"""
        report = DataQualityReport(harness_name=harness_name, key=key)
        
        # 完整性检查
        if isinstance(data, dict):
            report.completeness = 1.0 if data else 0.0
        elif hasattr(data, "__len__"):
            report.completeness = 1.0 if len(data) > 0 else 0.0
        else:
            report.completeness = 1.0 if data is not None else 0.0
        
        # 大小估算
        try:
            import sys
            report.size_approx = sys.getsizeof(data)
        except:
            pass
        
        # 时效性（默认当前数据为最新）
        report.freshness = 1.0
        
        # 综合评分
        report.overall_score = (
            report.completeness * 30 +
            report.freshness * 30 +
            report.consistency * 20 +
            report.availability * 20
        )
        
        # 检查问题
        if report.completeness < 0.5:
            report.issues.append(f"数据不完整: completeness={report.completeness:.2f}")
        if report.overall_score < 60:
            report.issues.append(f"数据质量低: score={report.overall_score:.1f}")
        
        return report
    
    # ==================== 统计摘要 ====================
    
    def _record_harness_latency(self, name: str, duration_ms: float) -> None:
        if name not in self._harness_latencies:
            self._harness_latencies[name] = []
        self._harness_latencies[name].append(duration_ms)
    
    def _record_harness_success(self, name: str, success: bool) -> None:
        if name not in self._harness_success_rates:
            self._harness_success_rates[name] = []
        self._harness_success_rates[name].append(success)
    
    def get_harness_stats(self, name: str) -> Dict:
        """获取Harness统计摘要"""
        latencies = self._harness_latencies.get(name, [])
        successes = self._harness_success_rates.get(name, [])
        
        stats = {
            "name": name,
            "total_runs": len(latencies),
        }
        
        if latencies:
            stats["avg_latency_ms"] = round(statistics.mean(latencies), 2)
            stats["median_latency_ms"] = round(statistics.median(latencies), 2)
            stats["p95_latency_ms"] = round(latencies[int(len(latencies) * 0.95)], 2) if len(latencies) >= 20 else round(max(latencies), 2)
        
        if successes:
            stats["success_rate"] = round(sum(successes) / len(successes), 4)
        
        return stats
    
    def get_all_harness_stats(self) -> List[Dict]:
        """获取所有Harness统计"""
        names = set(self._harness_latencies.keys()) | set(self._harness_success_rates.keys())
        return [self.get_harness_stats(n) for n in names]
    
    # ==================== 导出 ====================
    
    def export_full_report(self) -> Dict:
        """导出完整可观测性报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "harness_stats": self.get_all_harness_stats(),
            "lineage_graph": self.get_lineage_graph(),
            "traces": [t.to_dict() for t in self._traces.values()],
            "log_count": len(self._logs),
            "metric_count": len(self._metrics),
        }
    
    def reset(self) -> None:
        """重置所有数据（用于测试）"""
        self._init()


# ==================== 便捷函数 ====================

def get_obs() -> ObservabilityEngine:
    """获取可观测性引擎实例"""
    return ObservabilityEngine()


if __name__ == "__main__":
    # 快速测试
    obs = get_obs()
    
    # 测试日志
    obs.log("INFO", "System started", "system")
    obs.log("INFO", "Data loaded", "data_fetcher", trace_id="trace-1")
    
    # 测试指标
    obs.record_histogram("harness_latency_ms", 1500, {"name": "data_fetcher"})
    obs.record_histogram("harness_latency_ms", 2000, {"name": "data_fetcher"})
    obs.record_counter("pipeline_runs", 1)
    
    # 测试链路追踪
    trace = obs.start_trace("trace-1", "post_market")
    span = obs.start_span("trace-1", "data_fetcher")
    time.sleep(0.01)
    obs.finish_span("trace-1", span, "ok")
    obs.finish_trace("trace-1", "ok")
    
    # 测试血缘
    obs.record_lineage("stock_data", "data_fetcher", "dict", 1024)
    obs.record_consumption("stock_data", "pattern_recognition")
    obs.record_consumption("stock_data", "sector_calculation")
    
    # 测试质量
    report = obs.evaluate_data_quality("data_fetcher", "stock_data", {"a": 1})
    
    # 导出报告
    full = obs.export_full_report()
    print(json.dumps(full, ensure_ascii=False, indent=2, default=str))
    
    print(f"\nHarness stats: {obs.get_all_harness_stats()}")
    print(f"Histogram stats: {obs.get_histogram_stats('harness_latency_ms', {'name': 'data_fetcher'})}")
    print(f"Lineage: {obs.get_lineage()}")
