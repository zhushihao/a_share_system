#!/usr/bin/env python3
"""
API自检脚本 - 实际验证所有关键端点
"""
import urllib.request
import urllib.error
import json
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:5889/api/v1"
RESULTS_FILE = "api_selfcheck_results_20250625_0700.json"

ENDPOINTS = [
    # 基础健康
    {"name": "health", "method": "GET", "path": "/health", "group": "基础健康"},
    
    # 数据平台
    {"name": "data_health", "method": "GET", "path": "/data/health", "group": "数据平台"},
    {"name": "data_overview", "method": "GET", "path": "/data/overview", "group": "数据平台"},
    {"name": "data_diagnose", "method": "GET", "path": "/data/diagnose/000001", "group": "数据平台"},
    {"name": "data_quality", "method": "GET", "path": "/data/quality", "group": "数据平台"},
    
    # 行情数据
    {"name": "quote_ohlcv", "method": "GET", "path": "/quote/000001/ohlcv", "group": "行情数据"},
    {"name": "quote_indicators", "method": "GET", "path": "/quote/000001/indicators", "group": "行情数据"},
    {"name": "quote_signal", "method": "GET", "path": "/quote/000001/signal", "group": "行情数据"},
    {"name": "quote_resonance", "method": "GET", "path": "/quote/000001/resonance", "group": "行情数据"},
    {"name": "quote_patterns", "method": "GET", "path": "/quote/000001/patterns", "group": "行情数据"},
    {"name": "quote_volume", "method": "GET", "path": "/quote/000001/volume-analysis", "group": "行情数据"},
    {"name": "quote_support_resistance", "method": "GET", "path": "/quote/000001/support-resistance", "group": "行情数据"},
    
    # 批量扫描
    {"name": "scan_resonance", "method": "POST", "path": "/quote/scan/resonance", "group": "批量扫描", "body": json.dumps(["000001", "000002", "600519"]).encode()},
    
    # 信号系统
    {"name": "signals", "method": "GET", "path": "/signals", "group": "信号系统"},
    {"name": "signals_performance", "method": "GET", "path": "/signals/performance", "group": "信号系统"},
    
    # 回测系统
    {"name": "backtest_strategies", "method": "GET", "path": "/backtest/strategies", "group": "回测系统"},
    {"name": "backtest_results", "method": "GET", "path": "/backtest/results", "group": "回测系统"},
    
    # 自选股
    {"name": "watchlist", "method": "GET", "path": "/watchlist", "group": "自选股"},
]

def check_endpoint(ep):
    url = BASE_URL + ep["path"]
    method = ep.get("method", "GET")
    body = ep.get("body", None)
    
    req = urllib.request.Request(url, method=method, data=body)
    if body:
        req.add_header("Content-Type", "application/json")
    
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8")
            latency = round((time.time() - start) * 1000, 2)
            try:
                parsed = json.loads(data)
            except:
                parsed = {"raw": data[:500]}
            return {
                "status": "ok",
                "status_code": resp.status,
                "latency_ms": latency,
                "data": parsed
            }
    except urllib.error.HTTPError as e:
        latency = round((time.time() - start) * 1000, 2)
        return {
            "status": "error",
            "status_code": e.code,
            "latency_ms": latency,
            "error": str(e.reason)
        }
    except Exception as e:
        latency = round((time.time() - start) * 1000, 2)
        return {
            "status": "error",
            "status_code": None,
            "latency_ms": latency,
            "error": str(e)
        }

def main():
    results = {}
    total = len(ENDPOINTS)
    passed = 0
    failed = 0
    
    print(f"=== API自检开始 ({datetime.now().isoformat()}) ===")
    print(f"共 {total} 个端点待验证\n")
    
    for ep in ENDPOINTS:
        name = ep["name"]
        group = ep["group"]
        print(f"  [{group}] {ep['method']} {ep['path']} ...", end=" ")
        result = check_endpoint(ep)
        results[name] = result
        
        if result["status"] == "ok":
            passed += 1
            print(f"  OK ({result['latency_ms']}ms)")
        else:
            failed += 1
            print(f"  FAIL ({result['status_code']} - {result['error']})")
    
    summary = {
        "timestamp": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total * 100, 1),
        "results": results
    }
    
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n=== 自检结果 ===")
    print(f"通过: {passed}/{total} ({summary['pass_rate']}%)")
    print(f"失败: {failed}")
    print(f"结果已保存: {RESULTS_FILE}")
    
    return summary

if __name__ == "__main__":
    main()
