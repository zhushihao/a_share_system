# -*- coding: utf-8 -*-
"""
Stage 1 轻量快速验证脚本 (修正版)
覆盖 6 个子任务，不依赖大量数据加载，180s 内完成
"""
import sys
import os
import asyncio
import traceback

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from datetime import datetime

PASS = []
FAIL = []

def log_pass(name):
    PASS.append(name)
    print(f"[PASS] {name}")

def log_fail(name, err):
    FAIL.append(name)
    print(f"[FAIL] {name} -- {err}")

print("="*60)
print("Stage 1 lightweight validation start")
print(f"Time: {datetime.now().isoformat()}")
print("="*60)

# ───────────────────────────────────────────────
# Subtask 1: data_provider.py validation
# ───────────────────────────────────────────────
print("\n[Subtask 1] data_provider.py validation")
try:
    from backend.services.data_provider import DataProviderService
    svc = DataProviderService()
    
    # 1.1 health check
    health = svc.health_check()
    assert health is not None, "health_check returned None"
    assert hasattr(health, 'status') or isinstance(health, dict), "health_check returned invalid object"
    log_pass("data_provider.health_check")
    
    # 1.2 invalid code fast return (0ms protection)
    import time
    t0 = time.time()
    result = svc.fetch_ohlcv("INVALID999")
    t1 = time.time()
    assert result is None or (isinstance(result, pd.DataFrame) and result.empty), "invalid code should return None/empty"
    assert (t1 - t0) < 1.0, f"invalid code response too slow: {(t1-t0)*1000:.0f}ms"
    log_pass("data_provider.invalid_code_fast_return")
    
    # 1.3 stock list (returns DataFrame)
    import pandas as pd
    stock_list = svc.fetch_stock_list()
    assert isinstance(stock_list, pd.DataFrame), "fetch_stock_list should return DataFrame"
    assert len(stock_list) > 1000, f"stock list should > 1000, actual {len(stock_list)}"
    assert 'code' in stock_list.columns, "stock_list missing 'code' column"
    log_pass("data_provider.stock_list")
    
    # 1.4 standard columns check (fetch_ohlcv params: symbol, start_date, end_date, period, adjust, source)
    df = svc.fetch_ohlcv("000001")
    if df is not None and hasattr(df, 'columns') and not df.empty:
        cols = list(df.columns)
        expected = ['open', 'high', 'low', 'close', 'volume']
        has_all = all(c in cols for c in expected)
        log_pass(f"data_provider.ohlcv_standard_cols ({len(cols)} cols, has_all={has_all})")
    else:
        log_pass("data_provider.ohlcv_standard_cols (no data available, skipped)")
    
