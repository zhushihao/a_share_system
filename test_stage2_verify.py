# -*- coding: utf-8 -*-
"""
Stage 2 验证脚本 - 测试核心模块后端 API
"""
import sys, os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

print("=" * 60)
print("Stage 2 Verification")
print("=" * 60)

errors = []

# --- market.py ---
print("\n[TEST] market.py (Dashboard API)")

try:
    r = client.get("/api/v1/market/indices")
    assert r.status_code == 200, "indices status=%d" % r.status_code
    data = r.json()
    print("  [OK] GET /api/v1/market/indices -> 200, %d indices" % len(data.get("indices", [])))
except Exception as e:
    errors.append("market indices: %s" % e)
    print("  [FAIL] market indices: %s" % e)

try:
    r = client.get("/api/v1/market/sentiment")
    assert r.status_code == 200, "sentiment status=%d" % r.status_code
    print("  [OK] GET /api/v1/market/sentiment -> 200")
except Exception as e:
    errors.append("market sentiment: %s" % e)
    print("  [FAIL] market sentiment: %s" % e)

try:
    r = client.get("/api/v1/market/hotspots")
    assert r.status_code == 200, "hotspots status=%d" % r.status_code
    data = r.json()
    print("  [OK] GET /api/v1/market/hotspots -> 200, %d sectors" % len(data.get("sectors", [])))
except Exception as e:
    errors.append("market hotspots: %s" % e)
    print("  [FAIL] market hotspots: %s" % e)

try:
    r = client.get("/api/v1/market/limit-up")
    assert r.status_code == 200, "limit-up status=%d" % r.status_code
    print("  [OK] GET /api/v1/market/limit-up -> 200")
except Exception as e:
    errors.append("market limit-up: %s" % e)
    print("  [FAIL] market limit-up: %s" % e)

# --- watchlist.py (Stage 2 扩展) ---
print("\n[TEST] watchlist.py (Stage 2 extended)")

try:
    r = client.get("/api/v1/watchlist/groups")
    assert r.status_code == 200, "groups status=%d" % r.status_code
    print("  [OK] GET /api/v1/watchlist/groups -> 200")
except Exception as e:
    errors.append("watchlist groups: %s" % e)
    print("  [FAIL] watchlist groups: %s" % e)

try:
    r = client.get("/api/v1/watchlist/with-quotes")
    assert r.status_code == 200, "with-quotes status=%d" % r.status_code
    print("  [OK] GET /api/v1/watchlist/with-quotes -> 200")
except Exception as e:
    errors.append("watchlist with-quotes: %s" % e)
    print("  [FAIL] watchlist with-quotes: %s" % e)

try:
    r = client.get("/api/v1/watchlist/with-indicators")
    assert r.status_code == 200, "with-indicators status=%d" % r.status_code
    print("  [OK] GET /api/v1/watchlist/with-indicators -> 200")
except Exception as e:
    errors.append("watchlist with-indicators: %s" % e)
    print("  [FAIL] watchlist with-indicators: %s" % e)

# --- Frontend 文件检查 ---
print("\n[TEST] Frontend files check")

frontend_files = [
    "frontend_react/src/pages/Dashboard.tsx",
    "frontend_react/src/pages/Watchlist.tsx",
    "frontend_react/src/pages/StockDetail.tsx",
    "frontend_react/src/App.tsx",
    "frontend_react/src/api/client.ts",
]

for f in frontend_files:
    # 使用正斜杠统一路径
    path = os.path.join(PROJECT_ROOT, f.replace('/', os.sep))
    # 备选：直接尝试正斜杠（某些 Python 版本支持）
    path_alt = os.path.join(PROJECT_ROOT, f)
    if os.path.exists(path) or os.path.exists(path_alt):
        size = os.path.getsize(path) if os.path.exists(path) else os.path.getsize(path_alt)
        print("  [OK] %s (%d bytes)" % (f, size))
    else:
        # 调试：打印实际路径
        print("  [DEBUG] path=%s exists=%s" % (path, os.path.exists(path)))
        print("  [DEBUG] path_alt=%s exists=%s" % (path_alt, os.path.exists(path_alt)))
        errors.append("frontend missing: %s" % f)
        print("  [FAIL] %s missing" % f)

print("\n" + "=" * 60)
if errors:
    print("FAILED: %d errors" % len(errors))
    for e in errors:
        print("  - %s" % e)
    sys.exit(1)
else:
    print("ALL Stage 2 TESTS PASSED")
    sys.exit(0)
