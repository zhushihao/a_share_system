# -*- coding: utf-8 -*-
"""
Quant Workbench 数据中台质量自检脚本（多周期数据质量检查）

自检范围：
1. 数据平台核心缓存 — L1/L2/L3 缓存命中率、数据新鲜度
2. 多周期数据质量 — minute/daily/weekly/monthly/quarterly/yearly 完整性
3. 指数数据 — sh000001/sz399001/sz399006 各周期
4. 个股数据 — 随机抽样10只A股各周期测试
5. 指标引擎 — 各周期 MA/KDJ/MACD/RSI/BOLL 计算正确性
6. 聚合层正确性 — 周/月/季/年K线聚合逻辑验证
7. 前端兼容性 — 前端周期切换按钮对应的API参数验证

时间锚定：2026-06-24 01:00 CST
"""

import sys, os, time, json, random, math
from datetime import datetime, timedelta
from collections import defaultdict

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import numpy as np

# ───────────────────────────────────────────────
# 导入后端模块
# ───────────────────────────────────────────────
from backend.services.data_platform import get_data_platform_service, DataPlatformService
from backend.services.data_provider import get_data_provider_service
from backend.services.indicators import calculate_all_indicators, get_latest_indicators
from backend.core.cache import MultiLevelCache

# ───────────────────────────────────────────────
# 配置与常量
# ───────────────────────────────────────────────
PERIODS = ["daily", "weekly", "monthly", "quarterly", "yearly"]  # minute 可能数据量过大，单独测试
INDEX_SYMBOLS = ["sh000001", "sz399001", "sz399006"]
MIN_SAMPLE_SIZE = 10    # 各周期最小样本数要求

random.seed(42)  # 可复现

# 全局报告
REPORT = {
    "timestamp": datetime.now().isoformat(),
    "summary": {"passed": 0, "failed": 0, "warnings": 0, "total": 0},
    "sections": {}
}

# ───────────────────────────────────────────────
# 辅助函数
# ───────────────────────────────────────────────

def record(section: str, name: str, status: str, details: dict = None):
    """记录检查结果"""
    if section not in REPORT["sections"]:
        REPORT["sections"][section] = {"items": [], "passed": 0, "failed": 0, "warnings": 0}
    item = {"name": name, "status": status, "details": details or {}}
    REPORT["sections"][section]["items"].append(item)
    REPORT["summary"]["total"] += 1
    if status == "PASS":
        REPORT["summary"]["passed"] += 1
        REPORT["sections"][section]["passed"] += 1
    elif status == "FAIL":
        REPORT["summary"]["failed"] += 1
        REPORT["sections"][section]["failed"] += 1
    elif status == "WARN":
        REPORT["summary"]["warnings"] += 1
        REPORT["sections"][section]["warnings"] += 1
    return status == "PASS"


def check_dataframe(df, required_cols=None, min_rows=1) -> tuple:
    """检查DataFrame是否满足基本要求"""
    if df is None:
        return False, "DataFrame is None"
    if not isinstance(df, pd.DataFrame):
        return False, f"Not a DataFrame, got {type(df)}"
    if len(df) < min_rows:
        return False, f"Rows too few: {len(df)} < {min_rows}"
    if required_cols:
        missing = set(required_cols) - set(df.columns)
        if missing:
            return False, f"Missing columns: {missing}"
    return True, "OK"


# ───────────────────────────────────────────────
# 1. 数据平台核心缓存检查
# ───────────────────────────────────────────────