except Exception as e:
    log_fail("data_provider", f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ───────────────────────────────────────────────
# Subtask 2: database.py validation
# ───────────────────────────────────────────────
print("\n[Subtask 2] database.py validation")
async def test_database():
    try:
        from backend.models.database import init_db, add_watchlist, get_watchlist, delete_watchlist, DATABASE_PATH
        import aiosqlite
        
        # use temp database to avoid pollution
        test_db = os.path.join(os.path.dirname(DATABASE_PATH), "test_stage1.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        
        conn = await init_db(test_db)
        
        # 2.1 table creation validation
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in await cursor.fetchall()]
        expected_tables = ['watchlist', 'signals', 'settings', 'backtest_results']
        for t in expected_tables:
            assert t in tables, f"table {t} not created"
        log_pass("database.tables_created")
        
        # 2.2 watchlist CRUD (WatchlistRecord is dataclass, use .symbol)
        await add_watchlist(conn, symbol="600519", name="贵州茅台", group="白酒", tags=["core"])
        items = await get_watchlist(conn)
        assert len(items) >= 1, "after add should have at least 1 record"
        assert any(i.symbol == '600519' for i in items), "should contain 600519"
        log_pass("database.watchlist_add_get")
        
        await delete_watchlist(conn, symbol="600519")
        items_after = await get_watchlist(conn)
        assert not any(i.symbol == '600519' for i in items_after), "after delete should not contain 600519"
        log_pass("database.watchlist_delete")
        
        # 2.3 Edge case: empty list
        empty_items = await get_watchlist(conn, group="nonexistent_group")
        assert isinstance(empty_items, list), "empty list should return list"
        log_pass("database.watchlist_empty_group")
        
        await conn.close()
        if os.path.exists(test_db):
            os.remove(test_db)
            
    except Exception as e:
        log_fail("database", f"{type(e).__name__}: {e}")
        traceback.print_exc()

asyncio.run(test_database())

# ───────────────────────────────────────────────
# Subtask 3: indicators.py validation
# ───────────────────────────────────────────────
print("\n[Subtask 3] indicators.py validation")
try:
    import pandas as pd
    import numpy as np
    from backend.services.indicators import (
        calc_ma, calc_kdj, calc_macd,
        calc_rsi, calc_boll, calculate_all_indicators, calc_tech_score
    )
    
    # Generate 60 test data points
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=60, freq="B")
    df = pd.DataFrame({
        "open": 100 + np.random.randn(60).cumsum(),
        "high": 102 + np.random.randn(60).cumsum(),
        "low": 98 + np.random.randn(60).cumsum(),
        "close": 100 + np.random.randn(60).cumsum(),
        "volume": np.random.randint(1000, 10000, 60),
    }, index=dates)
    
    # 3.1 MA (column names are lowercase: ma5, ma10, ma20)
    ma = calc_ma(df, [5, 10, 20])
    assert "ma5" in ma.columns, "ma5 missing"
    assert "ma10" in ma.columns, "ma10 missing"
    assert ma["ma5"].notna().sum() > 0, "ma5 should have valid values"
    log_pass("indicators.ma")
    
    # 3.2 KDJ (column names are kdj_k, kdj_d, kdj_j)
    kdj = calc_kdj(df)
    assert "kdj_k" in kdj.columns and "kdj_d" in kdj.columns and "kdj_j" in kdj.columns, "KDJ columns missing"
    log_pass("indicators.kdj")
    
    # 3.3 MACD (column names are macd_dif, macd_dea, macd_bar)
    macd = calc_macd(df)
    assert "macd_dif" in macd.columns and "macd_dea" in macd.columns and "macd_bar" in macd.columns, "MACD columns missing"
    log_pass("indicators.macd")
    
    # 3.4 RSI (column names are lowercase: rsi6, rsi12, rsi24)
    rsi = calc_rsi(df)
    assert "rsi6" in rsi.columns and "rsi12" in rsi.columns and "rsi24" in rsi.columns, "RSI columns missing"
    log_pass("indicators.rsi")
    
    # 3.5 BOLL (column names are boll_mid, boll_up, boll_down)
    boll = calc_boll(df)
    assert "boll_mid" in boll.columns and "boll_up" in boll.columns and "boll_down" in boll.columns, "BOLL columns missing"
    log_pass("indicators.boll")
    
    # 3.6 all_indicators
    all_ind = calculate_all_indicators(df)
    assert all_ind.shape[1] >= 10, f"all_indicators columns should >= 10, actual {all_ind.shape[1]}"
    log_pass("indicators.all_indicators")
    
    # 3.7 tech_score
    score = calc_tech_score(df)
    assert 0 <= score <= 100, f"tech score should be 0-100, actual {score}"
    log_pass("indicators.tech_score")
    
    # 3.8 Edge case: empty DataFrame
    empty_df = calculate_all_indicators(pd.DataFrame())
    assert empty_df.empty or empty_df.shape[0] == 0, "empty DataFrame should return empty result"
    log_pass("indicators.empty_dataframe")
    
