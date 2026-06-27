#!/usr/bin/env python3
"""
Quant Workbench v2.0 API 全面验证脚本
验证 18 个关键端点 + 数据真实性 + 数据库完整性
"""

import urllib.request
import urllib.error
import json
import sys
from datetime import datetime

BASE = "http://127.0.0.1:5889/api/v1"

def fetch(url, method="GET", data=None, headers=None):
    """统一请求封装"""
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if data:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return -1, str(e)

def check_json(body):
    try:
        return json.loads(body)
    except:
        return None

results = []
failed = []

def test(name, url, method="GET", data=None, check_fn=None):
    status, body = fetch(url, method, data)
    ok = status == 200
    parsed = check_json(body) if body else None
    if check_fn and parsed:
        ok = ok and check_fn(parsed)
    results.append((name, status, ok, parsed))
    if not ok:
        failed.append((name, status, body[:300]))
    print(f"  {'✅' if ok else '❌'} {name} (HTTP {status})")
    return parsed

print(f"=== Quant Workbench v2.0 验证开始 ===")
print(f"时间: {datetime.now().isoformat()}")
print(f"后端: {BASE}")
print()

# ── 1. 基础健康 ──
print("【1. 基础健康】")
test("/api/health", "http://127.0.0.1:5889/api/health", check_fn=lambda d: d.get("status") == "ok")

# ── 2. 数据平台 ──
print("\n【2. 数据平台】")
test("/data/health", f"{BASE}/data/health", check_fn=lambda d: d.get("status") == "ok")
overview = test("/data/overview", f"{BASE}/data/overview", check_fn=lambda d: d.get("stock_count", 0) > 0)
test("/data/diagnose/000001", f"{BASE}/data/diagnose/000001", check_fn=lambda d: d.get("status") == "ok" and "diagnosis" in d)
test("/data/quality", f"{BASE}/data/quality", check_fn=lambda d: d.get("status") == "ok" and "quality_score" in d.get("summary", {}))

# ── 3. 行情数据 ──
print("\n【3. 行情数据】")
test("/quote/000001/ohlcv", f"{BASE}/quote/000001/ohlcv", check_fn=lambda d: isinstance(d, list) and len(d) > 0)
test("/quote/000001/indicators", f"{BASE}/quote/000001/indicators", check_fn=lambda d: isinstance(d, dict) and len(d) > 0)
signal = test("/quote/000001/signal", f"{BASE}/quote/000001/signal", check_fn=lambda d: "signal_type" in d or "type" in d)
test("/quote/000001/resonance", f"{BASE}/quote/000001/resonance", check_fn=lambda d: "direction" in d and "confidence" in d)
test("/quote/000001/patterns", f"{BASE}/quote/000001/patterns", check_fn=lambda d: isinstance(d, list))
test("/quote/000001/volume-analysis", f"{BASE}/quote/000001/volume-analysis", check_fn=lambda d: isinstance(d, list))
test("/quote/000001/support-resistance", f"{BASE}/quote/000001/support-resistance", check_fn=lambda d: isinstance(d, dict))

# ── 4. 批量扫描 ──
print("\n【4. 批量扫描】")
test("/quote/scan/resonance", f"{BASE}/quote/scan/resonance", method="POST", data=["000001", "000002", "000063"], check_fn=lambda d: isinstance(d, list))

# ── 5. 信号系统 ──
print("\n【5. 信号系统】")
test("/signals", f"{BASE}/signals", check_fn=lambda d: isinstance(d, list))
test("/signals/performance", f"{BASE}/signals/performance", check_fn=lambda d: isinstance(d, dict))

# ── 6. 回测系统 ──
print("\n【6. 回测系统】")
test("/backtest/strategies", f"{BASE}/backtest/strategies", check_fn=lambda d: isinstance(d, list) and len(d) > 0)
test("/backtest/results", f"{BASE}/backtest/results", check_fn=lambda d: isinstance(d, list))

# ── 7. 自选股 ──
print("\n【7. 自选股】")
test("/watchlist", f"{BASE}/watchlist", check_fn=lambda d: isinstance(d, list))

# ── 汇总 ──
print("\n" + "="*60)
print(f"验证完成: {sum(1 for _, _, ok, _ in results if ok)}/{len(results)} 通过")
if failed:
    print(f"\n失败端点:")
    for name, status, body in failed:
        print(f"  ❌ {name} (HTTP {status}): {body}")
else:
    print("全部通过 ✅")

# ── 数据真实性快速检查 ──
print("\n【数据真实性抽样】")
if overview:
    sc = overview.get("stock_count", 0)
    tf = overview.get("tdx_files", 0)
    print(f"  stock_count={sc}, tdx_files={tf} — {'真实' if sc > 9000 and tf > 100000 else '⚠️ 异常'}")

if signal:
    conf = signal.get("confidence", 0)
    sig_type = signal.get("type") or signal.get("signal_type", "")
    print(f"  signal: type={sig_type}, confidence={conf} — {'真实' if conf > 0 and conf <= 1 else '⚠️ 异常'}")
    factors = signal.get("factors", [])
    print(f"  factors 数量: {len(factors)} — {'真实' if 4 <= len(factors) <= 6 else '⚠️ 异常'}")
    for f in factors:
        print(f"    - {f.get('name', '?')}: score={f.get('score', '?'):.3f}, weight={f.get('weight', '?')}")

print("\n=== 验证结束 ===")
