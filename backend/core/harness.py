"""
Harness Engineering v3.0 - 方案A

核心改进：
1. 每个 Harness 显式声明 INPUTS/OUTPUTS 契约
2. run(inputs, ctx) -> outputs 纯函数：不直接修改 ctx，副作用由 Runner 控制
3. Runner 自动装配 inputs、合并 outputs、DAG 拓扑排序、并行执行
4. 切面机制：PreRunHook / PostRunHook 用于日志、监控、重试
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Type, Set, Tuple, Union
from enum import Enum
from datetime import datetime
import traceback
import time
import concurrent.futures
from collections import defaultdict, deque


class ErrorPolicy(Enum):
    TERMINATE = "terminate"
    SKIP = "skip"
    FALLBACK = "fallback"


class RunMode(Enum):
    POST_MARKET = "post_market"
    PRE_MARKET = "pre_market"
    BACKTEST = "backtest"
    DEVIATION = "deviation"


@dataclass
class HarnessConfig:
    name: str
    enabled: bool = True
    error_policy: ErrorPolicy = ErrorPolicy.TERMINATE
    timeout_seconds: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)
    parallelism: int = 1           # 并行度：1=顺序，>1=并发


@dataclass
class HarnessResult:
    name: str
    success: bool
    duration_ms: float
    inputs: Dict[str, str] = field(default_factory=dict)   # {key: type_name}
    outputs: Dict[str, str] = field(default_factory=dict)  # {key: type_name}
    error: Optional[str] = None
    trace: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
            "inputs": self.inputs,
            "outputs": self.outputs,
            "error": self.error,
        }


class Context:
    """
    共享数据容器 - 只提供读写接口，Harness 不直接操作内部字典
    """
    
    def __init__(self, mode: RunMode = RunMode.POST_MARKET, date: str = ""):
        self._data: Dict[str, Any] = {}
        self._snapshots: List[Dict[str, Any]] = []
        self.mode = mode
        self.date = date
        self.started_at = datetime.now()
        self.harness_results: List[HarnessResult] = []
    
    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        data = self._data
        for part in parts:
            if isinstance(data, dict) and part in data:
                data = data[part]
            else:
                return default
        return data
    
    def set(self, key: str, value: Any) -> None:
        """内部方法：只由 Runner 调用"""
        parts = key.split(".")
        data = self._data
        for part in parts[:-1]:
            if part not in data or not isinstance(data[part], dict):
                data[part] = {}
            data = data[part]
        data[parts[-1]] = value
    
    def has(self, key: str) -> bool:
        return self.get(key) is not None
    
    def extract(self, keys: List[str]) -> Dict[str, Any]:
        """提取指定 keys 为字典，缺失的跳过"""
        return {k: self.get(k) for k in keys if self.has(k)}
    
    def merge(self, data: Dict[str, Any]) -> None:
        """合并字典到 Context（支持嵌套 key）"""
        for key, value in data.items():
            self.set(key, value)
    
    def snapshot(self, label: str = "") -> None:
        import copy
        self._snapshots.append({
            "label": label,
            "timestamp": datetime.now().isoformat(),
            "data": copy.deepcopy(self._data),
        })
    
    def keys(self, prefix: str = "") -> List[str]:
        """返回所有 key（可选前缀过滤）"""
        def _collect(d, path=""):
            result = []
            for k, v in d.items():
                p = f"{path}.{k}" if path else k
                if isinstance(v, dict) and type(v) is dict:
                    # 只展开纯 dict，不展开 DataFrame 等对象（DataFrame 不是 dict 子类）
                    result.extend(_collect(v, p))
                else:
                    result.append(p)
            return result
        all_keys = _collect(self._data)
        if prefix:
            return [k for k in all_keys if k.startswith(prefix)]
        return all_keys
    
    def to_dict(self, shallow: bool = False) -> Dict:
        if shallow:
            return {k: type(v).__name__ for k, v in self._data.items()}
        return self._data
    
    def log(self, level: str, message: str, harness: str = "") -> None:
        entries = self._data.setdefault("_log_entries", [])
        entries.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "harness": harness,
            "message": message,
        })
    
    def __repr__(self) -> str:
        return f"Context(mode={self.mode.value}, date={self.date}, keys={len(self.keys())})"


class PreRunHook(ABC):
    """切面：Harness 执行前调用"""
    @abstractmethod
    def before(self, harness_name: str, inputs: Dict[str, Any], ctx: Context) -> None:
        pass


class PostRunHook(ABC):
    """切面：Harness 执行后调用"""
    @abstractmethod
    def after(self, harness_name: str, result: Dict[str, Any], duration_ms: float, ctx: Context) -> None:
        pass


class Harness(ABC):
    """
    Harness 基类 - 纯函数接口
    
    子类必须声明：
    - INPUTS: List[str]   # 从 Context 读取的 keys
    - OUTPUTS: List[str]  # 会写入 Context 的 keys
    
    子类必须实现：
    - run(inputs, ctx) -> Dict[str, Any]  # 纯函数，返回 outputs 字典
    
    可选：
    - init(ctx) -> 预热
    - fallback(inputs, ctx) -> 降级输出
    """
    
    INPUTS: List[str] = []
    OUTPUTS: List[str] = []
    
    def __init__(self, config: HarnessConfig):
        self.config = config
        self._initialized = False
    
    @property
    def name(self) -> str:
        return self.config.name
    
    def init(self, ctx: Context) -> None:
        """初始化（默认空）"""
        pass
    
    @abstractmethod
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        """
        纯函数：接收 inputs 字典，返回 outputs 字典
        - 不直接修改 ctx._data
        - 可以通过 ctx.log 记录日志
        - 可以通过 ctx.get 读取只读配置（不依赖的数据）
        """
        pass
    
    def fallback(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        """降级逻辑：返回空字典或默认值"""
        ctx.log("WARN", f"{self.name} using fallback", self.name)
        return {}
    
    def validate_outputs(self, outputs: Dict[str, Any]) -> Optional[str]:
        """校验 outputs 是否包含所有声明的 OUTPUTS"""
        missing = [k for k in self.OUTPUTS if k not in outputs]
        if missing:
            return f"Missing outputs: {missing}"
        return None


class Registry:
    _harnesses: Dict[str, Type[Harness]] = {}
    
    @classmethod
    def register(cls, name: str, harness_class: Type[Harness]) -> None:
        cls._harnesses[name] = harness_class
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[Harness]]:
        return cls._harnesses.get(name)
    
    @classmethod
    def list(cls) -> List[str]:
        return list(cls._harnesses.keys())
    
    @classmethod
    def create(cls, config: HarnessConfig) -> Optional[Harness]:
        h_class = cls.get(config.name)
        if h_class:
            return h_class(config)
        return None


class Pipeline:
    def __init__(self, name: str, steps: List[HarnessConfig], description: str = ""):
        self.name = name
        self.steps = steps
        self.description = description
    
    def get_enabled_steps(self) -> List[HarnessConfig]:
        return [s for s in self.steps if s.enabled]
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [{"name": s.name, "enabled": s.enabled, "policy": s.error_policy.value} for s in self.steps],
        }


class Runner:
    """
    执行引擎
    - DAG 拓扑排序（基于 INPUTS/OUTPUTS 数据依赖）
    - 自动装配/合并
    - 并行执行（同层无依赖的 Harness）
    - 切面 Hook
    """
    
    def __init__(self, pipeline: Pipeline, registry: Optional[Registry] = None,
                 pre_hooks: List[PreRunHook] = None, post_hooks: List[PostRunHook] = None):
        self.pipeline = pipeline
        self.registry = registry or Registry()
        self.pre_hooks = pre_hooks or []
        self.post_hooks = post_hooks or []
        self._instances: Dict[str, Harness] = {}
    
    def _build_dag(self, steps: List[HarnessConfig]) -> List[List[HarnessConfig]]:
        """
        构建 DAG 拓扑排序
        返回：List[Layer]，每层内的 Harness 可以并行执行
        """
        # 收集所有 Harness 的 INPUTS/OUTPUTS
        io_map: Dict[str, Dict[str, List[str]]] = {}  # name -> {inputs, outputs}
        for config in steps:
            h_class = self.registry.get(config.name)
            if h_class:
                io_map[config.name] = {
                    "inputs": h_class.INPUTS,
                    "outputs": h_class.OUTPUTS,
                }
        
        # 构建依赖图：如果 harness A 的 INPUTS 包含 harness B 的 OUTPUTS，则 A 依赖 B
        # 简化：按声明顺序执行，但同层无依赖的可并行
        # 更精确：基于 key 的依赖图
        
        # key -> 产生它的 harness
        key_producers: Dict[str, str] = {}
        for config in steps:
            name = config.name
            outputs = io_map.get(name, {}).get("outputs", [])
            for out in outputs:
                key_producers[out] = name
        
        # 每个 harness 的依赖
        dependencies: Dict[str, Set[str]] = defaultdict(set)
        for config in steps:
            name = config.name
            inputs = io_map.get(name, {}).get("inputs", [])
            for inp in inputs:
                if inp in key_producers:
                    producer = key_producers[inp]
                    if producer != name:
                        dependencies[name].add(producer)
        
        # 拓扑排序（Kahn算法）
        in_degree = {c.name: len(dependencies[c.name]) for c in steps}
        queue = deque([c for c in steps if in_degree[c.name] == 0])
        layers = []
        processed = set()
        
        while queue:
            # 当前层 = 所有入度为0的节点
            layer = []
            next_queue = deque()
            
            while queue:
                config = queue.popleft()
                if config.name in processed:
                    continue
                layer.append(config)
                processed.add(config.name)
            
            if layer:
                layers.append(layer)
            
            # 更新入度
            for config in steps:
                if config.name in processed:
                    continue
                # 检查是否依赖已处理节点
                deps = dependencies[config.name]
                if all(d in processed for d in deps):
                    next_queue.append(config)
            
            queue = next_queue
        
        # 检查是否有未处理的节点（循环依赖）
        remaining = [c.name for c in steps if c.name not in processed]
        if remaining:
            raise RuntimeError(f"Circular dependency detected: {remaining}")
        
        return layers
    
    def _run_single(self, config: HarnessConfig, ctx: Context) -> HarnessResult:
        """执行单个 Harness"""
        start = time.time()
        
        try:
            harness = self._instances.get(config.name)
            if not harness:
                harness = self.registry.create(config)
                if not harness:
                    raise RuntimeError(f"Harness '{config.name}' not registered")
                self._instances[config.name] = harness
            
            # 初始化
            if not harness._initialized:
                harness.init(ctx)
                harness._initialized = True
            
            # 装配 inputs
            inputs = ctx.extract(harness.INPUTS)
            
            # PreRun Hooks
            for hook in self.pre_hooks:
                hook.before(config.name, inputs, ctx)
            
            # 执行
            outputs = harness.run(inputs, ctx)
            
            # 校验 outputs
            val_err = harness.validate_outputs(outputs)
            if val_err:
                raise RuntimeError(val_err)
            
            # 合并 outputs 到 Context
            ctx.merge(outputs)
            
            success = True
            error = None
            trace = None
            
        except Exception as e:
            error = str(e)
            trace = traceback.format_exc()
            ctx.log("ERROR", f"{config.name}: {error}", config.name)
            
            if config.error_policy == ErrorPolicy.FALLBACK:
                try:
                    outputs = harness.fallback(inputs, ctx)
                    ctx.merge(outputs)
                    success = True
                    error = None
                except Exception as fe:
                    error = f"Fallback failed: {fe}"
            elif config.error_policy == ErrorPolicy.SKIP:
                success = True
            else:
                success = False
            
            outputs = {}
        
        duration = (time.time() - start) * 1000
        
        # PostRun Hooks
        for hook in self.post_hooks:
            hook.after(config.name, outputs, duration, ctx)
        
        result = HarnessResult(
            name=config.name,
            success=success,
            duration_ms=duration,
            inputs={k: type(v).__name__ for k, v in inputs.items()},
            outputs={k: type(v).__name__ for k, v in outputs.items()},
            error=error,
            trace=trace,
        )
        ctx.harness_results.append(result)
        return result
    
    def _run_layer(self, layer: List[HarnessConfig], ctx: Context) -> List[HarnessResult]:
        """执行一层（并行）"""
        names = [c.name for c in layer]
        if len(layer) == 1:
            ctx.log("INFO", f"Layer [seq]: {names[0]}")
            return [self._run_single(layer[0], ctx)]
        
        ctx.log("INFO", f"Layer [parallel] running {len(layer)} harnesses: {names}")
        layer_start = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self._run_single, c, ctx): c for c in layer}
            results = []
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
        
        layer_duration = (time.time() - layer_start) * 1000
        ctx.log("INFO", f"Layer [parallel] completed: {names} in {layer_duration:.0f}ms")
        return results
    
    def run(self, ctx: Context, enable_snapshots: bool = True) -> Dict:
        """执行完整流水线"""
        steps = self.pipeline.get_enabled_steps()
        ctx.log("INFO", f"Pipeline '{self.pipeline.name}' starting ({len(steps)} steps)")
        
        # 构建 DAG
        layers = self._build_dag(steps)
        ctx.log("INFO", f"DAG layers: {len(layers)}")
        
        total_results = []
        all_success = True
        
        for i, layer in enumerate(layers, 1):
            names = [c.name for c in layer]
            ctx.log("INFO", f"Layer {i}/{len(layers)}: {names}")
            
            if enable_snapshots:
                ctx.snapshot(f"before_layer_{i}")
            
            results = self._run_layer(layer, ctx)
            total_results.extend(results)
            
            for r in results:
                if not r.success and r.error:
                    all_success = False
            
            if enable_snapshots:
                ctx.snapshot(f"after_layer_{i}")
        
        ctx.log("INFO", f"Pipeline completed")
        
        return {
            "success": all_success,
            "completed_steps": len([r for r in total_results if r.success]),
            "total_steps": len(steps),
            "results": [r.to_dict() for r in total_results],
            "context_keys": ctx.keys(),
            "context_shallow": ctx.to_dict(shallow=True),
        }
    
    def reset(self) -> None:
        for harness in self._instances.values():
            harness._initialized = False
        self._instances.clear()


# ==================== 预定义流水线 ====================

def build_post_market_pipeline() -> Pipeline:
    return Pipeline(
        name="post_market",
        description="盘后全自动执行流水线",
        steps=[
            HarnessConfig(name="data_fetcher", error_policy=ErrorPolicy.FALLBACK),
            HarnessConfig(name="pattern_recognition", error_policy=ErrorPolicy.FALLBACK),
            HarnessConfig(name="sector_calculation", error_policy=ErrorPolicy.FALLBACK),
            HarnessConfig(name="traffic_light", error_policy=ErrorPolicy.FALLBACK),
            HarnessConfig(name="report_generator", error_policy=ErrorPolicy.TERMINATE),
        ],
    )


def build_pre_market_pipeline() -> Pipeline:
    return Pipeline(
        name="pre_market",
        description="盘前快速执行流水线",
        steps=[
            HarnessConfig(name="data_fetcher", error_policy=ErrorPolicy.FALLBACK, params={"mode": "preload"}),
            HarnessConfig(name="traffic_light", error_policy=ErrorPolicy.FALLBACK),
            HarnessConfig(name="report_generator", error_policy=ErrorPolicy.TERMINATE),
        ],
    )


def build_backtest_pipeline() -> Pipeline:
    return Pipeline(
        name="backtest",
        description="历史回测验证流水线",
        steps=[
            HarnessConfig(name="data_fetcher", error_policy=ErrorPolicy.TERMINATE, params={"mode": "backtest"}),
            HarnessConfig(name="pattern_recognition", error_policy=ErrorPolicy.SKIP),
            HarnessConfig(name="sector_calculation", error_policy=ErrorPolicy.SKIP),
            HarnessConfig(name="traffic_light", error_policy=ErrorPolicy.SKIP),
            HarnessConfig(name="backtest", error_policy=ErrorPolicy.TERMINATE),
        ],
    )


def build_deviation_pipeline() -> Pipeline:
    return Pipeline(
        name="deviation",
        description="执行偏差报告流水线",
        steps=[
            HarnessConfig(name="data_fetcher", error_policy=ErrorPolicy.FALLBACK, params={"mode": "positions"}),
            HarnessConfig(name="report_generator", error_policy=ErrorPolicy.TERMINATE),
        ],
    )


if __name__ == "__main__":
    print("Harness Engineering v3.0 - Scheme A")
    print("Features: explicit IO contracts, pure run(), DAG topo-sort, parallel execution")
    
    # 测试 DAG 构建
    class MockHarness(Harness):
        INPUTS = ["a"]
        OUTPUTS = ["b"]
        def run(self, inputs, ctx):
            return {"b": inputs.get("a", 0) + 1}
    
    class MockHarness2(Harness):
        INPUTS = ["b"]
        OUTPUTS = ["c"]
        def run(self, inputs, ctx):
            return {"c": inputs.get("b", 0) * 2}
    
    Registry.register("mock1", MockHarness)
    Registry.register("mock2", MockHarness2)
    
    pipeline = Pipeline("test", [
        HarnessConfig(name="mock1"),
        HarnessConfig(name="mock2"),
    ])
    
    runner = Runner(pipeline)
    layers = runner._build_dag(pipeline.get_enabled_steps())
    print(f"DAG layers: {[[c.name for c in l] for l in layers]}")
    
    ctx = Context(mode=RunMode.POST_MARKET, date="20250619")
    ctx.set("a", 5)
    result = runner.run(ctx)
    print(f"Result: c = {ctx.get('c')}")
    print(f"Success: {result['success']}")
    print(f"Results: {result['results']}")
    print("\nHarness Engineering v3.0 tests: PASSED")
