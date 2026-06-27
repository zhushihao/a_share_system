# -*- coding: utf-8 -*-
"""
测试自定义策略 DSL（替代 exec 的安全方案）
"""
import json

import pandas as pd
import pytest

from backend.services.backtest_engine import (
    BacktestEngine,
    validate_custom_dsl,
    _eval_custom_dsl,
    get_custom_strategy_template,
    get_strategy_templates,
)


def _make_df(values: dict) -> pd.DataFrame:
    """构造测试 DataFrame，默认 5 行。"""
    n = 5
    base = {"close": [10.0] * n}
    base.update(values)
    return pd.DataFrame(base)


class TestValidateCustomDsl:
    def test_valid_cross_up_down(self):
        dsl = {
            "rules": [
                {
                    "condition": {"cross_up": [{"col": "ma5"}, {"col": "ma20"}]},
                    "action": "BUY",
                    "position_pct": 0.99,
                    "reason": "金叉",
                },
                {
                    "condition": {"cross_down": [{"col": "ma5"}, {"col": "ma20"}]},
                    "action": "SELL",
                    "reason": "死叉",
                },
            ]
        }
        validate_custom_dsl(dsl)  # should not raise

    def test_valid_and_or_not(self):
        dsl = {
            "rules": [
                {
                    "condition": {
                        "and": [
                            {"gt": [{"col": "close"}, {"const": 100}]},
                            {"or": [
                                {"lt": [{"col": "kdj_k"}, {"const": 20}]},
                                {"not": {"eq": [{"col": "macd_dif"}, {"const": 0}]}},
                            ]},
                        ]
                    },
                    "action": "HOLD",
                }
            ]
        }
        validate_custom_dsl(dsl)

    def test_valid_in_range(self):
        dsl = {
            "rules": [
                {
                    "condition": {"in_range": {"value": {"col": "rsi"}, "min": {"const": 30}, "max": {"const": 70}}},
                    "action": "BUY",
                    "position_pct": 0.5,
                }
            ]
        }
        validate_custom_dsl(dsl)

    @pytest.mark.parametrize("dsl", [
        {},
        {"rules": "not a list"},
        {"rules": [{"condition": {"gt": [{"col": "close"}, {"const": 10}]}}]},
        {"rules": [{"action": "UNKNOWN"}]},
        {"rules": [{"action": "BUY", "position_pct": 1.5}]},
        {"rules": [{"action": "BUY", "condition": {"unknown_op": []}}]},
    ])
    def test_invalid_dsl_raises(self, dsl):
        with pytest.raises(ValueError):
            validate_custom_dsl(dsl)


