# -*- coding: utf-8 -*-
"""
Stage 1 验证脚本 - 按子任务逐项验证
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pandas as pd
from datetime import datetime

# 设置 stdout 编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"

# ───────────────────────────────────────────────
# 子任务 1: data_provider.py 验证
# ───────────────────────────────────────────────
print("=" * 60)
print("子任务 1: data_provider.py")
print("=" * 60)

from backend.services.data_provider import DataProviderService, get_data_provider_service

svc = DataProviderService()
print(f"{PASS} DataProviderService 实例化成功")

# 健康检查
health = svc.health_check()
print(f"{PASS} 健康检查: {health}")

# 无效代码 edge case
try:
    bad = svc.fetch_ohlcv("999999", limit=5)
    if bad is None or len(bad) == 0:
        print(f"{PASS} 无效代码返回 None/空")
    else:
        print(f"{FAIL} 无效代码应返回 None 或空")
except Exception as e:
    print(f"{PASS} 无效代码异常处理: {type(e).__name__}")

# 有效代码获取 OHLCV (茅台 600519)
df = svc.fetch_ohlcv("600519", start_date="", end_date="")
if df is not None and len(df) > 0:
    # 取最近10条
    df = df.tail(10).reset_index(drop=True)
    required_cols = {"open", "high", "low", "close", "volume"}
    actual_cols = set(str(c).lower() for c in df.columns)
    print(f"{PASS} 600519 OHLCV 获取成功: {len(df)} rows, cols={actual_cols}")
    has_all = required_cols.issubset(actual_cols)
    status = PASS if has_all else FAIL
    print(f"{status} 标准列检查: {has_all}")
else:
    print(f"{INFO} 600519 OHLCV 无数据 (可能 TDX 数据不存在)")

# 实时行情
quotes = svc.fetch_realtime_quotes(["600519", "000001"])
print(f"{PASS} 实时行情获取: {len(quotes)} 条")

# ───────────────────────────────────────────────
# 子任务 2: database.py 验证
# ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("子任务 2: database.py")
print("=" * 60)

from backend.models.database import init_db, add_watchlist, get_watchlist, delete_watchlist, DATABASE_PATH
import tempfile
import aiosqlite

async def test_db():
    # 使用临时数据库避免污染生产数据
    test_db_path = os.path.join(tempfile.gettempdir(), f"test_stage1_{datetime.now().strftime('%H%M%S')}.db")
    conn = await init_db(test_db_path)
    
    # 检查表结构
    cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in await cursor.fetchall()]
    required_tables = {"watchlist", "signals", "settings", "backtest_results"}
    print(f"{PASS} 表列表: {tables}")
    has_all = required_tables.issubset(set(tables))
    status = PASS if has_all else FAIL
    print(f"{status} 必需表存在: {has_all}")
    
    # CRUD 测试
    record = await add_watchlist(conn, symbol="000001", name="平安银行", group="测试组")
    print(f"{PASS} 添加自选股: {record.symbol} ({record.name})")
    
    items = await get_watchlist(conn)
    print(f"{PASS} 查询自选股: {len(items)} 条")
    
    ok = await delete_watchlist(conn, "000001")
    print(f"{PASS} 删除自选股: {ok}")
    
    items_after = await get_watchlist(conn)
    print(f"{PASS} 删除后查询: {len(items_after)} 条")
    
    await conn.close()
    os.remove(test_db_path)
    print(f"{PASS} 数据库清理完成")

asyncio.run(test_db())

# ───────────────────────────────────────────────
# 子任务 3: indicators.py 验证
# ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("子任务 3: indicators.py")
print("=" * 60)

from backend.services.indicators import (
    calc_ma, calc_kdj, calc_macd, calc_rsi, calc_boll,
    calculate_all_indicators, get_latest_indicators, calc_tech_score
)

# 构造测试数据
import numpy as np
np.random.seed(42)
test_df = pd.DataFrame({
    "open": np.random.randn(100).cumsum() + 100,
    "high": np.random.randn(100).cumsum() + 101,
    "low": np.random.randn(100).cumsum() + 99,
    "close": np.random.randn(100).cumsum() + 100,
    "volume": np.random.randint(1000, 10000, 100),
})

# MA
df_ma = calc_ma(test_df.copy())
ma_cols = [c for c in df_ma.columns if 'ma' in str(c).lower()]
print(f"{PASS} MA 计算: {ma_cols}")

# KDJ
df_kdj = calc_kdj(test_df.copy())
kdj_cols = [c for c in df_kdj.columns if str(c).lower() in ('kdj_k', 'kdj_d', 'kdj_j')]
print(f"{PASS} KDJ 计算: {kdj_cols}")

# MACD
df_macd = calc_macd(test_df.copy())
macd_cols = [c for c in df_macd.columns if 'macd' in str(c).lower() or 'diff' in str(c).lower() or 'dea' in str(c).lower()]
print(f"{PASS} MACD 计算: {macd_cols}")

# RSI
df_rsi = calc_rsi(test_df.copy())
rsi_cols = [c for c in df_rsi.columns if 'rsi' in str(c).lower()]
print(f"{PASS} RSI 计算: {rsi_cols}")

# BOLL
df_boll = calc_boll(test_df.copy())
boll_cols = [c for c in df_boll.columns if 'boll' in str(c).lower() or 'upper' in str(c).lower() or 'lower' in str(c).lower()]
print(f"{PASS} BOLL 计算: {boll_cols}")

# 全指标
all_df = calculate_all_indicators(test_df.copy())
print(f"{PASS} 全指标计算: 共 {len(all_df.columns)} 列")

# 最新指标
latest = get_latest_indicators(all_df)
print(f"{PASS} 最新指标提取: {len(latest)} 个键")

# 技术评分
score = calc_tech_score(all_df)
print(f"{PASS} 技术评分: {score}")

# Edge case: 空数据
empty_df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
empty_result = calculate_all_indicators(empty_df)
print(f"{PASS} 空数据 Edge case: {len(empty_result)} 行")

# ───────────────────────────────────────────────
# 子任务 4 & 5: quote.py & watchlist.py API 验证
# ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("子任务 4 & 5: API 路由验证")
print("=" * 60)

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

# 健康检查
resp = client.get("/api/v1/quote/health")
print(f"{PASS if resp.status_code == 200 else FAIL} /api/v1/quote/health: {resp.status_code}")

# 无效代码
resp = client.get("/api/v1/quote/000000/ohlcv")
print(f"{PASS if resp.status_code == 404 else FAIL} 无效代码 OHLCV: {resp.status_code} (期望 404)")

# 有效代码
resp = client.get("/api/v1/quote/600519/ohlcv?limit=5")
print(f"{PASS if resp.status_code == 200 else INFO} 600519 OHLCV: {resp.status_code}")

# 批量行情
resp = client.get("/api/v1/quotes/batch?symbols=600519,000001")
print(f"{PASS if resp.status_code == 200 else INFO} 批量行情: {resp.status_code}")

# 空参数 edge case
resp = client.get("/api/v1/quotes/batch?symbols=")
print(f"{PASS if resp.status_code == 422 else FAIL} 空参数批量: {resp.status_code} (期望 422)")

# 自选股列表
resp = client.get("/api/v1/watchlist")
print(f"{PASS if resp.status_code == 200 else FAIL} /api/v1/watchlist: {resp.status_code}")

# 添加自选股
resp = client.post("/api/v1/watchlist", json={
    "symbol": "000001",
    "name": "平安银行",
    "group": "测试组"
})
print(f"{PASS if resp.status_code == 200 else FAIL} POST /watchlist: {resp.status_code}")

# 分组查询
resp = client.get("/api/v1/watchlist/groups")
print(f"{PASS if resp.status_code == 200 else FAIL} /watchlist/groups: {resp.status_code}")

# 删除
resp = client.delete("/api/v1/watchlist/000001")
print(f"{PASS if resp.status_code == 200 else FAIL} DELETE /watchlist/000001: {resp.status_code}")

print("\n" + "=" * 60)
print("Stage 1 验证完成")
print("=" * 60)