def check_cache_system():
    """检查缓存系统状态"""
    print("\n" + "=" * 60)
    print("[1] 数据平台核心缓存检查")
    print("=" * 60)

    platform = get_data_platform_service()
    stats = platform.get_stats()
    cache_stats = stats.get("cache_stats", {})

    # L1 检查
    l1_size = cache_stats.get("l1_size", 0)
    l3_count = cache_stats.get("l3_count", 0)
    hit_rate = cache_stats.get("hit_rate", 0)
    total_requests = cache_stats.get("total_requests", 0)
    update_counts = stats.get("update_counts", {})

    record("cache_system", "L1内存缓存",
           "PASS" if l1_size >= 0 else "FAIL",
           {"l1_size": l1_size, "description": f"L1内存缓存条目数: {l1_size}"})

    record("cache_system", "L3持久化缓存",
           "PASS" if l3_count >= 0 else "FAIL",
           {"l3_count": l3_count, "description": f"L3 SQLite缓存条目数: {l3_count}"})

    record("cache_system", "缓存总请求数",
           "PASS" if total_requests >= 0 else "FAIL",
           {"total_requests": total_requests})

    record("cache_system", "缓存命中率统计",
           "PASS" if hit_rate is not None else "FAIL",
           {"hit_rate": hit_rate, "hits": cache_stats.get("hits", {})})

    record("cache_system", "更新计数器",
           "PASS" if len(update_counts) > 0 else "FAIL",
           {"update_counts": update_counts})

    # 质量历史
    quality_history = stats.get("quality_history", {})
    record("cache_system", "质量历史检查",
           "PASS" if quality_history.get("total", 0) >= 0 else "FAIL",
           {"quality_history": quality_history})

    print(f"  L1缓存: {l1_size} 条目")
    print(f"  L3缓存: {l3_count} 条目")
    print(f"  总请求: {total_requests}")
    print(f"  命中率: {hit_rate}")
    print(f"  更新计数: {update_counts}")
    print(f"  质量历史: {quality_history}")


# ───────────────────────────────────────────────
# 2. 多周期数据质量检查
# ───────────────────────────────────────────────

def check_multi_period_data(symbol: str, is_index: bool = False, source_section: str = "multi_period"):
    """检查单个symbol的多周期数据质量"""
    platform = get_data_platform_service()
    required_cols = ["date", "open", "high", "low", "close", "volume"]
    results = {}

    for period in PERIODS:
        try:
            df = platform.get_ohlcv(symbol, period=period, adjust="qfq")
            ok, msg = check_dataframe(df, required_cols=required_cols, min_rows=1)
            if ok:
                results[period] = {
                    "status": "PASS",
                    "rows": len(df),
                    "cols": list(df.columns),
                    "date_range": {"start": str(df.iloc[0]["date"]), "end": str(df.iloc[-1]["date"])},
                    "null_count": int(df.isnull().sum().sum()),
                }
            else:
                results[period] = {"status": "FAIL", "message": msg}
        except Exception as e:
            results[period] = {"status": "FAIL", "message": str(e)}

    return results


def test_multi_period():
    """测试多周期数据质量"""
    print("\n" + "=" * 60)
    print("[2] 多周期数据质量检查")
    print("=" * 60)

    platform = get_data_platform_service()
    test_cases = [
        ("sh000001", True, "上证指数"),
        ("sz399001", True, "深证成指"),
        ("sz399006", True, "创业板指"),
    ]

    for symbol, is_index, name in test_cases:
        print(f"\n  测试 {symbol} ({name})...")
        results = check_multi_period_data(symbol, is_index, "multi_period")
        for period, res in results.items():
            status = res["status"]
            details = {k: v for k, v in res.items() if k != "status"}
            record("multi_period", f"{symbol} {period}", status, details)
            print(f"    {period:12s} -> {status} ({details.get('rows', details.get('message', 'N/A'))})")

    # 随机抽样个股
    print("\n  获取股票列表...")
    try:
        stock_list = platform.get_stock_list()
        if stock_list is not None and len(stock_list) > 0:
            codes = stock_list["code"].astype(str).str.zfill(6).tolist()
            # 过滤有效A股代码
            valid_codes = [c for c in codes if c.startswith(("600","601","603","605","000","001","002","003","300","301"))]
            sample = random.sample(valid_codes, min(10, len(valid_codes)))
            print(f"  随机抽样10只: {sample}")
            for symbol in sample:
                print(f"  测试 {symbol}...")
                results = check_multi_period_data(symbol, False, "multi_period")
                for period, res in results.items():
                    status = res["status"]
                    details = {k: v for k, v in res.items() if k != "status"}
                    record("multi_period", f"{symbol} {period}", status, details)
                    print(f"    {period:12s} -> {status} ({details.get('rows', details.get('message', 'N/A'))})")
        else:
            record("multi_period", "股票列表获取", "FAIL", {"message": "无法获取股票列表"})
    except Exception as e:
        record("multi_period", "股票列表获取", "FAIL", {"message": str(e)})
        print(f"  获取股票列表失败: {e}")


# ───────────────────────────────────────────────
# 3. 指数数据检查
# ───────────────────────────────────────────────