class TestEvalCustomDsl:
    def test_cross_up_buy(self):
        # ma5 在最后一根上穿 ma20
        df = _make_df({
            "ma5": [9.0, 9.5, 10.0, 10.2, 11.0],
            "ma20": [10.0, 10.0, 10.0, 10.5, 10.5],
        })
        dsl = {
            "rules": [
                {
                    "condition": {"cross_up": [{"col": "ma5"}, {"col": "ma20"}]},
                    "action": "BUY",
                    "position_pct": 1.0,
                    "reason": "金叉",
                }
            ]
        }
        signal = _eval_custom_dsl(dsl, df, position=0, cash=100000, params={})
        assert signal["action"] == "BUY"
        assert signal["size"] == 100000 // 10.0  # price = close 10.0
        assert signal["reason"] == "金叉"

    def test_cross_down_sell(self):
        df = _make_df({
            "ma5": [11.0, 11.0, 10.5, 10.5, 9.5],
            "ma20": [10.0, 10.0, 10.0, 10.5, 10.5],
        })
        dsl = {
            "rules": [
                {
                    "condition": {"cross_down": [{"col": "ma5"}, {"col": "ma20"}]},
                    "action": "SELL",
                    "reason": "死叉",
                }
            ]
        }
        signal = _eval_custom_dsl(dsl, df, position=500, cash=0, params={})
        assert signal["action"] == "SELL"
        assert signal["size"] == 500

    def test_hold_when_no_rule_matches(self):
        df = _make_df({"ma5": [10.0] * 5, "ma20": [10.0] * 5})
        dsl = {
            "rules": [
                {
                    "condition": {"cross_up": [{"col": "ma5"}, {"col": "ma20"}]},
                    "action": "BUY",
                    "position_pct": 1.0,
                }
            ]
        }
        signal = _eval_custom_dsl(dsl, df, position=0, cash=100000, params={})
        assert signal["action"] == "HOLD"

    def test_param_resolution(self):
        df = _make_df({"rsi": [20.0, 22.0, 24.0, 26.0, 28.0]})
        dsl = {
            "rules": [
                {
                    "condition": {"lt": [{"col": "rsi"}, {"param": "oversold", "default": 30}]},
                    "action": "BUY",
                    "position_pct": 1.0,
                }
            ]
        }
        signal = _eval_custom_dsl(dsl, df, position=0, cash=100000, params={"oversold": 30})
        assert signal["action"] == "BUY"

    def test_and_condition(self):
        df = _make_df({
            "kdj_k": [18.0, 19.0, 19.0, 19.0, 21.0],
            "kdj_d": [20.0, 20.0, 20.0, 20.0, 20.0],
        })
        dsl = {
            "rules": [
                {
                    "condition": {
                        "and": [
                            {"cross_up": [{"col": "kdj_k"}, {"col": "kdj_d"}]},
                            {"lt": [{"col": "kdj_k"}, {"const": 30}]},
                        ]
                    },
                    "action": "BUY",
                    "position_pct": 1.0,
                }
            ]
        }
        signal = _eval_custom_dsl(dsl, df, position=0, cash=100000, params={})
        assert signal["action"] == "BUY"

    def test_no_buy_when_already_in_position(self):
        df = _make_df({
            "ma5": [9.0, 9.5, 10.0, 10.2, 11.0],
            "ma20": [10.0, 10.0, 10.0, 10.5, 10.5],
        })
        dsl = {
            "rules": [
                {
                    "condition": {"cross_up": [{"col": "ma5"}, {"col": "ma20"}]},
                    "action": "BUY",
                    "position_pct": 1.0,
                }
            ]
        }
        signal = _eval_custom_dsl(dsl, df, position=100, cash=50000, params={})
        assert signal["action"] == "HOLD"


class TestBacktestEngineCustom:
    def test_load_custom_strategy_rejects_python_code(self):
        engine = BacktestEngine()
        python_code = "import os; print(os.environ); def strategy(df, p, c, params): return {}"
        fn = engine._load_custom_strategy(python_code)
        assert fn is None

    def test_load_custom_strategy_accepts_valid_dsl(self):
        engine = BacktestEngine()
        dsl = json.dumps({
            "rules": [
                {
                    "condition": {"gt": [{"col": "close"}, {"const": 0}]},
                    "action": "HOLD",
                }
            ]
        })
        fn = engine._load_custom_strategy(dsl)
        assert fn is not None

    def test_resolve_strategy_custom(self):
        engine = BacktestEngine()
        dsl = json.dumps({"rules": [{"action": "HOLD"}]})
        fn = engine._resolve_strategy("custom", dsl)
        assert fn is not None
        # Python code should be rejected
        assert engine._resolve_strategy("custom", "import os") is None

    def test_custom_not_in_presets(self):
        templates = get_strategy_templates()
        names = [t["name"] for t in templates]
        assert "custom" in names
        # But PRESET_STRATEGIES does not contain it
        from backend.services.backtest_engine import PRESET_STRATEGIES
        assert "custom" not in PRESET_STRATEGIES

    def test_template_is_json(self):
        template = get_custom_strategy_template()
        parsed = json.loads(template)
        assert "rules" in parsed

    def test_no_exec_in_source(self):
        import pathlib
        source = pathlib.Path(__file__).parent.parent.parent / "backend" / "services" / "backtest_engine.py"
        text = source.read_text(encoding="utf-8")
        assert "exec(" not in text, "backend/services/backtest_engine.py 中仍存在 exec() 调用"
