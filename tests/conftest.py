"""
测试共享配置 - pytest fixtures
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.harness import Context, RunMode, HarnessConfig, Harness, ErrorPolicy
from core.observability import ObservabilityEngine


@pytest.fixture
def context():
    """基础 Context fixture"""
    return Context(mode=RunMode.POST_MARKET, date="20250619")


@pytest.fixture
def empty_context():
    """空 Context fixture"""
    return Context(mode=RunMode.POST_MARKET, date="")


@pytest.fixture
def harness_config():
    """基础 HarnessConfig fixture"""
    return HarnessConfig(
        name="test_harness",
        error_policy=ErrorPolicy.SKIP,
        params={"test_param": 42},
    )


@pytest.fixture
def observability():
    """可观测性引擎（自动重置）"""
    obs = ObservabilityEngine()
    obs.reset()
    return obs


@pytest.fixture
def mock_stock_data():
    """模拟股票数据"""
    return {
        "000001": {"name": "平安银行", "price": 10.5, "volume": 1000000},
        "600519": {"name": "贵州茅台", "price": 1680.0, "volume": 50000},
    }


@pytest.fixture
def mock_patterns():
    """模拟型态数据"""
    return {
        "000001": [{"type": "W底", "confidence": 0.85}],
        "600519": [{"type": "M头", "confidence": 0.72}],
    }
