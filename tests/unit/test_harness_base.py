"""
单元测试：Harness 基类行为
"""
import pytest
import sys
import os
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.harness import Harness, HarnessConfig, Context, RunMode, ErrorPolicy
from core.observability import ObservabilityEngine


class MockHarness(Harness):
    """模拟 Harness 用于测试"""
    INPUTS = ["input_a", "input_b"]
    OUTPUTS = ["output_a"]
    
    def __init__(self, config: HarnessConfig):
        super().__init__(config)
        self.init_called = False
        self.run_called = False
    
    def init(self, ctx: Context) -> None:
        self.init_called = True
    
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        self.run_called = True
        return {"output_a": inputs.get("input_a", 0) + inputs.get("input_b", 0)}


class FailingHarness(Harness):
    """总是失败的 Harness"""
    INPUTS = []
    OUTPUTS = ["output_fail"]
    
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        raise RuntimeError("Simulated failure")


class TimeoutHarness(Harness):
    """超时的 Harness"""
    INPUTS = []
    OUTPUTS = ["output_timeout"]
    
    def run(self, inputs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        import time
        time.sleep(0.1)
        return {"output_timeout": True}


class TestHarnessBasics:
    """Harness 基础行为测试"""
    
    def test_name_property(self, harness_config):
        h = MockHarness(harness_config)
        assert h.name == "test_harness"
    
    def test_init(self, context, harness_config):
        h = MockHarness(harness_config)
        assert not h._initialized
        h.init(context)
        assert h._initialized
        assert h.init_called
    
    def test_run(self, context, harness_config):
        h = MockHarness(harness_config)
        ctx = context
        ctx.set("input_a", 10)
        ctx.set("input_b", 20)
        
        inputs = ctx.extract(h.INPUTS)
        outputs = h.run(inputs, ctx)
        
        assert outputs == {"output_a": 30}
    
    def test_validate(self, context, harness_config):
        h = MockHarness(harness_config)
        ctx = context
        ctx.set("input_a", 1)
        ctx.set("input_b", 2)
        
        assert h.validate(ctx) is None  # 所有依赖都存在
    
    def test_validate_missing(self, context, harness_config):
        h = MockHarness(harness_config)
        ctx = context
        ctx.set("input_a", 1)
        # input_b 缺失
        
        assert h.validate(ctx) is not None
    
    def test_validate_outputs(self, context, harness_config):
        h = MockHarness(harness_config)
        outputs = {"output_a": 42}
        assert h.validate_outputs(outputs) is None
        
        outputs = {}
        assert h.validate_outputs(outputs) is not None
    
    def test_fallback(self, context, harness_config):
        h = MockHarness(harness_config)
        ctx = context
        outputs = h.fallback({}, ctx)
        assert outputs == {}
    
    def test_pure_function(self, context, harness_config):
        """测试 Harness.run 是纯函数（不修改 ctx）"""
        h = MockHarness(harness_config)
        ctx = context
        ctx.set("input_a", 10)
        ctx.set("input_b", 20)
        
        original_keys = set(ctx.keys())
        inputs = ctx.extract(h.INPUTS)
        outputs = h.run(inputs, ctx)
        after_keys = set(ctx.keys())
        
        assert original_keys == after_keys  # ctx 未被修改
        assert outputs == {"output_a": 30}


class TestHarnessExecution:
    """Harness 执行测试"""
    
    def test_execute_success(self, context, harness_config):
        h = MockHarness(harness_config)
        ctx = context
        ctx.set("input_a", 1)
        ctx.set("input_b", 2)
        
        result = h._execute(ctx)
        
        assert result.success is True
        assert result.name == "test_harness"
        assert result.duration_ms >= 0
        assert "output_a" in result.outputs
    
    def test_execute_failure_terminate(self, context):
        config = HarnessConfig(name="fail", error_policy=ErrorPolicy.TERMINATE)
        h = FailingHarness(config)
        ctx = context
        
        result = h._execute(ctx)
        
        assert result.success is False
        assert result.error is not None
    
    def test_execute_failure_skip(self, context):
        config = HarnessConfig(name="fail", error_policy=ErrorPolicy.SKIP)
        h = FailingHarness(config)
        ctx = context
        
        result = h._execute(ctx)
        
        assert result.success is True  # SKIP 策略下算成功
        assert result.error is not None
    
    def test_execute_failure_fallback(self, context):
        config = HarnessConfig(name="fail", error_policy=ErrorPolicy.FALLBACK)
        h = FailingHarness(config)
        ctx = context
        
        result = h._execute(ctx)
        
        assert result.success is True  # FALLBACK 成功
        assert result.error is not None  # 但记录了原始错误
    
    def test_execute_duration(self, context):
        config = HarnessConfig(name="timeout", error_policy=ErrorPolicy.SKIP)
        h = TimeoutHarness(config)
        ctx = context
        
        result = h._execute(ctx)
        
        assert result.duration_ms >= 100  # 至少100ms
        assert result.success is True


class TestHarnessObservability:
    """Harness 与可观测性集成测试"""
    
    def test_execution_logs(self, context, harness_config):
        obs = ObservabilityEngine()
        obs.reset()
        
        h = MockHarness(harness_config)
        ctx = context
        ctx.set("input_a", 1)
        ctx.set("input_b", 2)
        
        result = h._execute(ctx)
        
        # 检查日志被记录
        logs = ctx.get("_log_entries")
        assert len(logs) >= 3  # init, run, completed
    
    def test_output_keys_recorded(self, context, harness_config):
        h = MockHarness(harness_config)
        ctx = context
        ctx.set("input_a", 1)
        ctx.set("input_b", 2)
        
        result = h._execute(ctx)
        
        assert "output_a" in result.outputs