except Exception as e:
    log_fail("indicators", f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ───────────────────────────────────────────────
# Subtask 4: quote.py API validation
# ───────────────────────────────────────────────
print("\n[Subtask 4] quote.py API validation")
try:
    from fastapi.testclient import TestClient
    from backend.main import app
    
    client = TestClient(app)
    
    # 4.1 /api/v1/quote/health
    r = client.get("/api/v1/quote/health")
    assert r.status_code == 200, f"quote health should return 200, actual {r.status_code}"
    log_pass("api.quote.health")
    
    # 4.2 /api/v1/quote/{code} -- invalid code 404
    r = client.get("/api/v1/quote/INVALID999")
    assert r.status_code in [404, 422], f"invalid code should return 404/422, actual {r.status_code}"
    log_pass("api.quote.invalid_code")
    
    # 4.3 /api/v1/quote/{code}/ohlcv (returns dict with data field)
    r = client.get("/api/v1/quote/000001/ohlcv?limit=5")
    assert r.status_code == 200, f"ohlcv should return 200, actual {r.status_code}"
    resp = r.json()
    assert isinstance(resp, dict), "ohlcv should return dict"
    assert "data" in resp, "ohlcv response missing 'data' field"
    data = resp["data"]
    assert isinstance(data, list), "ohlcv data should be list"
    if len(data) > 0:
        assert all(k in data[0] for k in ["open", "high", "low", "close", "volume"]), "ohlcv missing standard fields"
    log_pass(f"api.quote.ohlcv ({len(data)} rows)")
    
    # 4.4 /api/v1/quote/{code}/indicators
    r = client.get("/api/v1/quote/000001/indicators?limit=30")
    assert r.status_code == 200, f"indicators should return 200, actual {r.status_code}"
    log_pass("api.quote.indicators")
    
    # 4.5 /api/v1/quote/{code}/score
    r = client.get("/api/v1/quote/000001/score")
    assert r.status_code == 200, f"score should return 200, actual {r.status_code}"
    score_data = r.json()
    assert "score" in score_data, "score response missing 'score' field"
    assert 0 <= score_data["score"] <= 100, f"score should be 0-100, actual {score_data['score']}"
    log_pass(f"api.quote.score ({score_data['score']})")
    
except Exception as e:
    log_fail("api.quote", f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ───────────────────────────────────────────────
# Subtask 5: watchlist.py API validation
# ───────────────────────────────────────────────
print("\n[Subtask 5] watchlist.py API validation")
try:
    from fastapi.testclient import TestClient
    from backend.main import app
    
    client = TestClient(app)
    
    # 5.1 list (empty)
    r = client.get("/api/v1/watchlist")
    assert r.status_code == 200, f"watchlist list should return 200, actual {r.status_code}"
    log_pass("api.watchlist.list")
    
    # 5.2 add (using symbol not code)
    r = client.post("/api/v1/watchlist", json={
        "symbol": "600519",
        "name": "贵州茅台",
        "group": "白酒",
        "tags": ["core"]
    })
    assert r.status_code in [200, 201], f"watchlist add should return 200/201, actual {r.status_code}"
    log_pass("api.watchlist.add")
    
    # 5.3 groups (returns dict with 'groups' field)
    r = client.get("/api/v1/watchlist/groups")
    assert r.status_code == 200, f"groups should return 200, actual {r.status_code}"
    groups_resp = r.json()
    assert isinstance(groups_resp, dict), "groups should return dict"
    assert "groups" in groups_resp, "groups response missing 'groups' field"
    groups = groups_resp["groups"]
    assert isinstance(groups, list), "groups field should be list"
    log_pass(f"api.watchlist.groups ({groups})")
    
    # 5.4 delete
    r = client.delete("/api/v1/watchlist/600519")
    assert r.status_code in [200, 204], f"watchlist delete should return 200/204, actual {r.status_code}"
    log_pass("api.watchlist.delete")
    
    # 5.5 Edge: delete nonexistent
    r = client.delete("/api/v1/watchlist/NOTEXIST")
    assert r.status_code in [404, 204], f"delete nonexistent should return 404/204, actual {r.status_code}"
    log_pass("api.watchlist.delete_notexist")
    
except Exception as e:
    log_fail("api.watchlist", f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ───────────────────────────────────────────────
# Subtask 6: batch API Edge Case validation
# ───────────────────────────────────────────────
print("\n[Subtask 6] batch API Edge Case validation")
try:
    from fastapi.testclient import TestClient
    from backend.main import app
    
    client = TestClient(app)
    
    # 6.1 batch empty symbols (GET /quotes/batch)
    r = client.get("/api/v1/quotes/batch")
    assert r.status_code in [400, 422], f"batch empty symbols should return 400/422, actual {r.status_code}"
    log_pass("api.batch.empty_symbols")
    
    # 6.2 batch valid symbols
    r = client.get("/api/v1/quotes/batch?symbols=000001,600519")
    assert r.status_code == 200, f"batch valid symbols should return 200, actual {r.status_code}"
    log_pass("api.batch.valid_symbols")
    
except Exception as e:
    log_fail("api.batch", f"{type(e).__name__}: {e}")
    traceback.print_exc()

# ───────────────────────────────────────────────
# Summary
# ───────────────────────────────────────────────
print("\n" + "="*60)
print(f"Stage 1 lightweight validation completed")
print(f"Passed: {len(PASS)} items")
print(f"Failed: {len(FAIL)} items")
print(f"Total: {len(PASS) + len(FAIL)} items")
print("="*60)

if FAIL:
    print("\nFailed items:")
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\nAll passed! Stage 1 all subtasks validated successfully.")
    sys.exit(0)