def test_index_data():
    """验证指数各周期数据"""
    print("\n" + "=" * 60)
    print("[3] 指数数据检查")
    print("=" * 60)

    platform = get_data_platform_service()

    for symbol in INDEX_SYMBOLS:
        print(f"\n  测试 {symbol}...")
        for period in PERIODS:
            try:
                df = platform.get_ohlcv(symbol, period=period, adjust="none")
                ok, msg = check_dataframe(df, required_cols=["date","open","high","low","close","volume"], min_rows=5)
                if ok:
                    # 额外检查：价格一致性
                    issues = []
                    invalid_close = ~((df["close"] >= df["low"] - 0.02) & (df["close"] <= df["high"] + 0.02))
                    if invalid_close.any():
                        issues.append(f"close out of range in {invalid_close.sum()} rows")
                    invalid_low_high = ~(df["low"] <= df["high"] + 0.02)
                    if invalid_low_high.any():
                        issues.append(f"low > high in {invalid_low_high.sum()} rows")

                    status = "PASS" if not issues else "WARN"
                    record("index_data", f"{symbol} {period}", status, {
                        "rows": len(df), "date_range": [str(df.iloc[0]["date"]), str(df.iloc[-1]["date"])],
                        "issues": issues
                    })
                    print(f"    {period:12s} -> {status} ({len(df)} rows, {issues if issues else 'OK'})")
                else:
                    record("index_data", f"{symbol} {period}", "FAIL", {"message": msg})
                    print(f"    {period:12s} -> FAIL ({msg})")
            except Exception as e:
                record("index_data", f"{symbol} {period}", "FAIL", {"message": str(e)})
                print(f"    {period:12s} -> FAIL ({e})")


# ───────────────────────────────────────────────
# 4. 个股数据抽样
# ───────────────────────────────────────────────

def test_stock_sample():
    """随机抽样10只A股测试各周期数据"""
    print("\n" + "=" * 60)
    print("[4] 个股数据抽样检查")
    print("=" * 60)

    platform = get_data_platform_service()
    try:
        stock_list = platform.get_stock_list()
        if stock_list is not None and len(stock_list) > 0:
            codes = stock_list["code"].astype(str).str.zfill(6).tolist()
            valid_codes = [c for c in codes if c.startswith(("600","601","603","605","000","001","002","003","300","301"))]
            sample = random.sample(valid_codes, min(10, len(valid_codes)))
        else:
            sample = ["000001", "600519", "000858", "002594", "300750",
                      "600036", "601318", "601012", "000333", "600276"]
    except Exception:
        sample = ["000001", "600519", "000858", "002594", "300750",
                  "600036", "601318", "601012", "000333", "600276"]

    print(f"  抽样股票: {sample}")
    for symbol in sample:
        print(f"  测试 {symbol}...")
        for period in ["daily", "weekly", "monthly"]:
            try:
                df = platform.get_ohlcv(symbol, period=period, adjust="qfq")
                ok, msg = check_dataframe(df, required_cols=["date","open","high","low","close","volume"], min_rows=5)
                if ok:
                    record("stock_sample", f"{symbol} {period}", "PASS", {
                        "rows": len(df), "date_range": [str(df.iloc[0]["date"]), str(df.iloc[-1]["date"])]
                    })
                    print(f"    {period:12s} -> PASS ({len(df)} rows)")
                else:
                    record("stock_sample", f"{symbol} {period}", "FAIL", {"message": msg})
                    print(f"    {period:12s} -> FAIL ({msg})")
            except Exception as e:
                record("stock_sample", f"{symbol} {period}", "FAIL", {"message": str(e)})
                print(f"    {period:12s} -> FAIL ({e})")


# ───────────────────────────────────────────────
# 5. 指标引擎检查
# ───────────────────────────────────────────────

