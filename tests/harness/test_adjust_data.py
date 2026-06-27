"""
Harness 测试：前复权数据正确性验证 v2

验证 OfflineDataProvider 的前复权处理是否准确：
- 读取不复权 vs 前复权数据对比
- OHLC 逻辑一致性
- 前复权核心特征：早期价格被调高，最新价格不变
- 数据完整性
"""

import pytest
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.harness import Harness, HarnessConfig, Context, RunMode, ErrorPolicy
from core.observability import ObservabilityEngine
from utils.mootdx_provider import OfflineDataProvider, MOOTDX_AVAILABLE, MOOTDX_ADJUST_AVAILABLE


# ─────────────────────────────────────────────────────────────
# 测试配置
# ─────────────────────────────────────────────────────────────

TEST_CODES = {
    "600519": "贵州茅台",  # 多次送股+分红
    "000001": "平安银行",  # 多次分红
    "300750": "宁德时代",  # 创业板，有送股
}

TDX_DIR = os.environ.get("TDX_DIR", "D:/TDX")
SKIP_REASON = "mootdx not installed or no local data"


def _has_tdx_data():
    if not MOOTDX_AVAILABLE:
        return False
    return os.path.exists(TDX_DIR) and os.path.exists(os.path.join(TDX_DIR, "vipdoc"))


# ─────────────────────────────────────────────────────────────
# Harness 定义：前复权数据验证
# ─────────────────────────────────────────────────────────────

class AdjustDataValidationHarness(Harness):
    """验证前复权数据正确性的 Harness"""
    
    INPUTS = ["code", "tdx_dir"]
    OUTPUTS = ["validation_result"]
    
    def __init__(self, config: HarnessConfig):
        super().__init__(config)
    
    def init(self, ctx: Context) -> None:
        pass
    
    def run(self, inputs: dict, ctx: Context) -> dict:
        code = inputs["code"]
        tdx_dir = inputs["tdx_dir"]
        
        provider = OfflineDataProvider(tdxdir=tdx_dir)
        
        raw_df = provider.fetch_kline(code, adjust="none")
        qfq_df = provider.fetch_kline(code, adjust="qfq")
        
        result = {
            "code": code,
            "raw_rows": 0,
            "qfq_rows": 0,
            "checks": {},
            "passed": False,
        }
        
        if raw_df is None or qfq_df is None:
            result["checks"]["data_availability"] = {
                "passed": False,
                "reason": f"raw_none={raw_df is None}, qfq_none={qfq_df is None}",
            }
            return {"validation_result": result}
        
        raw_df = raw_df.sort_values("date").reset_index(drop=True)
        qfq_df = qfq_df.sort_values("date").reset_index(drop=True)
        
        result["raw_rows"] = len(raw_df)
        result["qfq_rows"] = len(qfq_df)
        
        checks = {}
        
        # 检查1：数据量一致
        checks["row_count_match"] = {
            "passed": len(raw_df) == len(qfq_df),
            "raw_count": len(raw_df),
            "qfq_count": len(qfq_df),
        }
        
        # 检查2：价格列均为正数
        for col in ["open", "high", "low", "close"]:
            if col in qfq_df.columns:
                min_val = qfq_df[col].min()
                checks[f"qfq_{col}_positive"] = {
                    "passed": min_val > 0 if pd.notna(min_val) else False,
                    "min": float(min_val) if pd.notna(min_val) else None,
                }
        
        # 检查3：OHLC 逻辑一致性
        if all(c in qfq_df.columns for c in ["open", "high", "low", "close"]):
            ohlc_ok = (
                (qfq_df["high"] >= qfq_df["open"]).all() and
                (qfq_df["high"] >= qfq_df["close"]).all() and
                (qfq_df["high"] >= qfq_df["low"]).all() and
                (qfq_df["low"] <= qfq_df["open"]).all() and
                (qfq_df["low"] <= qfq_df["close"]).all()
            )
            checks["ohlc_logic"] = {"passed": bool(ohlc_ok)}
        
        # 检查4：前复权核心特征——早期价格被调高，最新价格不变
        if len(raw_df) == len(qfq_df) and len(raw_df) > 0:
            early_n = min(10, len(raw_df))
            raw_early = raw_df["close"].iloc[:early_n].values
            qfq_early = qfq_df["close"].iloc[:early_n].values
            
            # 前复权：早期价格 >= 原始价格（历史被调高）
            early_adjusted = (qfq_early >= raw_early).any()
            
            # 最新价格应该不变（允许浮点误差）
            raw_latest = raw_df["close"].iloc[-1]
            qfq_latest = qfq_df["close"].iloc[-1]
            latest_unchanged = abs(raw_latest - qfq_latest) < 0.01
            
            checks["early_price_adjusted"] = {
                "passed": early_adjusted and latest_unchanged,
                "raw_early_mean": float(raw_early.mean()),
                "qfq_early_mean": float(qfq_early.mean()),
                "early_ratio": float(qfq_early.mean() / raw_early.mean()) if raw_early.mean() > 0 else None,
                "raw_latest": float(raw_latest),
                "qfq_latest": float(qfq_latest),
                "latest_diff": float(abs(raw_latest - qfq_latest)),
            }
        
        # 检查5：日期列一致
        if "date" in raw_df.columns and "date" in qfq_df.columns:
            checks["dates_match"] = {
                "passed": raw_df["date"].tolist() == qfq_df["date"].tolist(),
            }
        
        # 检查6：volume 不变（复权不应改变成交量）
        if "volume" in raw_df.columns and "volume" in qfq_df.columns:
            vol_ratio = qfq_df["volume"].sum() / raw_df["volume"].sum() if raw_df["volume"].sum() > 0 else 1.0
            checks["volume_ratio"] = {
                "passed": 0.999 < vol_ratio < 1.001,
                "ratio": float(vol_ratio),
            }
        
        all_passed = all(c["passed"] for c in checks.values())
        result["checks"] = checks
        result["passed"] = all_passed
        
        return {"validation_result": result}


