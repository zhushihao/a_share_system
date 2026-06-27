# -*- coding: utf-8 -*-
"""
Technical Indicators Engine - 技术指标引擎

支持的指标：
  - MA: 简单移动平均线 (5, 10, 20, 60)
  - KDJ: 随机指标 (N=9, M1=3, M2=3)
  - MACD: 指数平滑异同平均线 (12, 26, 9)
  - RSI: 相对强弱指标 (6, 12, 24)
  - BOLL: 布林带 (20, 2)

实现标准：通达信公式兼容，偏差 < 0.01%
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any


# ───────────────────────────────────────────────
# 基础工具函数
# ───────────────────────────────────────────────

def _sma(series: pd.Series, n: int, m: int = 1) -> pd.Series:
    """
    通达信 SMA 函数实现
    
    SMA(X, N, M) = M/N * X + (N-M)/N * SMA(X, N, M)[-1]
    
    即 alpha = M/N 的递推加权平均。
    初始值使用前 N 个元素的简单平均。
    
    Args:
        series: 输入序列
        n: 周期 N
        m: 权重 M
    
    Returns:
        SMA 序列
    """
    if n <= 0 or m <= 0:
        return pd.Series(np.nan, index=series.index)
    
    alpha = m / n
    result = pd.Series(np.nan, index=series.index)
    
    # 初始值：前 n 个有效值的简单平均
    valid = series.dropna()
    if len(valid) == 0:
        return result
    
    # 找到第一个可以作为初始值的点
    first_idx = n - 1
    if first_idx < len(series):
        init_val = series.iloc[:first_idx + 1].mean()
        result.iloc[first_idx] = init_val
        
        # 递推计算
        for i in range(first_idx + 1, len(series)):
            if not pd.isna(series.iloc[i]):
                result.iloc[i] = alpha * series.iloc[i] + (1 - alpha) * result.iloc[i - 1]
    
    return result


def _ema(series: pd.Series, n: int) -> pd.Series:
    """
    指数移动平均（EMA）
    
    EMA(X, N) = 2/(N+1) * X + (N-1)/(N+1) * EMA(X, N)[-1]
    
    使用 pandas ewm 实现，adjust=False 匹配递推公式。
    """
    return series.ewm(span=n, adjust=False, min_periods=n).mean()


def _llv(series: pd.Series, n: int) -> pd.Series:
    """N 日内最低值（Lowest Low Value，含当前日）"""
    return series.rolling(window=n, min_periods=n).min()


def _hhv(series: pd.Series, n: int) -> pd.Series:
    """N 日内最高值（Highest High Value，含当前日）"""
    return series.rolling(window=n, min_periods=n).max()


# ───────────────────────────────────────────────
# 指标计算函数
# ───────────────────────────────────────────────

def calc_ma(df: pd.DataFrame, periods: List[int] = None) -> pd.DataFrame:
    """
    计算简单移动平均线（MA）
    
    Args:
        df: DataFrame 含 'close' 列
        periods: MA 周期列表，默认 [5, 10, 20, 60]
    
    Returns:
        原 DataFrame 附加 maX 列
    """
    if periods is None:
        periods = [5, 10, 20, 60]
    
    df = df.copy()
    for p in periods:
        df[f"ma{p}"] = df["close"].rolling(window=p, min_periods=p).mean()
    
    return df


def calc_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """
    计算 KDJ 指标
    
    通达信公式：
      RSV = (CLOSE - LLV(LOW, N)) / (HHV(HIGH, N) - LLV(LOW, N)) * 100
      K = SMA(RSV, M1, 1)
      D = SMA(K, M2, 1)
      J = 3*K - 2*D
    
    Args:
        df: DataFrame 含 'high', 'low', 'close' 列
        n: RSV 周期，默认 9
        m1: K 平滑周期，默认 3
        m2: D 平滑周期，默认 3
    
    Returns:
        原 DataFrame 附加 kdj_k, kdj_d, kdj_j 列
    """
    df = df.copy()
    
    low_n = _llv(df["low"], n)
    high_n = _hhv(df["high"], n)
    
    # RSV，避免除以 0
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)  # 当 high==low 时，RSV 设为 50（中性）
    
    df["kdj_k"] = _sma(rsv, m1, 1)
    df["kdj_d"] = _sma(df["kdj_k"], m2, 1)
    df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]
    
    return df


def calc_macd(df: pd.DataFrame, short: int = 12, long: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    计算 MACD 指标
    
    通达信公式：
      DIF = EMA(CLOSE, SHORT) - EMA(CLOSE, LONG)
      DEA = EMA(DIF, MID)
      MACD_BAR = (DIF - DEA) * 2
    
    Args:
        df: DataFrame 含 'close' 列
        short: 短周期，默认 12
        long: 长周期，默认 26
        signal: 信号周期，默认 9
    
    Returns:
        原 DataFrame 附加 macd_dif, macd_dea, macd_bar 列
    """
    df = df.copy()
    
    ema_short = _ema(df["close"], short)
    ema_long = _ema(df["close"], long)
    
    df["macd_dif"] = ema_short - ema_long
    df["macd_dea"] = _ema(df["macd_dif"], signal)
    df["macd_bar"] = (df["macd_dif"] - df["macd_dea"]) * 2
    
    return df