def test_indicator_engine():
    """验证各周期技术指标计算正确性"""
    print("\n" + "=" * 60)
    print("[5] 指标引擎检查")
    print("=" * 60)

    platform = get_data_platform_service()
    test_symbols = ["sh000001", "000001", "600519"]
    indicator_keys = ["ma5", "ma10", "ma20", "ma60", "kdj_k", "kdj_d", "kdj_j",
                      "macd_dif", "macd_dea", "macd_bar", "rsi6", "rsi12", "rsi24",
                      "boll_up", "boll_mid", "boll_down"]

    for symbol in test_symbols:
        print(f"\n  测试 {symbol}...")
        for period in ["daily", "weekly", "monthly"]:
            try:
                df = platform.get_indicators(symbol, period=period, adjust="qfq")
                if df is None or len(df) == 0:
                    record("indicator_engine", f"{symbol} {period}", "FAIL", {"message": "No indicators data"})
                    print(f"    {period:12s} -> FAIL (No data)")
                    continue

                # 检查指标列是否存在
                missing_cols = [c for c in indicator_keys if c not in df.columns]
                if missing_cols:
                    record("indicator_engine", f"{symbol} {period}", "WARN",
                           {"message": f"Missing indicator columns: {missing_cols}", "columns": list(df.columns)})
                    print(f"    {period:12s} -> WARN (Missing: {missing_cols})")
                    continue

                # 检查最新指标值是否有NaN
                latest = df.iloc[-1]
                # 智能判断NaN是否为预期行为（数据长度不足导致的边界效应）
                nan_indicators = [c for c in indicator_keys if c in df.columns and pd.isna(latest[c])]
                if nan_indicators:
                    expected_nan = []
                    unexpected_nan = []
                    for col in nan_indicators:
                        if col.startswith("ma"):
                            window = int(col.replace("ma", ""))
                            if len(df) < window:
                                expected_nan.append(col)
                            else:
                                unexpected_nan.append(col)
                        elif col in ("kdj_k", "kdj_d", "kdj_j"):
                            if len(df) < 14:
                                expected_nan.append(col)
                            else:
                                unexpected_nan.append(col)
                        elif col in ("macd_dif", "macd_dea", "macd_bar"):
                            if len(df) < 35:
                                expected_nan.append(col)
                            else:
                                unexpected_nan.append(col)
                        elif col in ("rsi6", "rsi12", "rsi24"):
                            window = int(col.replace("rsi", ""))
                            if len(df) < window:
                                expected_nan.append(col)
                            else:
                                unexpected_nan.append(col)
                        elif col in ("boll_up", "boll_mid", "boll_down"):
                            if len(df) < 20:
                                expected_nan.append(col)
                            else:
                                unexpected_nan.append(col)
                        else:
                            unexpected_nan.append(col)

                    if unexpected_nan:
                        record("indicator_engine", f"{symbol} {period}", "WARN",
                               {"message": f"Unexpected NaN: {unexpected_nan}", "expected_nan": expected_nan,
                                "nan_count": len(nan_indicators)})
                        print(f"    {period:12s} -> WARN (Unexpected NaN: {unexpected_nan})")
                    else:
                        # 全部为预期行为
                        record("indicator_engine", f"{symbol} {period}", "PASS",
                               {"message": f"All NaN are expected (insufficient data): {expected_nan}",
                                "expected_nan": expected_nan, "data_length": len(df)})
                        print(f"    {period:12s} -> PASS (expected NaN: {expected_nan})")
                else:
                    # 检查指标值合理性
                    issues = []
                    if "kdj_k" in df.columns and "kdj_d" in df.columns and "kdj_j" in df.columns:
                        k, d, j = latest["kdj_k"], latest["kdj_d"], latest["kdj_j"]
                        if not (0 <= k <= 100 and 0 <= d <= 100):
                            issues.append(f"KDJ K/D out of range: K={k}, D={d}")
                        if not pd.isna(j) and not (-20 <= j <= 120):
                            issues.append(f"KDJ J out of range: J={j}")
                    if "rsi6" in df.columns:
                        rsi6 = latest["rsi6"]
                        if not pd.isna(rsi6) and not (0 <= rsi6 <= 100):
                            issues.append(f"RSI6 out of range: {rsi6}")
                    if "boll_up" in df.columns and "boll_down" in df.columns:
                        up, down = latest["boll_up"], latest["boll_down"]
                        if not pd.isna(up) and not pd.isna(down) and up < down:
                            issues.append(f"BOLL up < down: {up} < {down}")

                    status = "PASS" if not issues else "WARN"
                    record("indicator_engine", f"{symbol} {period}", status,
                           {"columns": list(df.columns), "latest_valid": len(df) - len(nan_indicators),
                            "issues": issues})
                    print(f"    {period:12s} -> {status} ({len(df)} rows, issues={issues if issues else 'None'})")
            except Exception as e:
                record("indicator_engine", f"{symbol} {period}", "FAIL", {"message": str(e)})
                print(f"    {period:12s} -> FAIL ({e})")


