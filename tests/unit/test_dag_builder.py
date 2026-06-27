"""
单元测试：DAG 构建
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.harness import Runner, Pipeline, Harness, HarnessConfig, Context, Registry, ErrorPolicy


class A_Harness(Harness):
    INPUTS = []
    OUTPUTS = ["a"]
    def run(self, inputs, ctx):
        return {"a": 1}

class B_Harness(Harness):
    INPUTS = ["a"]
    OUTPUTS = ["b"]
    def run(self, inputs, ctx):
        return {"b": inputs.get("a", 0) + 1}

class C_Harness(Harness):
    INPUTS = ["b"]
    OUTPUTS = ["c"]
    def run(self, inputs, ctx):
        return {"c": inputs.get("b", 0) + 1}

class D_Harness(Harness):
    INPUTS = ["a"]
    OUTPUTS = ["d"]
    def run(self, inputs, ctx):
        return {"d": inputs.get("a", 0) * 2}

class E_Harness(Harness):
    INPUTS = ["c", "d"]
    OUTPUTS = ["e"]
    def run(self, inputs, ctx):
        return {"e": inputs.get("c", 0) + inputs.get("d", 0)}


class TestDagBuilder:
    """DAG 构建测试"""
    
    @pytest.fixture(autouse=True)
    def setup_registry(self):
        Registry.register("A", A_Harness)
        Registry.register("B", B_Harness)
        Registry.register("C", C_Harness)
        Registry.register("D", D_Harness)
        Registry.register("E", E_Harness)
    
    def test_linear_chain(self):
        """线性链：A → B → C"""
        pipeline = Pipeline("linear", [
            HarnessConfig(name="A"),
            HarnessConfig(name="B"),
            HarnessConfig(name="C"),
        ])
        runner = Runner(pipeline)
        layers = runner._build_dag(pipeline.get_enabled_steps())
        
        names = [[c.name for c in layer] for layer in layers]
        assert names == [["A"], ["B"], ["C"]]
    
    def test_parallel_branches(self):
        """并行分支：A → B → C, A → D → E(C+D)"""
        pipeline = Pipeline("parallel", [
            HarnessConfig(name="A"),
            HarnessConfig(name="B"),
            HarnessConfig(name="D"),
            HarnessConfig(name="C"),
            HarnessConfig(name="E"),
        ])
        runner = Runner(pipeline)
        layers = runner._build_dag(pipeline.get_enabled_steps())
        
        names = [[c.name for c in layer] for layer in layers]
        # A 在第一层
        assert "A" in names[0]
        # B 和 D 可以在同一层（都依赖 A）
        layer1 = names[1]
        assert "B" in layer1
        assert "D" in layer1
        # C 依赖 B，E 依赖 C 和 D
        # C 在 B 之后，E 在 C 和 D 之后
        assert "C" in [n for layer in names[2:] for n in layer]
        assert "E" in [n for layer in names[2:] for n in layer]
    
    def test_independent_harnesses(self):
        """完全独立的 Harnesses"""
        class X_Harness(Harness):
            INPUTS = []
            OUTPUTS = ["x"]
            def run(self, inputs, ctx): return {"x": 1}
        
        class Y_Harness(Harness):
            INPUTS = []
            OUTPUTS = ["y"]
            def run(self, inputs, ctx): return {"y": 2}
        
        Registry.register("X", X_Harness)
        Registry.register("Y", Y_Harness)
        
        pipeline = Pipeline("independent", [
            HarnessConfig(name="X"),
            HarnessConfig(name="Y"),
        ])
        runner = Runner(pipeline)
        layers = runner._build_dag(pipeline.get_enabled_steps())
        
        # X 和 Y 都在第一层（并行）
        names = [c.name for c in layers[0]]
        assert "X" in names
        assert "Y" in names
    
    def test_circular_dependency(self):
        """循环依赖检测"""
        class X_Harness(Harness):
            INPUTS = ["y"]
            OUTPUTS = ["x"]
            def run(self, inputs, ctx): return {"x": 1}
        
        class Y_Harness(Harness):
            INPUTS = ["x"]
            OUTPUTS = ["y"]
            def run(self, inputs, ctx): return {"y": 2}
        
        Registry.register("CX", X_Harness)
        Registry.register("CY", Y_Harness)
        
        pipeline = Pipeline("circular", [
            HarnessConfig(name="CX"),
            HarnessConfig(name="CY"),
        ])
        runner = Runner(pipeline)
        
        with pytest.raises(RuntimeError) as exc_info:
            runner._build_dag(pipeline.get_enabled_steps())
        
        assert "Circular dependency" in str(exc_info.value)
    
    def test_disabled_steps(self):
        """禁用步骤"""
        pipeline = Pipeline("disabled", [
            HarnessConfig(name="A"),
            HarnessConfig(name="B", enabled=False),
            HarnessConfig(name="C"),
        ])
        steps = pipeline.get_enabled_steps()
        assert len(steps) == 2
        assert steps[0].name == "A"
        assert steps[1].name == "C"


class TestDagExecution:
    """DAG 执行测试"""
    
    @pytest.fixture(autouse=True)
    def setup_registry(self):
        Registry.register("A", A_Harness)
        Registry.register("B", B_Harness)
        Registry.register("C", C_Harness)
    
    def test_linear_execution(self):
        """线性链执行"""
        pipeline = Pipeline("linear", [
            HarnessConfig(name="A"),
            HarnessConfig(name="B"),
            HarnessConfig(name="C"),
        ])
        runner = Runner(pipeline)
        ctx = Context()
        
        result = runner.run(ctx, enable_snapshots=False)
        
        assert result["success"] is True
        assert result["completed_steps"] == 3
        assert ctx.get("c") == 3  # a=1, b=2, c=3
    
    def test_partial_execution(self):
        """部分执行（依赖缺失）"""
        class Bad_Harness(Harness):
            INPUTS = ["missing"]
            OUTPUTS = ["out"]
            def run(self, inputs, ctx): return {"out": 1}
        
        Registry.register("BAD", Bad_Harness)
        
        pipeline = Pipeline("bad", [
            HarnessConfig(name="BAD", error_policy=ErrorPolicy.TERMINATE),
        ])
        runner = Runner(pipeline)
        ctx = Context()
        
        result = runner.run(ctx, enable_snapshots=False)
        
        assert result["success"] is False
        assert result["completed_steps"] == 0