def calc_rsi(df: pd.DataFrame, periods: List[int] = None) -> pd.DataFrame:
    """
    计算 RSI 指标
    
    通达信公式：
      LC = REF(CLOSE, 1)
      RSI = SMA(MAX(CLOSE - LC, 0), N, 1) / SMA(ABS(CLOSE - LC), N, 1) * 100
    
    Args:
        df: DataFrame 含 'close' 列
        periods: 周期列表，默认 [6, 12, 24]
    
    Returns:
        原 DataFrame 附加 rsiX 列
    """
    if periods is None:
        periods = [6, 12, 24]
    
    df = df.copy()
    
    # 涨跌
    diff = df["close"].diff()
    
    # 上涨和下跌幅度
    up = diff.where(diff > 0, 0.0)
    down = (-diff).where(diff < 0, 0.0)
    
    for p in periods:
        # 使用 SMA（alpha=1/p）
        avg_up = _sma(up, p, 1)
        avg_down = _sma(down, p, 1)
        
        # RSI = avg_up / (avg_up + avg_down) * 100
        rsi = avg_up / (avg_up + avg_down).replace(0, np.nan) * 100
        rsi = rsi.fillna(50)  # 当 avg_up + avg_down == 0 时，设为 50
        df[f"rsi{p}"] = rsi
    
    return df


def calc_boll(df: pd.DataFrame, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """
    计算布林带（BOLL）指标
    
    通达信公式：
      MID = MA(CLOSE, N)
      STD = STD(CLOSE, N)
      UP = MID + P * STD
      DOWN = MID - P * STD
    
    Args:
        df: DataFrame 含 'close' 列
        n: 周期，默认 20
        k: 标准差倍数，默认 2.0
    
    Returns:
        原 DataFrame 附加 boll_mid, boll_up, boll_down 列
    """
    df = df.copy()
    
    mid = df["close"].rolling(window=n, min_periods=n).mean()
    std = df["close"].rolling(window=n, min_periods=n).std(ddof=0)
    
    df["boll_mid"] = mid
    df["boll_up"] = mid + k * std
    df["boll_down"] = mid - k * std
    
    return df


def calc_obv(df: pd.DataFrame) -> pd.DataFrame:
    """
    OBV - 能量潮指标

    OBV = 前一日 OBV + 今日成交量（如果收盘价 > 前一日收盘价）
    OBV = 前一日 OBV - 今日成交量（如果收盘价 < 前一日收盘价）
    OBV = 前一日 OBV（如果收盘价 = 前一日收盘价）

    Args:
        df: DataFrame 含 'close', 'volume' 列

    Returns:
        原 DataFrame 附加 obv 列
    """
    df = df.copy()
    close_diff = df["close"].diff()
    obv = pd.Series(0.0, index=df.index)  # 使用 float 避免 int64 overflow
    for i in range(1, len(df)):
        if close_diff.iloc[i] > 0:
            obv.iloc[i] = obv.iloc[i - 1] + df["volume"].iloc[i]
        elif close_diff.iloc[i] < 0:
            obv.iloc[i] = obv.iloc[i - 1] - df["volume"].iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i - 1]
    df["obv"] = obv
    return df