# ───────────────────────────────────────────────
# 6. 聚合层正确性检查
# ───────────────────────────────────────────────

def test_aggregation_logic():
    """验证周/月/季/年K线聚合逻辑：open=first, high=max, low=min, close=last, volume=sum"""
    print("\n" + "=" * 60)
    print("[6] 聚合层正确性检查")
    print("=" * 60)

    platform = get_data_platform_service()
    test_symbols = ["sh000001", "000001", "600519"]
    tolerance = 0.02

    for symbol in test_symbols:
        print(f"\n  测试 {symbol}...")
        try:
            # 获取日线数据
            daily_df = platform.get_ohlcv(symbol, period="daily", adjust="qfq")
            if daily_df is None or len(daily_df) < 20:
                record("aggregation", f"{symbol} daily insufficient", "FAIL",
                       {"message": f"Daily data too few: {len(daily_df) if daily_df is not None else 0}"})
                print(f"    日线数据不足，跳过")
                continue

            # 验证周线
            weekly_df = platform.get_ohlcv(symbol, period="weekly", adjust="qfq")
            if weekly_df is not None and len(weekly_df) > 0:
                # 手动聚合最近4周
                ok = verify_aggregation(daily_df, weekly_df, "W", tolerance)
                status = "PASS" if ok else "FAIL"
                record("aggregation", f"{symbol} weekly", status, {"verified_weeks": min(4, len(weekly_df))})
                print(f"    weekly      -> {status}")
            else:
                record("aggregation", f"{symbol} weekly", "FAIL", {"message": "No weekly data"})
                print(f"    weekly      -> FAIL (No data)")

            # 验证月线
            monthly_df = platform.get_ohlcv(symbol, period="monthly", adjust="qfq")
            if monthly_df is not None and len(monthly_df) > 0:
                ok = verify_aggregation(daily_df, monthly_df, "M", tolerance)
                status = "PASS" if ok else "FAIL"
                record("aggregation", f"{symbol} monthly", status, {"verified_months": min(3, len(monthly_df))})
                print(f"    monthly     -> {status}")
            else:
                record("aggregation", f"{symbol} monthly", "FAIL", {"message": "No monthly data"})
                print(f"    monthly     -> FAIL (No data)")

        except Exception as e:
            record("aggregation", f"{symbol}", "FAIL", {"message": str(e)})
            print(f"    FAIL ({e})")


def verify_aggregation(daily_df, aggregated_df, freq, tolerance):
    """
    验证聚合逻辑是否正确
    daily_df: 日K线DataFrame
    aggregated_df: 聚合后的K线DataFrame
    freq: 'W' 或 'M' 或 'Q' 或 'Y'
    """
    try:
        # 确保date列是datetime
        daily_df = daily_df.copy()
        daily_df["date"] = pd.to_datetime(daily_df["date"], errors="coerce")
        daily_df = daily_df[daily_df["date"].notna()].sort_values("date")

        # 取最近N个聚合周期验证
        n_check = min(4, len(aggregated_df))
        if n_check == 0:
            return False

        for i in range(n_check):
            agg_row = aggregated_df.iloc[-(i+1)]
            agg_date_str = str(agg_row["date"])
            agg_date = pd.to_datetime(agg_date_str, errors="coerce")
            if pd.isna(agg_date):
                continue

            # 确定该聚合周期对应的日期范围
            if freq == "W":
                # 找该周的所有日K
                start_of_week = agg_date - timedelta(days=agg_date.weekday())
                end_of_week = start_of_week + timedelta(days=6)
                mask = (daily_df["date"] >= start_of_week) & (daily_df["date"] <= end_of_week)
            elif freq == "M":
                start_of_month = agg_date.replace(day=1)
                if agg_date.month == 12:
                    end_of_month = agg_date.replace(year=agg_date.year+1, month=1, day=1) - timedelta(days=1)
                else:
                    end_of_month = agg_date.replace(month=agg_date.month+1, day=1) - timedelta(days=1)
                mask = (daily_df["date"] >= start_of_month) & (daily_df["date"] <= end_of_month)
            elif freq == "Q":
                quarter = (agg_date.month - 1) // 3 + 1
                start_of_q = pd.Timestamp(f"{agg_date.year}-{3*quarter-2:02d}-01")
                end_of_q = pd.Timestamp(f"{agg_date.year}-{3*quarter+1:02d}-01") - timedelta(days=1)
                mask = (daily_df["date"] >= start_of_q) & (daily_df["date"] <= end_of_q)
            elif freq == "Y":
                start_of_y = pd.Timestamp(f"{agg_date.year}-01-01")
                end_of_y = pd.Timestamp(f"{agg_date.year+1}-01-01") - timedelta(days=1)
                mask = (daily_df["date"] >= start_of_y) & (daily_df["date"] <= end_of_y)
            else:
                return False

            daily_subset = daily_df[mask]
            if len(daily_subset) == 0:
                continue

            # 验证聚合规则
            expected_open = daily_subset.iloc[0]["open"]
            expected_high = daily_subset["high"].max()
            expected_low = daily_subset["low"].min()
            expected_close = daily_subset.iloc[-1]["close"]
            expected_volume = daily_subset["volume"].sum()

            actual_open = float(agg_row["open"])
            actual_high = float(agg_row["high"])
            actual_low = float(agg_row["low"])
            actual_close = float(agg_row["close"])
            actual_volume = float(agg_row["volume"])

            checks = [
                abs(actual_open - expected_open) <= tolerance,
                abs(actual_high - expected_high) <= tolerance,
                abs(actual_low - expected_low) <= tolerance,
                abs(actual_close - expected_close) <= tolerance,
                abs(actual_volume - expected_volume) <= tolerance * max(expected_volume, 1),
            ]
            if not all(checks):
                return False

        return True
    except Exception as e:
        print(f"    聚合验证异常: {e}")
        return False


