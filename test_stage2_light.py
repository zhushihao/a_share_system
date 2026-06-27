# -*- coding: utf-8 -*-
"""Stage 2 超轻量验证 - 只测快速端点，跳过耗时的 with-quotes/with-indicators"""
import sys, os
PROJECT_ROOT = os.getcwd()
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

ALL_OK = True

def _ok(name):
    print(f"  [PASS] {name}")

def _fail(name, err):
    global ALL_OK
    ALL_OK = False
    print(f"  [FAIL] {name}: {err}")

from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)

# Test 1: market imports
print("\n[TEST] market.py import")
try:
    from backend.api import market
    assert hasattr(market, "router")
    _ok("market.router exists")
except Exception as e:
    _fail("market import", e)

# Test 2: market endpoints (fast)
print("\n[TEST] market endpoints (fast)")
for path in ["/api/v1/market/indices", "/api/v1/market/sentiment", "/api/v1/market/hotspots", "/api/v1/market/limit-up"]:
    try:
        r = client.get(path)
        assert r.status_code == 200, f"status={r.status_code}"
        _ok(f"GET {path} -> {r.status_code}")
    except Exception as e:
        _fail(path, e)

# Test 3: watchlist import
print("\n[TEST] watchlist.py import")
try:
    from backend.api import watchlist
    assert hasattr(watchlist, "router")
    _ok("watchlist.router exists")
except Exception as e:
    _fail("watchlist import", e)

# Test 4: watchlist basic endpoints (fast, no quotes)
print("\n[TEST] watchlist basic endpoints (fast)")
for path in ["/api/v1/watchlist", "/api/v1/watchlist/groups"]:
    try:
        r = client.get(path)
        assert r.status_code == 200, f"status={r.status_code}"
        _ok(f"GET {path} -> {r.status_code}")
    except Exception as e:
        _fail(path, e)

# Test 5: frontend files exist
print("\n[TEST] Stage 2 frontend files")
for fname in ["Dashboard.tsx", "Watchlist.tsx", "StockDetail.tsx"]:
    fpath = os.path.join(PROJECT_ROOT, "frontend_react", "src", "pages", fname)
    try:
        assert os.path.exists(fpath), f"missing {fname}"
        sz = os.path.getsize(fpath)
        _ok(f"{fname} exists ({sz} bytes)")
    except Exception as e:
        _fail(fname, e)

print("\n" + "="*60)
if ALL_OK:
    print("Stage 2 light verify: ALL PASS")
else:
    print("Stage 2 light verify: SOME FAILED")
sys.exit(0 if ALL_OK else 1)