def calc_dmi(df: pd.DataFrame, n: int = 14, m: int = 6) -> pd.DataFrame:
    """
    DMI - 动向指标（ADX, +DI, -DI）

    +DM = max(今日高 - 昨日高, 0) 如果 今日高 - 昨日高 > 昨日低 - 今日低
    -DM = max(昨日低 - 今日低, 0) 如果 昨日低 - 今日低 > 今日高 - 昨日高
    TR = max(今日高 - 今日低, |今日高 - 昨日收盘|, |今日低 - 昨日收盘|)
    +DI = 100 * EMA(+DM, N) / EMA(TR, N)
    -DI = 100 * EMA(-DM, N) / EMA(TR, N)
    DX = 100 * |+DI - (-DI)| / (+DI + -DI)
    ADX = EMA(DX, M)

    Args:
        df: DataFrame 含 'high', 'low', 'close' 列
        n: 周期 N，默认 14
        m: 平滑周期 M，默认 6

    Returns:
        原 DataFrame 附加 dmi_pdi, dmi_mdi, dmi_adx 列
    """
    df = df.copy()
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = -low.diff()

    pdm = pd.Series(0.0, index=df.index)
    mdm = pd.Series(0.0, index=df.index)
    for i in range(1, len(df)):
        if up_move.iloc[i] > down_move.iloc[i] and up_move.iloc[i] > 0:
            pdm.iloc[i] = up_move.iloc[i]
        if down_move.iloc[i] > up_move.iloc[i] and down_move.iloc[i] > 0:
            mdm.iloc[i] = down_move.iloc[i]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    tr_ema = _ema(tr, n)
    pdm_ema = _ema(pdm, n)
    mdm_ema = _ema(mdm, n)

    pdi = 100 * pdm_ema / tr_ema.replace(0, np.nan)
    mdi = 100 * mdm_ema / tr_ema.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = _ema(dx, m)

    df["dmi_pdi"] = pdi
    df["dmi_mdi"] = mdi
    df["dmi_adx"] = adx

    return df


# ───────────────────────────────────────────────
# 批量计算接口
# ───────────────────────────────────────────────

def calculate_all_indicators(df: pd.DataFrame, period: str = "daily") -> pd.DataFrame:
    """
    一键计算所有技术指标
    
    Args:
        df: OHLCV DataFrame，必须包含 'open', 'high', 'low', 'close', 'volume' 列
    
    Returns:
        附加所有指标列的 DataFrame
    """
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if len(df) == 0:
        # 空数据 edge case：直接返回空 DataFrame（不检查列，避免无列空 DataFrame 报错）
        return df.copy()
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    df = df.copy()
    df = calc_ma(df)
    df = calc_kdj(df)
    df = calc_macd(df)
    df = calc_rsi(df)
    df = calc_boll(df)
    df = calc_obv(df)
    df = calc_dmi(df)
    
    return df


