# -*- coding: utf-8 -*-
"""
Quant Workbench v1.0 — 全阶段 API 集成测试
覆盖 Stage 1~6 所有端点的 happy path + edge case

运行方式:
    python test_all_stages.py
"""

import sys, os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
passed = 0
failed = 0


def test(name, method, url, expected_status=200, check=None, **kwargs):
    """执行单条测试"""
    global passed, failed
    try:
        if method == "GET":
            resp = client.get(url, **kwargs)
        elif method == "POST":
            resp = client.post(url, **kwargs)
        elif method == "DELETE":
            resp = client.delete(url, **kwargs)
        elif method == "PUT":
            resp = client.put(url, **kwargs)
        else:
            raise ValueError(f"Unknown method: {method}")

        status_ok = resp.status_code == expected_status
        check_ok = True
        detail = ""
        if check and status_ok:
            try:
                check_ok = check(resp.json())
            except Exception as e:
                check_ok = False
                detail = str(e)

        if status_ok and check_ok:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name} - status={resp.status_code}, expected={expected_status}, body={resp.text[:200]}, detail={detail}")
            failed += 1
    except Exception as e:
        print(f"  [FAIL] {name} - exception: {e}")
        failed += 1


# ───────────────────────────────────────────────
# Stage 1: 数据层
# ───────────────────────────────────────────────
print("\n=== Stage 1: 数据层 ===")

# 1. Health
print("\n[1.1] Health & Quote")
test("Health check", "GET", "/api/health", check=lambda d: d.get("status") == "ok")
test("Quote health", "GET", "/api/v1/quote/health", check=lambda d: "sources" in d)

# 2. Realtime
print("\n[1.2] Realtime Quote")
test("Quote 000001", "GET", "/api/v1/quote/000001", check=lambda d: d.get("symbol") == "000001")
test("Quote 600519", "GET", "/api/v1/quote/600519", check=lambda d: d.get("symbol") == "600519")

# 3. Batch
print("\n[1.3] Batch Quotes")
test("Batch quotes", "GET", "/api/v1/quotes/batch?symbols=000001,600519", check=lambda d: d.get("count", 0) >= 0)
test("Batch empty symbols", "GET", "/api/v1/quotes/batch?symbols=", expected_status=400)

# 4. OHLCV
print("\n[1.4] OHLCV")
test("OHLCV 000001", "GET", "/api/v1/quote/000001/ohlcv", check=lambda d: d.get("count", 0) > 0 and "data" in d)
test("OHLCV limit", "GET", "/api/v1/quote/000001/ohlcv?limit=10", check=lambda d: d.get("count") == 10)
test("OHLCV invalid symbol", "GET", "/api/v1/quote/INVALID999/ohlcv", expected_status=404)

# 5. Indicators
print("\n[1.5] Indicators")
test("Indicators 000001", "GET", "/api/v1/quote/000001/indicators?limit=10", check=lambda d: "indicators" in d and "data" in d)
test("Indicators 600519", "GET", "/api/v1/quote/600519/indicators", check=lambda d: "indicators" in d)

# 6. Tech Score
print("\n[1.6] Tech Score")
test("Score 000001", "GET", "/api/v1/quote/000001/score", check=lambda d: 0 <= d.get("score", -1) <= 100)
test("Score 600519", "GET", "/api/v1/quote/600519/score", check=lambda d: 0 <= d.get("score", -1) <= 100)
test("Score invalid", "GET", "/api/v1/quote/INVALID999/score", expected_status=404)

# 7. Watchlist CRUD
print("\n[1.7] Watchlist CRUD")
client.delete("/api/v1/watchlist/TEST001")
client.delete("/api/v1/watchlist/TEST002")

test("Add watchlist", "POST", "/api/v1/watchlist", json={"symbol": "TEST001", "name": "测试股票1", "group": "测试组"}, check=lambda d: d.get("status") == "ok")
test("Add watchlist 2", "POST", "/api/v1/watchlist", json={"symbol": "TEST002", "name": "测试股票2", "group": "测试组"}, check=lambda d: d.get("status") == "ok")
test("List watchlist", "GET", "/api/v1/watchlist", check=lambda d: d.get("count", 0) >= 2)
test("List by group", "GET", "/api/v1/watchlist?group=测试组", check=lambda d: all(item.get("group") == "测试组" for item in d.get("items", [])))
test("Update group", "PUT", "/api/v1/watchlist/TEST001/group", json={"group": "新分组"}, check=lambda d: d.get("group") == "新分组")
test("List groups", "GET", "/api/v1/watchlist/groups", check=lambda d: "新分组" in d.get("groups", []))
test("Delete watchlist", "DELETE", "/api/v1/watchlist/TEST001", check=lambda d: d.get("status") == "ok")
test("Delete non-existent", "DELETE", "/api/v1/watchlist/NOTEXIST", expected_status=404)

# 8. Watchlist with quotes
print("\n[1.8] Watchlist with quotes")
test("Watchlist with quotes", "GET", "/api/v1/watchlist/with-quotes", check=lambda d: "count" in d and "items" in d)

client.delete("/api/v1/watchlist/TEST002")


# ───────────────────────────────────────────────
# Stage 2: 核心模块
# ───────────────────────────────────────────────
print("\n=== Stage 2: 核心模块 ===")

print("\n[2.1] Market Dashboard")
test("Market indices", "GET", "/api/v1/market/indices", check=lambda d: "indices" in d or "data" in d)
test("Market sentiment", "GET", "/api/v1/market/sentiment", check=lambda d: "up_down_ratio" in d or "advancing" in d)
test("Market hotspots", "GET", "/api/v1/market/hotspots", check=lambda d: isinstance(d.get("items", d.get("hotspots", [])), list))
test("Market limit-up", "GET", "/api/v1/market/limit-up", check=lambda d: isinstance(d.get("items", d.get("limit_up", [])), list))