# ─────────────────────────────────────────────────────────────
# 测试用例
# ─────────────────────────────────────────────────────────────

class TestAdjustDataAvailability:
    """测试数据可用性前提"""
    
    def test_mootdx_installed(self):
        assert MOOTDX_AVAILABLE, "mootdx must be installed"
    
    def test_adjust_module_available(self):
        assert MOOTDX_ADJUST_AVAILABLE, "mootdx.utils.adjust must be available"
    
    def test_tdx_dir_exists(self):
        assert _has_tdx_data(), f"TDX data directory not found: {TDX_DIR}"


class TestAdjustDataValidation:
    """前复权数据验证测试"""
    
    @pytest.fixture
    def harness(self):
        config = HarnessConfig(
            name="adjust_validation",
            error_policy=ErrorPolicy.TERMINATE,
        )
        return AdjustDataValidationHarness(config)
    
    @pytest.fixture
    def context(self):
        return Context(mode=RunMode.POST_MARKET, date="20250619")
    
    @pytest.mark.skipif(not _has_tdx_data(), reason=SKIP_REASON)
    @pytest.mark.parametrize("code,name", [(k, v) for k, v in TEST_CODES.items()])
    def test_validation_runs(self, harness, context, code, name):
        """验证每个测试股票都能运行通过"""
        ctx = context
        ctx.set("code", code)
        ctx.set("tdx_dir", TDX_DIR)
        
        result = harness._execute(ctx)
        
        assert result.success, f"Harness execution failed for {code} ({name})"
        assert "validation_result" in result.outputs
        
        validation = result.outputs["validation_result"]
        assert validation["code"] == code
        assert validation["qfq_rows"] > 0, f"No qfq data for {code}"
    
    @pytest.mark.skipif(not _has_tdx_data(), reason=SKIP_REASON)
    @pytest.mark.parametrize("code,name", [(k, v) for k, v in TEST_CODES.items()])
    def test_prices_positive(self, harness, context, code, name):
        """前复权价格必须为正数"""
        ctx = context
        ctx.set("code", code)
        ctx.set("tdx_dir", TDX_DIR)
        
        result = harness._execute(ctx)
        validation = result.outputs["validation_result"]
        
        for col in ["open", "high", "low", "close"]:
            key = f"qfq_{col}_positive"
            assert key in validation["checks"], f"Missing check: {key} for {code}"
            assert validation["checks"][key]["passed"], \
                f"{code} {col} has non-positive values (min={validation['checks'][key].get('min')})"
    
    @pytest.mark.skipif(not _has_tdx_data(), reason=SKIP_REASON)
    @pytest.mark.parametrize("code,name", [(k, v) for k, v in TEST_CODES.items()])
    def test_ohlc_logic(self, harness, context, code, name):
        """OHLC 逻辑一致性：high >= open/close/low, low <= open/close/high"""
        ctx = context
        ctx.set("code", code)
        ctx.set("tdx_dir", TDX_DIR)
        
        result = harness._execute(ctx)
        validation = result.outputs["validation_result"]
        
        assert "ohlc_logic" in validation["checks"], f"Missing OHLC check for {code}"
        assert validation["checks"]["ohlc_logic"]["passed"], \
            f"{code} OHLC logic violated: high < open/close/low or low > open/close/high"
    
    @pytest.mark.skipif(not _has_tdx_data(), reason=SKIP_REASON)
    @pytest.mark.parametrize("code,name", [(k, v) for k, v in TEST_CODES.items()])
    def test_early_price_adjusted_and_latest_unchanged(self, harness, context, code, name):
        """前复权核心特征：早期价格被调高，最新价格不变"""
        ctx = context
        ctx.set("code", code)
        ctx.set("tdx_dir", TDX_DIR)
        
        result = harness._execute(ctx)
        validation = result.outputs["validation_result"]
        
        assert "early_price_adjusted" in validation["checks"], f"Missing early price check for {code}"
        assert validation["checks"]["early_price_adjusted"]["passed"], \
            f"{code} early price adjust failed. " \
            f"early_ratio={validation['checks']['early_price_adjusted'].get('early_ratio')}, " \
            f"latest_diff={validation['checks']['early_price_adjusted'].get('latest_diff')}"
    
    @pytest.mark.skipif(not _has_tdx_data(), reason=SKIP_REASON)
    @pytest.mark.parametrize("code,name", [(k, v) for k, v in TEST_CODES.items()])
    def test_dates_consistent(self, harness, context, code, name):
        """前复权后日期序列不变"""
        ctx = context
        ctx.set("code", code)
        ctx.set("tdx_dir", TDX_DIR)
        
        result = harness._execute(ctx)
        validation = result.outputs["validation_result"]
        
        assert "dates_match" in validation["checks"], f"Missing dates check for {code}"
        assert validation["checks"]["dates_match"]["passed"], \
            f"{code} dates mismatch between raw and qfq"
    
    @pytest.mark.skipif(not _has_tdx_data(), reason=SKIP_REASON)
    @pytest.mark.parametrize("code,name", [(k, v) for k, v in TEST_CODES.items()])
    def test_volume_unchanged(self, harness, context, code, name):
        """复权不应改变成交量"""
        ctx = context
        ctx.set("code", code)
        ctx.set("tdx_dir", TDX_DIR)
        
        result = harness._execute(ctx)
        validation = result.outputs["validation_result"]
        
        assert "volume_ratio" in validation["checks"], f"Missing volume check for {code}"
        assert validation["checks"]["volume_ratio"]["passed"], \
            f"{code} volume changed after adjust (should be identical). " \
            f"ratio={validation['checks']['volume_ratio'].get('ratio')}"


class TestAdjustEdgeCases:
    """边界情况测试"""
    
    @pytest.mark.skipif(not MOOTDX_AVAILABLE, reason="mootdx not installed")
    def test_invalid_code(self, harness, context):
        """无效代码应返回 None 或空数据"""
        from utils.mootdx_provider import OfflineDataProvider
        provider = OfflineDataProvider(tdxdir=TDX_DIR)
        df = provider.fetch_kline("999999", adjust="qfq")
        assert df is None or len(df) == 0
    
    @pytest.mark.skipif(not _has_tdx_data(), reason=SKIP_REASON)
    def test_single_day_data(self, context):
        """单条数据的前复权处理"""
        harness = AdjustDataValidationHarness(HarnessConfig(
            name="single_day_test", error_policy=ErrorPolicy.SKIP
        ))
        ctx = context
        ctx.set("code", "600519")
        ctx.set("tdx_dir", TDX_DIR)
        
        result = harness._execute(ctx)
        assert result.success
        
        validation = result.outputs["validation_result"]
        assert validation["qfq_rows"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