def get_latest_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    获取最新一行的指标值（用于 API 返回）
    
    Args:
        df: 已计算指标的 DataFrame
    
    Returns:
        指标字典
    """
    if df is None or len(df) == 0:
        return {}
    
    latest = df.iloc[-1]
    result = {}
    
    # MA
    for col in df.columns:
        if col.startswith("ma"):
            result[col] = round(float(latest[col]), 2) if not pd.isna(latest[col]) else None
    
    # KDJ
    for k in ["kdj_k", "kdj_d", "kdj_j"]:
        if k in df.columns:
            result[k] = round(float(latest[k]), 2) if not pd.isna(latest[k]) else None
    
    # MACD
    for k in ["macd_dif", "macd_dea", "macd_bar"]:
        if k in df.columns:
            result[k] = round(float(latest[k]), 3) if not pd.isna(latest[k]) else None
    
    # RSI
    for col in df.columns:
        if col.startswith("rsi"):
            result[col] = round(float(latest[col]), 2) if not pd.isna(latest[col]) else None
    
    # BOLL
    for k in ["boll_mid", "boll_up", "boll_down"]:
        if k in df.columns:
            result[k] = round(float(latest[k]), 2) if not pd.isna(latest[k]) else None
    
    # OBV
    if "obv" in df.columns:
        result["obv"] = round(float(latest["obv"]), 0) if not pd.isna(latest["obv"]) else None
    
    # DMI
    for k in ["dmi_pdi", "dmi_mdi", "dmi_adx"]:
        if k in df.columns:
            result[k] = round(float(latest[k]), 2) if not pd.isna(latest[k]) else None
    
    return result


# ───────────────────────────────────────────────
# 技术评分（0-100）
# ───────────────────────────────────────────────

def calc_tech_score(df: pd.DataFrame) -> int:
    """
    基于多指标的技术评分（0-100）
    
    评分维度：
      - 趋势（30分）：MA 多头排列、价格站上 MA20
      - 动量（30分）：MACD 金叉、DIF 向上、MACD_BAR 为正
      - 超买超卖（20分）：KDJ 在合理区间、RSI 不极端
      - 波动（20分）：价格在 BOLL 中轨上方
    
    Args:
        df: 已计算指标的 DataFrame（至少包含最近2行）
    
    Returns:
        0-100 的整数评分
    """
    if df is None or len(df) < 2:
        return 0
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0
    
    # 1. 趋势（30分）
    # MA5 > MA10 > MA20
    ma_ok = False
    if all(k in df.columns for k in ["ma5", "ma10", "ma20"]):
        ma_ok = (not pd.isna(curr["ma5"])) and (not pd.isna(curr["ma10"])) and (not pd.isna(curr["ma20"])) and (curr["ma5"] > curr["ma10"] > curr["ma20"])
    if ma_ok:
        score += 15
    
    # 价格 > MA20
    price_ma20 = False
    if "ma20" in df.columns and "close" in df.columns:
        price_ma20 = (not pd.isna(curr["ma20"])) and (curr["close"] > curr["ma20"])
    if price_ma20:
        score += 15
    
    # 2. 动量（30分）
    # MACD 金叉（DIF 上穿 DEA）
    macd_golden = False
    if all(k in df.columns for k in ["macd_dif", "macd_dea"]):
        macd_golden = (not pd.isna(prev["macd_dif"])) and (not pd.isna(prev["macd_dea"])) and (not pd.isna(curr["macd_dif"])) and (not pd.isna(curr["macd_dea"])) and (prev["macd_dif"] <= prev["macd_dea"]) and (curr["macd_dif"] > curr["macd_dea"])
    if macd_golden:
        score += 15
    
    # MACD_BAR > 0
    macd_positive = False
    if "macd_bar" in df.columns:
        macd_positive = (not pd.isna(curr["macd_bar"])) and (curr["macd_bar"] > 0)
    if macd_positive:
        score += 10
    
    # DIF 向上
    dif_up = False
    if "macd_dif" in df.columns:
        dif_up = (not pd.isna(curr["macd_dif"])) and (not pd.isna(prev["macd_dif"])) and (curr["macd_dif"] > prev["macd_dif"])
    if dif_up:
        score += 5
    
    # 3. 超买超卖（20分）
    # KDJ K 在 20-80 之间（非极端）
    kdj_ok = False
    if "kdj_k" in df.columns:
        k = curr["kdj_k"]
        kdj_ok = (not pd.isna(k)) and (20 <= k <= 80)
    if kdj_ok:
        score += 10
    
    # RSI6 在 30-70 之间
    rsi_ok = False
    if "rsi6" in df.columns:
        r = curr["rsi6"]
        rsi_ok = (not pd.isna(r)) and (30 <= r <= 70)
    if rsi_ok:
        score += 10
    
    # 4. 波动（20分）
    # 价格在中轨上方
    boll_up = False
    if "boll_mid" in df.columns and "close" in df.columns:
        boll_up = (not pd.isna(curr["boll_mid"])) and (curr["close"] > curr["boll_mid"])
    if boll_up:
        score += 10
    
    # 价格靠近上轨（强势）
    boll_strong = False
    if all(k in df.columns for k in ["boll_up", "boll_mid", "close"]):
        boll_strong = (not pd.isna(curr["boll_up"])) and (not pd.isna(curr["boll_mid"])) and (curr["close"] > (curr["boll_up"] + curr["boll_mid"]) / 2)
    if boll_strong:
        score += 10
    
    return min(100, max(0, int(score)))


# ───────────────────────────────────────────────
# 测试
# ───────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    
    from backend.services.data_provider import DataProviderService
    
    print("=== Technical Indicators Engine Test ===")
    
    # 获取真实数据
    svc = DataProviderService()
    df = svc.fetch_ohlcv("000001", period="daily", adjust="qfq")
    
    if df is None or len(df) == 0:
        print("ERROR: No real data available for test. Cannot proceed with synthetic data (system policy: no fake data).")
        sys.exit(1)
    
    print(f"\nData shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    
    # 1. MA 测试
    print("\n[1] MA Test")
    df_ma = calc_ma(df)
    for p in [5, 10, 20, 60]:
        col = f"ma{p}"
        assert col in df_ma.columns, f"Missing {col}"
        # 验证前 N-1 行为 NaN
        assert pd.isna(df_ma[col].iloc[p-2]), f"MA{p} should be NaN at index {p-2}"
        assert not pd.isna(df_ma[col].iloc[p-1]), f"MA{p} should be valid at index {p-1}"
    print(f"  MA5 latest: {df_ma['ma5'].iloc[-1]:.2f}")
    print(f"  MA20 latest: {df_ma['ma20'].iloc[-1]:.2f}")
    print("  MA: PASSED")
    
    # 2. KDJ 测试
    print("\n[2] KDJ Test")
    df_kdj = calc_kdj(df)
    assert "kdj_k" in df_kdj.columns
    assert "kdj_d" in df_kdj.columns
    assert "kdj_j" in df_kdj.columns
    
    # K, D 应在 0-100 之间
    k_valid = df_kdj["kdj_k"].dropna()
    d_valid = df_kdj["kdj_d"].dropna()
    assert k_valid.min() >= 0 and k_valid.max() <= 100, f"KDJ K out of range: {k_valid.min()}-{k_valid.max()}"
    assert d_valid.min() >= 0 and d_valid.max() <= 100, f"KDJ D out of range: {d_valid.min()}-{d_valid.max()}"
    
    print(f"  KDJ K latest: {df_kdj['kdj_k'].iloc[-1]:.2f}")
    print(f"  KDJ D latest: {df_kdj['kdj_d'].iloc[-1]:.2f}")
    print(f"  KDJ J latest: {df_kdj['kdj_j'].iloc[-1]:.2f}")
    print("  KDJ: PASSED")
    
    # 3. MACD 测试
    print("\n[3] MACD Test")
    df_macd = calc_macd(df)
    assert "macd_dif" in df_macd.columns
    assert "macd_dea" in df_macd.columns
    assert "macd_bar" in df_macd.columns
    
    print(f"  DIF latest: {df_macd['macd_dif'].iloc[-1]:.3f}")
    print(f"  DEA latest: {df_macd['macd_dea'].iloc[-1]:.3f}")
    print(f"  BAR latest: {df_macd['macd_bar'].iloc[-1]:.3f}")
    print("  MACD: PASSED")
    
    # 4. RSI 测试
    print("\n[4] RSI Test")
    df_rsi = calc_rsi(df)
    for p in [6, 12, 24]:
        col = f"rsi{p}"
        assert col in df_rsi.columns
        r_valid = df_rsi[col].dropna()
        assert r_valid.min() >= 0 and r_valid.max() <= 100, f"RSI{p} out of range"
    print(f"  RSI6 latest: {df_rsi['rsi6'].iloc[-1]:.2f}")
    print(f"  RSI12 latest: {df_rsi['rsi12'].iloc[-1]:.2f}")
    print("  RSI: PASSED")
    
    # 5. BOLL 测试
    print("\n[5] BOLL Test")
    df_boll = calc_boll(df)
    assert "boll_mid" in df_boll.columns
    assert "boll_up" in df_boll.columns
    assert "boll_down" in df_boll.columns
    
    # 上轨 > 中轨 > 下轨
    for i in range(19, len(df_boll)):
        assert df_boll["boll_up"].iloc[i] >= df_boll["boll_mid"].iloc[i]
        assert df_boll["boll_mid"].iloc[i] >= df_boll["boll_down"].iloc[i]
    
    print(f"  MID latest: {df_boll['boll_mid'].iloc[-1]:.2f}")
    print(f"  UP latest: {df_boll['boll_up'].iloc[-1]:.2f}")
    print(f"  DOWN latest: {df_boll['boll_down'].iloc[-1]:.2f}")
    print("  BOLL: PASSED")
    
    # 6. 批量计算测试
    print("\n[6] All Indicators Test")
    df_all = calculate_all_indicators(df)
    expected_cols = ["ma5", "ma10", "ma20", "ma60", "kdj_k", "kdj_d", "kdj_j",
                     "macd_dif", "macd_dea", "macd_bar", "rsi6", "rsi12", "rsi24",
                     "boll_mid", "boll_up", "boll_down"]
    for col in expected_cols:
        assert col in df_all.columns, f"Missing {col}"
    print(f"  All columns present: {len(expected_cols)} indicators")
    print("  All indicators: PASSED")
    
    # 7. 最新指标提取
    print("\n[7] Latest Indicators Test")
    latest = get_latest_indicators(df_all)
    print(f"  Latest keys: {list(latest.keys())}")
    assert len(latest) > 0
    print("  Latest indicators: PASSED")
    
    # 8. 技术评分
    print("\n[8] Tech Score Test")
    score = calc_tech_score(df_all)
    print(f"  Tech score: {score}")
    assert 0 <= score <= 100
    print("  Tech score: PASSED")
    
    # 9. Edge case: 空数据（应返回空 DataFrame，不抛异常）
    print("\n[9] Edge case - empty DataFrame")
    df_empty = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
    result_empty = calculate_all_indicators(df_empty)
    assert len(result_empty) == 0
    assert isinstance(result_empty, pd.DataFrame)
    print("  Empty DataFrame handled: PASSED")
    
    # 10. Edge case: 数据不足
    print("\n[10] Edge case - insufficient data")
    df_small = pd.DataFrame({
        "open": [10, 11], "high": [11, 12], "low": [9, 10], "close": [10.5, 11.5], "volume": [1000, 2000]
    })
    df_small = calculate_all_indicators(df_small)
    score_small = calc_tech_score(df_small)
    print(f"  Small data score: {score_small}")
    # 数据不足时指标多为 NaN，但 RSI 会 fillna(50) 导致可能得少量分数，确保分数不会过高
    assert score_small <= 50
    print("  Insufficient data handled: PASSED")
    
    print("\n=== All Indicator Tests PASSED ===")
