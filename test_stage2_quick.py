# -*- coding: utf-8 -*-
"""Stage 2 快速验证脚本"""
import sys, os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

ALL_OK = True

def _ok(name):
    print(f"  [PASS] {name}")

def _fail(name, err):
    global ALL_OK
    ALL_OK = False
    print(f"  [FAIL] {name}: {err}")

# Test market API imports
print("\n[TEST] market.py import")
try:
    from backend.api import market
    assert hasattr(market, "router")
    _ok("market.router exists")
except Exception as e:
    _fail("market import", e)

# Test quote API imports
print("\n[TEST] quote.py import")
try:
    from backend.api import quote
    assert hasattr(quote, "router")
    _ok("quote.router exists")
except Exception as e:
    _fail("quote import", e)

# Test watchlist API imports
print("\n[TEST] watchlist.py import")
try:
    from backend.api import watchlist
    assert hasattr(watchlist, "router")
    _ok("watchlist.router exists")
except Exception as e:
    _fail("watchlist import", e)

# Test with-quotes / with-indicators parallel (light: 1 stock)
print("\n[TEST] watchlist with-quotes / with-indicators (1 stock)")
try:
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)

    # add a stock first
    r = client.post("/api/v1/watchlist", json={"symbol": "000001", "name": "平安银行", "group": "测试"})
    assert r.status_code == 200 or r.status_code == 201 or r.status_code == 409, f"add failed: {r.status_code}"
    _ok(f"add watchlist -> {r.status_code}")

    # with-quotes
    r = client.get("/api/v1/watchlist/with-quotes")
    assert r.status_code == 200, f"with-quotes failed: {r.status_code}"
    data = r.json()
    _ok(f"with-quotes -> {r.status_code}, items={len(data.get('data', []))}")

    # with-indicators
    r = client.get("/api/v1/watchlist/with-indicators")
    assert r.status_code == 200, f"with-indicators failed: {r.status_code}"
    data = r.json()
    _ok(f"with-indicators -> {r.status_code}, items={len(data.get('data', []))}")
except Exception as e:
    _fail("watchlist extensions", e)

# Test tech score
print("\n[TEST] calc_tech_score")
try:
    import pandas as pd
    import numpy as np
    from backend.services.indicators import calculate_all_indicators, calc_tech_score
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    df = pd.DataFrame({
        "open": 100 + np.random.randn(100).cumsum(),
        "high": 102 + np.random.randn(100).cumsum(),
        "low": 98 + np.random.randn(100).cumsum(),
        "close": 100 + np.random.randn(100).cumsum(),
        "volume": np.random.randint(1000000, 5000000, 100),
    }, index=dates)
    df["high"] = df[["open", "close", "high"]].max(axis=1) + 1
    df["low"] = df[["open", "close", "low"]].min(axis=1) - 1
    ind = calculate_all_indicators(df)
    score = calc_tech_score(ind)
    assert 0 <= score <= 100
    _ok(f"tech_score -> {score}")
except Exception as e:
    _fail("tech_score", e)

print("\n" + "="*60)
if ALL_OK:
    print("Stage 2 quick verify: ALL PASS")
else:
    print("Stage 2 quick verify: SOME FAILED")