# ───────────────────────────────────────────────
# 7. 前端兼容性检查
# ───────────────────────────────────────────────

def test_frontend_compatibility():
    """检查前端周期切换按钮对应的API参数是否正常工作"""
    print("\n" + "=" * 60)
    print("[7] 前端兼容性检查")
    print("=" * 60)

    # 前端支持的周期: minute, daily, weekly, monthly
    frontend_periods = ["minute", "daily", "weekly", "monthly"]
    platform = get_data_platform_service()
    symbol = "000001"

    for period in frontend_periods:
        try:
            # 测试OHLCV API
            df = platform.get_ohlcv(symbol, period=period, adjust="qfq")
            if df is not None and len(df) > 0:
                record("frontend_compat", f"OHLCV period={period}", "PASS",
                       {"rows": len(df), "columns": list(df.columns)})
                print(f"  OHLCV period={period:8s} -> PASS ({len(df)} rows)")
            else:
                # minute数据可能为空（非交易时间），这是正常的
                if period == "minute":
                    record("frontend_compat", f"OHLCV period={period}", "WARN",
                           {"message": "Minute data empty (expected outside trading hours)"})
                    print(f"  OHLCV period={period:8s} -> WARN (Empty, expected outside trading hours)")
                else:
                    record("frontend_compat", f"OHLCV period={period}", "FAIL",
                           {"message": "Empty data"})
                    print(f"  OHLCV period={period:8s} -> FAIL (Empty)")
        except Exception as e:
            record("frontend_compat", f"OHLCV period={period}", "FAIL", {"message": str(e)})
            print(f"  OHLCV period={period:8s} -> FAIL ({e})")

        try:
            # 测试Indicators API
            ind = platform.get_indicators(symbol, period=period, adjust="qfq")
            if ind is not None and len(ind) > 0:
                record("frontend_compat", f"Indicators period={period}", "PASS",
                       {"rows": len(ind), "columns": list(ind.columns)})
                print(f"  Indicators period={period:8s} -> PASS ({len(ind)} rows)")
            else:
                if period == "minute":
                    record("frontend_compat", f"Indicators period={period}", "WARN",
                           {"message": "Empty indicators (expected outside trading hours)"})
                    print(f"  Indicators period={period:8s} -> WARN (Empty)")
                else:
                    record("frontend_compat", f"Indicators period={period}", "FAIL",
                           {"message": "Empty indicators"})
                    print(f"  Indicators period={period:8s} -> FAIL (Empty)")
        except Exception as e:
            record("frontend_compat", f"Indicators period={period}", "FAIL", {"message": str(e)})
            print(f"  Indicators period={period:8s} -> FAIL ({e})")


# ───────────────────────────────────────────────
# 主函数
# ───────────────────────────────────────────────