print("\n[2.2] Stock Detail")
test("Stock detail 000001", "GET", "/api/v1/quote/000001", check=lambda d: d.get("symbol") == "000001")
test("Stock detail invalid", "GET", "/api/v1/quote/INVALID999", expected_status=404)


# ───────────────────────────────────────────────
# Stage 3: 扩展模块
# ───────────────────────────────────────────────
print("\n=== Stage 3: 扩展模块 ===")

print("\n[3.1] Signals")
test("Signals list", "GET", "/api/v1/signals", check=lambda d: isinstance(d.get("signals", []), list))
test("Signals strategies", "GET", "/api/v1/signals/strategies", check=lambda d: isinstance(d.get("strategies", []), list))
test("Signals stats", "GET", "/api/v1/signals/stats", check=lambda d: "total_signals" in d)

test("Signals watchlist-scan", "GET", "/api/v1/signals/watchlist-scan", check=lambda d: d.get("status") == "ok")

# Acknowledge & delete (need a signal first)
resp = client.get("/api/v1/signals")
if resp.status_code == 200:
    sigs = resp.json().get("signals", [])
    if len(sigs) > 0:
        sid = sigs[0].get("id")
        if sid:
            test("Signals acknowledge", "POST", f"/api/v1/signals/{sid}/acknowledge", check=lambda d: d.get("status") == "ok")


# ───────────────────────────────────────────────
# Stage 4: 高级模块
# ───────────────────────────────────────────────
print("\n=== Stage 4: 高级模块 ===")

print("\n[4.1] Backtest")
test("Backtest strategies", "GET", "/api/v1/backtest/strategies", check=lambda d: d.get("status") == "ok")
test("Backtest custom template", "GET", "/api/v1/backtest/custom-template", check=lambda d: d.get("status") == "ok")

test("Backtest run", "POST", "/api/v1/backtest/run", json={
    "symbol": "000001", "strategy_name": "dual_ma", "start_date": "2024-11-01", "end_date": "2024-12-31", "initial_cash": 100000
}, check=lambda d: d.get("status") == "ok" and "result" in d)

test("Backtest run invalid", "POST", "/api/v1/backtest/run", json={
    "symbol": "INVALID999", "strategy_name": "dual_ma", "start_date": "2024-11-01", "end_date": "2024-12-31", "initial_cash": 100000
}, check=lambda d: d.get("status") == "ok" and d.get("result", {}).get("error") is not None)

test("Backtest results list", "GET", "/api/v1/backtest/results", check=lambda d: d.get("status") == "ok")

print("\n[4.2] Data Management")
test("Data overview", "GET", "/api/v1/data/overview", check=lambda d: d.get("status") == "ok")
test("Data health", "GET", "/api/v1/data/health", check=lambda d: d.get("status") == "ok")
test("Data stock-list", "GET", "/api/v1/data/stock-list", check=lambda d: d.get("status") == "ok")

test("Data diagnose", "GET", "/api/v1/data/diagnose?symbol=000001", check=lambda d: d.get("status") == "ok")

test("Data export", "GET", "/api/v1/data/export?symbol=000001&format=csv", check=lambda d: d.get("status") == "ok")

print("\n[4.3] Settings")
test("Settings GET", "GET", "/api/v1/settings", check=lambda d: d.get("status") == "ok" and isinstance(d.get("settings", {}), dict))
test("Settings batch GET", "GET", "/api/v1/settings/batch?keys=theme,tdx_dir", check=lambda d: d.get("status") == "ok")


# ───────────────────────────────────────────────
# Stage 5: AI 投研
# ───────────────────────────────────────────────
print("\n=== Stage 5: AI 投研 ===")

print("\n[5.1] AI Status & Templates")
test("AI status", "GET", "/api/v1/ai/status", check=lambda d: "enabled" in d or "api_key_configured" in d)
test("AI templates", "GET", "/api/v1/ai/templates", check=lambda d: isinstance(d, list))
test("AI templates category", "GET", "/api/v1/ai/templates?category=technical", check=lambda d: isinstance(d, list))

print("\n[5.2] AI Chat & Context")
test("AI chat", "POST", "/api/v1/ai/chat", json={"message": "分析一下", "context": "stock"}, check=lambda d: "reply" in d)
test("AI context", "POST", "/api/v1/ai/context", params={"symbol": "000001", "context_type": "stock"}, check=lambda d: "data" in d or "context" in d)


# ───────────────────────────────────────────────
# Stage 6: 部署验收
# ───────────────────────────────────────────────
print("\n=== Stage 6: 部署验收 ===")

print("\n[6.1] Onboarding & Health")
test("Health final", "GET", "/api/health", check=lambda d: d.get("status") == "ok")

# OpenAPI docs 返回 HTML，不解析 JSON，只看 status
def test_html(name, url):
    global passed, failed
    try:
        resp = client.get(url)
        if resp.status_code == 200:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name} - status={resp.status_code}")
            failed += 1
    except Exception as e:
        print(f"  [FAIL] {name} - exception: {e}")
        failed += 1

test_html("OpenAPI docs", "/docs")
test_html("ReDoc", "/redoc")


# ───────────────────────────────────────────────
# 汇总
# ───────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"汇总: {passed} passed, {failed} failed")
print(f"{'=' * 60}")

if failed > 0:
    sys.exit(1)
else:
    print("ALL STAGES PASSED!")
