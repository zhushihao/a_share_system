"""
单元测试：Context 数据操作
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.harness import Context, RunMode


class TestContextBasics:
    """Context 基础操作测试"""
    
    def test_init(self, context):
        assert context.mode == RunMode.POST_MARKET
        assert context.date == "20250619"
        assert context.keys() == []
    
    def test_set_and_get(self, context):
        context.set("stock_data.000001", {"name": "平安银行"})
        assert context.get("stock_data.000001") == {"name": "平安银行"}
    
    def test_get_nested(self, context):
        context.set("a.b.c", 42)
        assert context.get("a.b.c") == 42
    
    def test_get_default(self, context):
        assert context.get("nonexistent", "default") == "default"
        assert context.get("nonexistent") is None
    
    def test_has(self, context):
        context.set("key", "value")
        assert context.has("key") is True
        assert context.has("missing") is False
    
    def test_require(self, context):
        context.set("a", 1)
        context.set("b", 2)
        context.require("a", "b")  # 不抛异常
        
        with pytest.raises(KeyError):
            context.require("a", "c")
    
    def test_extract(self, context):
        context.set("a", 1)
        context.set("b", 2)
        context.set("c", 3)
        result = context.extract(["a", "b", "missing"])
        assert result == {"a": 1, "b": 2}
    
    def test_merge(self, context):
        context.merge({"x": 10, "y": 20})
        assert context.get("x") == 10
        assert context.get("y") == 20
    
    def test_snapshot_and_restore(self, context):
        context.set("data", "original")
        context.snapshot("test")
        context.set("data", "changed")
        assert context.get("data") == "changed"
        
        context.restore(-1)
        assert context.get("data") == "original"
    
    def test_keys(self, context):
        context.set("a", 1)
        context.set("b", 2)
        keys = context.keys()
        assert "a" in keys
        assert "b" in keys
    
    def test_keys_with_prefix(self, context):
        context.set("stock_data.000001", {})
        context.set("stock_data.000002", {})
        context.set("other", {})
        keys = context.keys("stock_data")
        assert len(keys) == 2
        assert "stock_data.000001" in keys
    
    def test_to_dict_shallow(self, context):
        context.set("a", {"nested": "value"})
        shallow = context.to_dict(shallow=True)
        assert shallow["a"] == "dict"
    
    def test_log(self, context):
        context.log("INFO", "test message", "test_harness")
        logs = context.get("_log_entries")
        assert len(logs) == 1
        assert logs[0]["level"] == "INFO"
        assert logs[0]["message"] == "test message"
    
    def test_log_multiple(self, context):
        context.log("INFO", "msg1")
        context.log("WARN", "msg2")
        context.log("ERROR", "msg3")
        logs = context.get("_log_entries")
        assert len(logs) == 3


class TestContextEdgeCases:
    """Context 边界情况测试"""
    
    def test_empty_key(self, context):
        with pytest.raises(IndexError):
            context.set("", "value")
    
    def test_overwrite(self, context):
        context.set("key", "first")
        context.set("key", "second")
        assert context.get("key") == "second"
    
    def test_nested_overwrite(self, context):
        context.set("a.b", {"x": 1})
        context.set("a.b", {"y": 2})
        assert context.get("a.b") == {"y": 2}
    
    def test_snapshot_empty(self, context):
        context.snapshot("empty")
        assert context.restore(-1) is context
    
    def test_multiple_snapshots(self, context):
        context.set("v", 1)
        context.snapshot("s1")
        context.set("v", 2)
        context.snapshot("s2")
        context.set("v", 3)
        
        context.restore(0)  # 恢复到s1
        assert context.get("v") == 1
        
        context.restore(-1)  # 恢复到s2
        assert context.get("v") == 2
