# -*- coding: utf-8 -*-
"""Stage 1 API 集成测试：quote + watchlist"""
import sys
import os

project_root = r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system"
os.chdir(project_root)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if os.path.join(project_root, "backend") not in sys.path:
    sys.path.insert(0, os.path.join(project_root, "backend"))

from fastapi.testclient import TestClient

# 导入 main.py 中的 app
from backend.main import app

client = TestClient(app)

print("=== Stage 1 API Integration Test ===\n")

# ── Cleanup residual watchlist data ──
client.delete("/api/v1/watchlist/600519")
client.delete("/api/v1/watchlist/000001")
client.delete("/api/v1/watchlist/600036")

# ── quote ──

print("[QUOTE API]")

# 1. health
r = client.get("/api/v1/quote/health")
assert r.status_code == 200, f"quote/health failed: {r.status_code}"
print(f"  GET /quote/health -> {r.status_code} OK")

# 2. invalid symbol -> 404
r = client.get("/api/v1/quote/INVALID999")
assert r.status_code == 404, f"invalid symbol should 404, got {r.status_code}"
print(f"  GET /quote/INVALID999 -> {r.status_code} OK (edge case)")

# 3. batch empty -> 422
r = client.get("/api/v1/quotes/batch?symbols=")
assert r.status_code == 422, f"empty batch should 422, got {r.status_code}"
print(f"  GET /quotes/batch?symbols= -> {r.status_code} OK (edge case)")

# 4. ohlcv happy path
r = client.get("/api/v1/quote/000001/ohlcv?limit=5")
assert r.status_code == 200, f"ohlcv failed: {r.status_code}"
body = r.json()
assert "data" in body and len(body["data"]) == 5
print(f"  GET /quote/000001/ohlcv -> {r.status_code} OK ({len(body['data'])} rows)")

# 5. ohlcv invalid -> 404
r = client.get("/api/v1/quote/INVALID999/ohlcv")
assert r.status_code == 404, f"invalid ohlcv should 404, got {r.status_code}"
print(f"  GET /quote/INVALID999/ohlcv -> {r.status_code} OK (edge case)")

# 6. indicators
r = client.get("/api/v1/quote/000001/indicators?limit=5")
assert r.status_code == 200, f"indicators failed: {r.status_code}"
body = r.json()
assert "indicators" in body and "data" in body
print(f"  GET /quote/000001/indicators -> {r.status_code} OK ({len(body['indicators'])} indicators)")

# 7. score
r = client.get("/api/v1/quote/000001/score")
assert r.status_code == 200, f"score failed: {r.status_code}"
body = r.json()
assert 0 <= body["score"] <= 100
print(f"  GET /quote/000001/score -> {r.status_code} OK (score={body['score']})")

# ── watchlist ──

print("\n[WATCHLIST API]")

# 1. list (post-cleanup)
r = client.get("/api/v1/watchlist")
assert r.status_code == 200
body = r.json()
print(f"  GET /watchlist -> {r.status_code} OK (count={body['count']})")

# 2. add
r = client.post("/api/v1/watchlist", json={
    "symbol": "600519",
    "name": "贵州茅台",
    "group": "白酒",
    "tags": ["蓝筹"]
})
assert r.status_code == 200
print(f"  POST /watchlist 600519 -> {r.status_code} OK")

# 3. add duplicate (should update)
r = client.post("/api/v1/watchlist", json={
    "symbol": "600519",
    "name": "贵州茅台",
    "group": "白酒龙头"
})
assert r.status_code == 200
print(f"  POST /watchlist 600519 dup -> {r.status_code} OK")

# 4. list with items
r = client.get("/api/v1/watchlist")
assert r.status_code == 200
body = r.json()
assert body["count"] >= 1
print(f"  GET /watchlist -> {r.status_code} OK ({body['count']} items)")

# 5. change group
r = client.put("/api/v1/watchlist/600519/group", json={"group": "核心资产"})
assert r.status_code == 200
print(f"  PUT /watchlist/600519/group -> {r.status_code} OK")

# 6. groups
r = client.get("/api/v1/watchlist/groups")
assert r.status_code == 200
body = r.json()
assert "核心资产" in body["groups"]
print(f"  GET /watchlist/groups -> {r.status_code} OK ({body['groups']})")

# 7. delete non-existent -> 404
r = client.delete("/api/v1/watchlist/999999")
assert r.status_code == 404
print(f"  DELETE /watchlist/999999 -> {r.status_code} OK (edge case)")

# 8. delete
r = client.delete("/api/v1/watchlist/600519")
assert r.status_code == 200
print(f"  DELETE /watchlist/600519 -> {r.status_code} OK")

# 9. import (only 1 item to keep test fast)
r = client.post("/api/v1/watchlist/import", json={
    "items": [
        {"symbol": "000001", "name": "平安银行", "group": "银行"}
    ]
})
assert r.status_code == 200
body = r.json()
assert body["added"] == 1
print(f"  POST /watchlist/import -> {r.status_code} OK ({body['added']} added)")

# 10. export
r = client.get("/api/v1/watchlist/export")
assert r.status_code == 200
body = r.json()
assert "csv" in body and body["count"] >= 1
print(f"  GET /watchlist/export -> {r.status_code} OK ({body['count']} rows)")

# 11. with-quotes (single item, fast)
r = client.get("/api/v1/watchlist/with-quotes")
assert r.status_code == 200
body = r.json()
assert body["count"] >= 1
print(f"  GET /watchlist/with-quotes -> {r.status_code} OK ({body['count']} items)")

# 12. with-indicators (single item, fast)
r = client.get("/api/v1/watchlist/with-indicators")
assert r.status_code == 200
body = r.json()
assert body["count"] >= 1
print(f"  GET /watchlist/with-indicators -> {r.status_code} OK ({body['count']} items)")

# cleanup
for sym in ["000001", "600036"]:
    client.delete(f"/api/v1/watchlist/{sym}")

print("\n=== Stage 1 API Integration ALL PASSED ===")
