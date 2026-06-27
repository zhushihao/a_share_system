# -*- coding: utf-8 -*-
"""
Stage 3 验证脚本 - 测试信号中心与扩展模块
"""
import sys, os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

print("=" * 60)
print("Stage 3 Verification")
print("=" * 60)

errors = []

# --- signals.py API ---
print("\n[TEST] signals.py API")

try:
    r = client.get("/api/v1/signals")
    assert r.status_code == 200, "signals list status=%d" % r.status_code
    data = r.json()
    print("  [OK] GET /api/v1/signals -> 200, %d signals" % len(data.get("items", [])))
except Exception as e:
    errors.append("signals list: %s" % e)
    print("  [FAIL] signals list: %s" % e)

try:
    r = client.get("/api/v1/signals/strategies")
    assert r.status_code == 200, "strategies status=%d" % r.status_code
    data = r.json()
    print("  [OK] GET /api/v1/signals/strategies -> 200, %d strategies" % len(data.get("strategies", [])))
except Exception as e:
    errors.append("signals strategies: %s" % e)
    print("  [FAIL] signals strategies: %s" % e)

try:
    r = client.post("/api/v1/signals/scan", json={
        "symbols": ["000001", "600519"],
        "strategies": ["ma_golden_cross", "bai_da_right_side"],
        "start_date": "20250101",
        "end_date": "20251231"
    })
    assert r.status_code == 200, "scan status=%d, body=%s" % (r.status_code, r.text[:200])
    print("  [OK] POST /api/v1/signals/scan -> 200")
except Exception as e:
    errors.append("signals scan: %s" % e)
    print("  [FAIL] signals scan: %s" % e)

try:
    r = client.get("/api/v1/signals/watchlist-scan?strategies=vol_price_breakout")
    assert r.status_code == 200, "watchlist-scan status=%d, body=%s" % (r.status_code, r.text[:200])
    print("  [OK] GET /api/v1/signals/watchlist-scan -> 200")
except Exception as e:
    errors.append("signals watchlist-scan: %s" % e)
    print("  [FAIL] signals watchlist-scan: %s" % e)

# --- signal_engine.py 独立测试 ---
print("\n[TEST] signal_engine.py")

try:
    from backend.services.signal_engine import SignalEngine, SignalStrategy
    import pandas as pd
    import numpy as np
    
    engine = SignalEngine()
    assert engine is not None
    print("  [OK] SignalEngine instantiated")
    
    # 构造假数据测试信号检测
    np.random.seed(42)
    n = 60
    df = pd.DataFrame({
        "open": np.random.uniform(10, 12, n),
        "high": np.random.uniform(11, 13, n),
        "low": np.random.uniform(9, 11, n),
        "close": np.random.uniform(10, 12, n),
        "volume": np.random.uniform(1000, 5000, n),
    })
    
    # 测试 MA 金叉策略
    signals = engine.detect_daily(df, symbol="TEST", strategies=[SignalStrategy.MA_GOLDEN_CROSS])
    print("  [OK] detect_daily(ma_golden_cross) -> %d signals" % len(signals))
    
    # 测试白大右侧策略
    signals = engine.detect_daily(df, symbol="TEST", strategies=[SignalStrategy.BAI_DA_RIGHT_SIDE])
    print("  [OK] detect_daily(bai_da_right_side) -> %d signals" % len(signals))
    
    # 测试 volume_breakout
    signals = engine.detect_daily(df, symbol="TEST", strategies=[SignalStrategy.VOL_PRICE_BREAKOUT])
    print("  [OK] detect_daily(vol_price_breakout) -> %d signals" % len(signals))
    
except Exception as e:
    errors.append("signal_engine: %s" % e)
    print("  [FAIL] signal_engine: %s" % e)

# --- Frontend 文件检查 ---
print("\n[TEST] Frontend files check")

frontend_files = [
    "frontend_react/src/pages/Signals.tsx",
]

for f in frontend_files:
    path = os.path.join(PROJECT_ROOT, f.replace('/', os.sep))
    path_alt = os.path.join(PROJECT_ROOT, f)
    if os.path.exists(path) or os.path.exists(path_alt):
        size = os.path.getsize(path) if os.path.exists(path) else os.path.getsize(path_alt)
        print("  [OK] %s (%d bytes)" % (f, size))
    else:
        errors.append("frontend missing: %s" % f)
        print("  [FAIL] %s missing" % f)

print("\n" + "=" * 60)
if errors:
    print("FAILED: %d errors" % len(errors))
    for e in errors:
        print("  - %s" % e)
    sys.exit(1)
else:
    print("ALL Stage 3 TESTS PASSED")
    sys.exit(0)
