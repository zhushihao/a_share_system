# -*- coding: utf-8 -*-
"""Stage 1 轻量 API 集成测试 - 只测快速端点，跳过数据密集型操作"""
import sys, os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
ALL_OK = True

def _ok(name):
    print(f"  [PASS] {name}")

def _fail(name, err):
    global ALL_OK
    ALL_OK = False
    print(f"  [FAIL] {name}: {err}")

def test_health():
    print("\n[TEST] Health Endpoints")
    try:
        r = client.get("/api/health")
        assert r.status_code == 200, f"status={r.status_code}"
        _ok(f"/api/health -> {r.status_code}")
    except Exception as e:
        _fail("/api/health", e)

    try:
        r = client.get("/api/v1/quote/health")
        assert r.status_code == 200, f"status={r.status_code}"
        _ok(f"/api/v1/quote/health -> {r.status_code}")
    except Exception as e:
        _fail("/api/v1/quote/health", e)

def test_quote_edge():
    print("\n[TEST] Quote Edge Cases")
    try:
        r = client.get("/api/v1/quote/INVALID999")
        assert r.status_code == 404, f"expected 404, got {r.status_code}"
        _ok(f"/api/v1/quote/INVALID999 -> 404")
    except Exception as e:
        _fail("invalid code 404", e)
    
    try:
        r = client.get("/api/v1/quotes/batch")
        assert r.status_code in [400, 422], f"expected 400/422, got {r.status_code}"
        _ok(f"/api/v1/quotes/batch (empty) -> {r.status_code}")
    except Exception as e:
        _fail("batch empty params", e)

def test_watchlist_crud():
    print("\n[TEST] Watchlist CRUD")
    try:
        r = client.get("/api/v1/watchlist")
        assert r.status_code == 200, f"status={r.status_code}"
        _ok(f"GET /api/v1/watchlist -> {r.status_code}")
    except Exception as e:
        _fail("watchlist list", e)
    
    try:
        r = client.post("/api/v1/watchlist", json={"symbol": "TEST0001", "name": "Test", "group": "TestGroup"})
        assert r.status_code == 200, f"status={r.status_code}, body={r.text[:100]}"
        _ok(f"POST /api/v1/watchlist -> {r.status_code}")
    except Exception as e:
        _fail("watchlist add", e)
    
    try:
        r = client.get("/api/v1/watchlist/groups")
        assert r.status_code == 200, f"status={r.status_code}"
        _ok(f"GET /api/v1/watchlist/groups -> {r.status_code}")
    except Exception as e:
        _fail("watchlist groups", e)

def test_quote_ohlcv():
    print("\n[TEST] Quote OHLCV (quick - limit=5)")
    try:
        r = client.get("/api/v1/quote/000001/ohlcv?limit=5")
        assert r.status_code in [200, 404], f"unexpected status={r.status_code}"
        _ok(f"GET /api/v1/quote/000001/ohlcv?limit=5 -> {r.status_code}")
    except Exception as e:
        _fail("ohlcv", e)
    
    try:
        r = client.get("/api/v1/quote/000001/indicators?limit=5")
        assert r.status_code in [200, 404], f"unexpected status={r.status_code}"
        _ok(f"GET /api/v1/quote/000001/indicators?limit=5 -> {r.status_code}")
    except Exception as e:
        _fail("indicators", e)
    
    try:
        r = client.get("/api/v1/quote/000001/score")
        assert r.status_code in [200, 404], f"unexpected status={r.status_code}"
        _ok(f"GET /api/v1/quote/000001/score -> {r.status_code}")
    except Exception as e:
        _fail("score", e)

def test_other_stage_routes():
    print("\n[TEST] Other Stage Routes (import check)")
    for path in [
        "/api/v1/market/indices",
        "/api/v1/signals/strategies",
        "/api/v1/backtest/strategies",
        "/api/v1/data/overview",
        "/api/v1/settings",
        "/api/v1/ai/status",
        "/api/v1/ai/templates",
    ]:
        try:
            r = client.get(path)
            assert r.status_code == 200, f"status={r.status_code}"
            _ok(f"GET {path} -> {r.status_code}")
        except Exception as e:
            _fail(path, e)

if __name__ == "__main__":
    print("="*60)
    print("Stage 1 Light API Integration Test")
    print("="*60)
    test_health()
    test_quote_edge()
    test_watchlist_crud()
    test_quote_ohlcv()
    test_other_stage_routes()
    print("\n" + "="*60)
    if ALL_OK:
        print("Stage 1 Light API Integration: ALL PASS")
    else:
        print("Stage 1 Light API Integration: SOME FAILED")
    sys.exit(0 if ALL_OK else 1)
