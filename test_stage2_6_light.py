# -*- coding: utf-8 -*-
"""Stage 2-6 轻量端点验证 - 只测快速接口，跳过数据密集型操作"""
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

def test_stage2_market():
    print("\n[STAGE 2] Market API")
    for path in ["/api/v1/market/indices", "/api/v1/market/sentiment", "/api/v1/market/hotspots", "/api/v1/market/limit-up"]:
        try:
            r = client.get(path)
            assert r.status_code == 200, f"status={r.status_code}"
            _ok(f"GET {path} -> {r.status_code}")
        except Exception as e:
            _fail(path, e)

def test_stage2_watchlist_extended():
    print("\n[STAGE 2] Watchlist Extended API")
    for path in ["/api/v1/watchlist/groups"]:
        try:
            r = client.get(path)
            assert r.status_code == 200, f"status={r.status_code}"
            _ok(f"GET {path} -> {r.status_code}")
        except Exception as e:
            _fail(path, e)

def test_stage3_signals():
    print("\n[STAGE 3] Signals API")
    for path in ["/api/v1/signals/strategies", "/api/v1/signals"]:
        try:
            r = client.get(path)
            assert r.status_code == 200, f"status={r.status_code}"
            _ok(f"GET {path} -> {r.status_code}")
        except Exception as e:
            _fail(path, e)

def test_stage4_backtest():
    print("\n[STAGE 4] Backtest API")
    try:
        r = client.get("/api/v1/backtest/strategies")
        assert r.status_code == 200, f"status={r.status_code}"
        _ok(f"GET /api/v1/backtest/strategies -> {r.status_code}")
    except Exception as e:
        _fail("/api/v1/backtest/strategies", e)

def test_stage4_data():
    print("\n[STAGE 4] Data Management API")
    for path in ["/api/v1/data/overview", "/api/v1/data/health"]:
        try:
            r = client.get(path)
            assert r.status_code == 200, f"status={r.status_code}"
            _ok(f"GET {path} -> {r.status_code}")
        except Exception as e:
            _fail(path, e)

def test_stage4_settings():
    print("\n[STAGE 4] Settings API")
    try:
        r = client.get("/api/v1/settings")
        assert r.status_code == 200, f"status={r.status_code}"
        _ok(f"GET /api/v1/settings -> {r.status_code}")
    except Exception as e:
        _fail("/api/v1/settings", e)

def test_stage5_ai():
    print("\n[STAGE 5] AI Research API")
    for path in ["/api/v1/ai/status", "/api/v1/ai/templates"]:
        try:
            r = client.get(path)
            assert r.status_code == 200, f"status={r.status_code}"
            _ok(f"GET {path} -> {r.status_code}")
        except Exception as e:
            _fail(path, e)

def test_stage6_onboarding():
    print("\n[STAGE 6] Onboarding")
    try:
        from backend.services.onboarding import get_onboarding_service
        svc = get_onboarding_service()
        report = svc.generate_report()
        assert report["ready"] == True, f"ready={report['ready']}"
        _ok(f"onboarding.generate_report() -> ready={report['ready']}")
    except Exception as e:
        _fail("onboarding", e)

def test_stage6_openapi():
    print("\n[STAGE 6] OpenAPI Documentation")
    try:
        r = client.get("/openapi.json")
        assert r.status_code == 200, f"status={r.status_code}"
        data = r.json()
        paths = list(data.get("paths", {}).keys())
        _ok(f"OpenAPI paths count: {len(paths)}")
    except Exception as e:
        _fail("/openapi.json", e)

if __name__ == "__main__":
    print("="*60)
    print("Stage 2-6 Light Endpoint Verification")
    print("="*60)
    test_stage2_market()
    test_stage2_watchlist_extended()
    test_stage3_signals()
    test_stage4_backtest()
    test_stage4_data()
    test_stage4_settings()
    test_stage5_ai()
    test_stage6_onboarding()
    test_stage6_openapi()
    print("\n" + "="*60)
    if ALL_OK:
        print("Stage 2-6 Light Endpoint Verification: ALL PASS")
    else:
        print("Stage 2-6 Light Endpoint Verification: SOME FAILED")
    sys.exit(0 if ALL_OK else 1)
