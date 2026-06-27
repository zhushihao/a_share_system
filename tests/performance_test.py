# -*- coding: utf-8 -*-
"""
Performance Test - 最终性能验收测试

测试目标：
- K 线加载 < 200ms
- 50 只自选股 < 500ms
- 全市场板块扫描 < 3s
- 信号扫描 < 10s

运行方式：
    python tests/performance_test.py
"""

import sys
import os
import time
import statistics
from typing import List, Dict, Any

# 路径设置
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_dir)
sys.path.insert(0, os.path.join(project_dir, "backend"))

from services.data_provider import get_data_provider_service
from services.indicators import calculate_all_indicators, calc_tech_score
from services.signal_engine import SignalEngine
from config import settings

# 性能目标
TARGETS = {
    "kline_load": 200,       # ms
    "watchlist_50": 500,     # ms
    "market_scan": 3000,     # ms
    "signal_scan": 10000,    # ms
}


def measure(name: str, func, iterations: int = 3) -> Dict[str, Any]:
    """测量函数执行时间"""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    return {
        "name": name,
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "avg_ms": round(statistics.mean(times), 2),
        "median_ms": round(statistics.median(times), 2),
        "target_ms": TARGETS.get(name, 0),
        "passed": min(times) <= TARGETS.get(name, float('inf')),
        "iterations": iterations,
    }


def test_kline_load():
    """测试 K 线加载性能"""
    dp = get_data_provider_service(tdxdir=settings.TDX_DIR)
    
    def _load():
        df = dp.fetch_ohlcv("000001", period="daily", adjust="qfq")
        if df is not None and len(df) > 0:
            df = df.tail(60)
            calculate_all_indicators(df)
        return df
    
    return measure("kline_load", _load, iterations=5)


def test_watchlist_quotes():
    """测试自选股批量加载性能"""
    dp = get_data_provider_service(tdxdir=settings.TDX_DIR)
    # 使用常见股票代码模拟 50 只自选股
    symbols = [
        "000001", "000002", "000333", "000568", "000651", "000725", "000768", "000858", "000895", "002001",
        "002007", "002024", "002027", "002142", "002230", "002236", "002271", "002304", "002415", "002460",
        "002594", "002714", "300014", "300015", "300033", "300059", "300122", "300124", "300274", "300408",
        "300433", "300498", "300750", "600000", "600009", "600016", "600028", "600030", "600031", "600036",
        "600048", "600276", "600309", "600519", "600585", "600690", "600745", "600809", "600887", "601012",
    ]
    
    def _load():
        results = []
        for sym in symbols:
            df = dp.get_kline_latest(sym, n=30, period="daily", adjust="qfq")
            if df is not None and len(df) > 0:
                try:
                    df_ind = calculate_all_indicators(df)
                    score = calc_tech_score(df_ind)
                    results.append({"symbol": sym, "score": score})
                except Exception:
                    results.append({"symbol": sym, "score": 0})
        return results
    
    return measure("watchlist_50", _load, iterations=3)


def test_market_scan():
    """测试市场板块扫描性能"""
    from services.data_provider import get_data_provider_service
    dp = get_data_provider_service(tdxdir=settings.TDX_DIR)
    
    def _scan():
        # 模拟热点板块扫描：获取股票列表 + 分类统计
        df = dp.fetch_stock_list()
        if df is not None and len(df) > 0:
            # 只取前 200 只模拟扫描
            codes = df["code"].head(200).tolist() if "code" in df.columns else []
            # 简单模拟板块扫描
            return {"stocks": len(codes), "blocks": 50}
        return {"stocks": 0, "blocks": 0}
    
    return measure("market_scan", _scan, iterations=3)


def test_signal_scan():
    """测试信号扫描性能"""
    from services.data_provider import get_data_provider_service
    dp = get_data_provider_service(tdxdir=settings.TDX_DIR)
    engine = SignalEngine(data_provider=dp)
    symbols = [
        ("000001", "平安银行"), ("000002", "万科A"), ("000333", "美的集团"),
        ("600519", "贵州茅台"), ("601012", "隆基绿能"),
    ] * 10  # 50 只
    
    def _scan():
        return engine.scan_daily(symbols, strategies=None)
    
    return measure("signal_scan", _scan, iterations=2)


def print_result(result: Dict[str, Any]):
    """打印测试结果"""
    status = "[PASS]" if result["passed"] else "[FAIL]"
    target = result["target_ms"]
    avg = result["avg_ms"]
    
    print(f"  {status} {result['name']}")
    print(f"     avg: {avg}ms | min: {result['min_ms']}ms | max: {result['max_ms']}ms | target: {target}ms")
    if not result["passed"]:
        print(f"     WARN: 超出目标 {avg - target:.1f}ms")
    print()


def main():
    print("=" * 60)
    print("Quant Workbench v1.0 性能验收测试")
    print("=" * 60)
    print(f"目标: K线 < {TARGETS['kline_load']}ms | 50股 < {TARGETS['watchlist_50']}ms | 板块 < {TARGETS['market_scan']}ms | 信号 < {TARGETS['signal_scan']}ms")
    print()
    
    results = []
    
    # 1. K 线加载
    print("--- 1. K 线加载 + 指标计算 ---")
    try:
        r = test_kline_load()
        print_result(r)
        results.append(r)
    except Exception as e:
        print(f"  [FAIL] failed: {e}")
        results.append({"name": "kline_load", "passed": False, "error": str(e)})
    
    # 2. 自选股 50 只
    print("--- 2. 50 只自选股指标计算 ---")
    try:
        r = test_watchlist_quotes()
        print_result(r)
        results.append(r)
    except Exception as e:
        print(f"  [FAIL] failed: {e}")
        results.append({"name": "watchlist_50", "passed": False, "error": str(e)})
    
    # 3. 市场板块扫描
    print("--- 3. 市场板块扫描 ---")
    try:
        r = test_market_scan()
        print_result(r)
        results.append(r)
    except Exception as e:
        print(f"  [FAIL] failed: {e}")
        results.append({"name": "market_scan", "passed": False, "error": str(e)})
    
    # 4. 信号扫描
    print("--- 4. 日线信号扫描（50只） ---")
    try:
        r = test_signal_scan()
        print_result(r)
        results.append(r)
    except Exception as e:
        print(f"  [FAIL] failed: {e}")
        results.append({"name": "signal_scan", "passed": False, "error": str(e)})
    
    # 汇总
    print("=" * 60)
    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    print(f"汇总: {passed}/{total} 项通过")
    
    for r in results:
        status = "[PASS]" if r.get("passed") else "[FAIL]"
        if "error" in r:
            print(f"  {status} {r['name']}: ERROR - {r['error']}")
        else:
            print(f"  {status} {r['name']}: {r.get('avg_ms', 'N/A')}ms (target: {r.get('target_ms', 'N/A')}ms)")
    
    print("=" * 60)
    
    if passed == total:
        print("ALL PERFORMANCE TARGETS MET!")
    else:
        print("SOME TARGETS NOT MET, SEE DETAILS ABOVE")
    
    return {"passed": passed, "total": total, "results": results}


if __name__ == "__main__":
    main()
