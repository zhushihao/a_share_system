#!/usr/bin/env python3
"""Quant Workbench v2.0 第80轮系统自检脚本"""

import urllib.request
import urllib.error
import json
import sys
import os

# Fix Windows encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE = "http://127.0.0.1:5889"

ENDPOINTS = [
    ("/api/health", "GET", "基础健康检查"),
    ("/api/v1/data/health", "GET", "数据平台健康"),
    ("/api/v1/data/overview", "GET", "数据概览"),
    ("/api/v1/data/quality", "GET", "数据质量"),
    ("/api/v1/data/diagnose/000001", "GET", "数据诊断"),
    ("/api/v1/data/stock-list", "GET", "股票列表"),
    ("/api/v1/quote/health", "GET", "行情健康"),
    ("/api/v1/quote/000001/ohlcv", "GET", "K线数据"),
    ("/api/v1/quote/000001/indicators", "GET", "技术指标"),
    ("/api/v1/quote/000001/signal", "GET", "信号合成"),
    ("/api/v1/quote/000001/resonance", "GET", "多周期共振"),
    ("/api/v1/quote/000001/patterns", "GET", "形态识别"),
    ("/api/v1/quote/000001/volume-analysis", "GET", "量价分析"),
    ("/api/v1/quote/000001/support-resistance", "GET", "支撑阻力"),
    ("/api/v1/signals", "GET", "信号列表"),
    ("/api/v1/signals/performance", "GET", "信号绩效"),
    ("/api/v1/backtest/strategies", "GET", "回测策略"),
    ("/api/v1/backtest/results", "GET", "回测结果"),
    ("/api/v1/watchlist", "GET", "自选股"),
    ("/api/v1/market/sentiment", "GET", "市场情绪"),
]

POST_ENDPOINTS = [
    ("/api/v1/quote/scan/resonance", "POST", "批量共振扫描", '["000001", "600519"]'),
    ("/api/v1/signals/scan-daily", "POST", "每日信号扫描", '{"symbols": ["000001", "600519"]}'),
    ("/api/v1/signals/watchlist-scan", "GET", "自选股扫描", None),
]

results = []
passed = 0
failed = 0

def check_get(url, name):
    global passed, failed
    try:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8')
            data = json.loads(body)
            status = resp.status
            key_info = extract_key_info(url, data)
            results.append({"name": name, "method": "GET", "status": status, "ok": True, "info": key_info})
            passed += 1
            return True
    except Exception as e:
        results.append({"name": name, "method": "GET", "status": 0, "ok": False, "info": str(e)[:60]})
        failed += 1
        return False

def check_post(url, name, payload):
    global passed, failed
    try:
        req = urllib.request.Request(url, data=payload.encode('utf-8'), method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode('utf-8')
            data = json.loads(body)
            status = resp.status
            key_info = extract_key_info(url, data)
            results.append({"name": name, "method": "POST", "status": status, "ok": True, "info": key_info})
            passed += 1
            return True
    except Exception as e:
        results.append({"name": name, "method": "POST", "status": 0, "ok": False, "info": str(e)[:60]})
        failed += 1
        return False

def extract_key_info(url, data):
    if "/diagnose" in url:
        diag = data.get('diagnosis', {})
        timeliness = diag.get('timeliness', {})
        return f"quality_score={diag.get('quality_score', 'N/A')}, days_behind={timeliness.get('days_behind', 'N/A')}"
    if "/watchlist" in url:
        return f"count={data.get('count', len(data.get('items', [])))}"
    if "/sentiment" in url:
        return f"up_down={data.get('up_down_ratio', data.get('up_down', 'N/A'))}"
    if "/stock-list" in url:
        return f"count={data.get('count', 'N/A')}"
    if "/health" in url:
        return f"status={data.get('status', 'unknown')}"
    if "/overview" in url:
        return f"stock_count={data.get('stock_count', data.get('total_stocks', 'N/A'))}"
    if "/quality" in url:
        return f"quality_score={data.get('quality_score', 'N/A')}, sample={data.get('sample_size', 'N/A')}"
    if "/ohlcv" in url:
        ohlcv = data.get('ohlcv', data.get('data', []))
        return f"count={len(ohlcv)}条"
    if "/indicators" in url:
        ind = data.get('indicators', data)
        keys = list(ind.keys())[:5] if isinstance(ind, dict) else ['wrapped']
        return f"keys={keys}"
    if "/signal" in url and "/signals" not in url:
        sig = data.get('signal', data.get('signal_type', 'N/A'))
        conf = data.get('confidence', data.get('composite_confidence', 0))
        return f"signal={sig}, conf={round(conf, 3)}"
    if "/resonance" in url and "scan" not in url:
        return f"conf={round(data.get('confidence', 0), 2)}, aligned={data.get('aligned_periods', 'N/A')}"
    if "/patterns" in url:
        return f"patterns={len(data.get('patterns', []))}"
    if "/volume" in url:
        signals = data.get('signals', [])
        return f"signals={len(signals)}"
    if "/support" in url:
        return f"levels={len(data.get('levels', []))}"
    if "/signals" in url and "performance" not in url:
        sigs = data.get('signals', data if isinstance(data, list) else [])
        return f"count={len(sigs)}"
    if "/performance" in url:
        return f"total={data.get('total_signals', 'N/A')}, closed={data.get('closed_signals', 'N/A')}"
    if "/strategies" in url:
        return f"count={len(data.get('strategies', data if isinstance(data, list) else []))}"
    if "/results" in url:
        return f"count={len(data.get('results', data if isinstance(data, list) else []))}"
    if "/scan" in url:
        return f"matched={len(data)} items" if isinstance(data, list) else str(data)[:60]
    return str(data)[:40]

print("="*60)
print(f"Quant Workbench v2.0 第80轮系统自检")
print(f"BASE: {BASE}")
print("="*60)

for path, method, name in ENDPOINTS:
    check_get(f"{BASE}{path}", name)

for path, method, name, payload in POST_ENDPOINTS:
    if method == "POST":
        check_post(f"{BASE}{path}", name, payload)
    else:
        check_get(f"{BASE}{path}", name)

print(f"\n{'#'*60}")
print(f"验证结果: 通过 {passed}/{passed+failed}")
print(f"{'#'*60}\n")

for r in results:
    ok_mark = "OK" if r["ok"] else "FAIL"
    print(f"[{ok_mark:>4}] [{r['method']:>4}] {r['status']:>3} | {r['name']:<20} | {r['info']}")

# Save results
with open("check_results_now.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n详细结果已保存: check_results_now.json")

sys.exit(0 if failed == 0 else 1)