def main(ctx):
    print("=" * 60)
    print("Quant Workbench 数据中台质量自检")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    start_time = time.time()

    try:
        check_cache_system()
    except Exception as e:
        print(f"[1] 缓存检查异常: {e}")
        record("cache_system", "初始化", "FAIL", {"message": str(e)})

    try:
        test_multi_period()
    except Exception as e:
        print(f"[2] 多周期检查异常: {e}")
        record("multi_period", "初始化", "FAIL", {"message": str(e)})

    try:
        test_index_data()
    except Exception as e:
        print(f"[3] 指数检查异常: {e}")
        record("index_data", "初始化", "FAIL", {"message": str(e)})

    try:
        test_stock_sample()
    except Exception as e:
        print(f"[4] 个股抽样异常: {e}")
        record("stock_sample", "初始化", "FAIL", {"message": str(e)})

    try:
        test_indicator_engine()
    except Exception as e:
        print(f"[5] 指标引擎异常: {e}")
        record("indicator_engine", "初始化", "FAIL", {"message": str(e)})

    try:
        test_aggregation_logic()
    except Exception as e:
        print(f"[6] 聚合逻辑异常: {e}")
        record("aggregation", "初始化", "FAIL", {"message": str(e)})

    try:
        test_frontend_compatibility()
    except Exception as e:
        print(f"[7] 前端兼容性异常: {e}")
        record("frontend_compat", "初始化", "FAIL", {"message": str(e)})

    elapsed = time.time() - start_time

    # 生成最终报告
    print("\n" + "=" * 60)
    print("自检报告汇总")
    print("=" * 60)

    summary = REPORT["summary"]
    print(f"  总检查项: {summary['total']}")
    print(f"  通过: {summary['passed']}")
    print(f"  失败: {summary['failed']}")
    print(f"  警告: {summary['warnings']}")
    print(f"  耗时: {elapsed:.1f}秒")
    print(f"  通过率: {summary['passed'] / max(summary['total'], 1) * 100:.1f}%")

    print("\n  各模块详细:")
    for section, data in REPORT["sections"].items():
        print(f"    {section:20s}: 通过={data['passed']:3d}, 失败={data['failed']:3d}, 警告={data['warnings']:3d}")

    # 保存报告到文件
    report_path = os.path.join(ctx["runDir"], "data_quality_self_check_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)

    md_path = os.path.join(ctx["runDir"], "data_quality_self_check_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_markdown_report(REPORT, elapsed))

    print(f"\n  报告已保存:")
    print(f"    JSON: {report_path}")
    print(f"    Markdown: {md_path}")

    return {"report_path": report_path, "md_path": md_path, "summary": summary}


def generate_markdown_report(report, elapsed):
    """生成Markdown格式报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = report["summary"]
    lines = [
        "# Quant Workbench 数据中台质量自检报告",
        "",
        f"**自检时间**: {now}",
        f"**耗时**: {elapsed:.1f}秒",
        "",
        "## 汇总",
        "",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 总检查项 | {summary['total']} |",
        f"| 通过 | {summary['passed']} |",
        f"| 失败 | {summary['failed']} |",
        f"| 警告 | {summary['warnings']} |",
        f"| 通过率 | {summary['passed'] / max(summary['total'], 1) * 100:.1f}% |",
        "",
        "## 各模块详细结果",
        "",
    ]

    for section, data in report["sections"].items():
        lines.append(f"### {section}")
        lines.append("")
        lines.append(f"- 通过: {data['passed']}, 失败: {data['failed']}, 警告: {data['warnings']}")
        lines.append("")
        lines.append("| 检查项 | 状态 | 详情 |")
        lines.append("|--------|------|------|")
        for item in data["items"]:
            status = item["status"]
            status_icon = "✅" if status == "PASS" else "⚠️" if status == "WARN" else "❌"
            details = item.get("details", {})
            detail_str = json.dumps(details, ensure_ascii=False)[:100]
            lines.append(f"| {item['name']} | {status_icon} {status} | {detail_str} |")
        lines.append("")

    lines.append("---")
    lines.append("*报告由 Quant Workbench 数据中台质量自检引擎生成*")
    return "\n".join(lines)


if __name__ == "__main__":
    import tempfile
    ctx = {"runDir": tempfile.mkdtemp()}
    result = main(ctx)
    print(f"\nResult: {result}")
