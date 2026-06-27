# -*- coding: utf-8 -*-
import sys, os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

import pandas as pd
import numpy as np
from backend.services.indicators import calc_ma, calc_kdj, calc_macd, calc_rsi, calc_boll

np.random.seed(42)
dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="B")
df = pd.DataFrame({
    "open": 100 + np.random.randn(100).cumsum(),
    "high": 102 + np.random.randn(100).cumsum(),
    "low": 98 + np.random.randn(100).cumsum(),
    "close": 100 + np.random.randn(100).cumsum(),
    "volume": np.random.randint(1000000, 5000000, 100),
}, index=dates)
df["high"] = df[["open", "close", "high"]].max(axis=1) + 1
df["low"] = df[["open", "close", "low"]].min(axis=1) - 1

print(f"Original df shape: {df.shape}, index len: {len(df.index)}")

try:
    df_ma = calc_ma(df)
    print(f"After calc_ma: {df_ma.shape}")
except Exception as e:
    print(f"calc_ma FAILED: {e}")

try:
    df_kdj = calc_kdj(df)
    print(f"After calc_kdj: {df_kdj.shape}")
except Exception as e:
    print(f"calc_kdj FAILED: {e}")
    import traceback; traceback.print_exc()

try:
    df_macd = calc_macd(df)
    print(f"After calc_macd: {df_macd.shape}")
except Exception as e:
    print(f"calc_macd FAILED: {e}")
    import traceback; traceback.print_exc()

try:
    df_rsi = calc_rsi(df)
    print(f"After calc_rsi: {df_rsi.shape}")
except Exception as e:
    print(f"calc_rsi FAILED: {e}")
    import traceback; traceback.print_exc()

try:
    df_boll = calc_boll(df)
    print(f"After calc_boll: {df_boll.shape}")
except Exception as e:
    print(f"calc_boll FAILED: {e}")
    import traceback; traceback.print_exc()

# Test calculate_all_indicators
try:
    from backend.services.indicators import calculate_all_indicators
    df_all = calculate_all_indicators(df)
    print(f"calculate_all_indicators: {df_all.shape}")
except Exception as e:
    print(f"calculate_all_indicators FAILED: {e}")
    import traceback; traceback.print_exc()
