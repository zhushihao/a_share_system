#!/usr/bin/env python3
"""API 批量检查脚本"""
import urllib.request
import urllib.error
import json
import os
from datetime import datetime

BASE_URL = "http://localhost:5889"

def fetch(path):
    try:
        req = urllib.request.Request(f"{BASE_URL}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else None
            return {"status": resp.status, "data": data, "raw": body[:3000]}
    except Exception as e:
        return {"status": 0, "error": str(e)}

results = {}

print("=== /api/health ===")
r = fetch("/api/health")
print(json.dumps(r, ensure_ascii=False, indent=2))
results["health"] = r

print("\n=== /api/v1/data/stock-list?page=1&size=20 ===")
r = fetch("/api/v1/data/stock-list?page=1&size=20")
data = r.get("data", {})
items = data.get("items", []) if isinstance(data, dict) else []
print(f"Total: {data.get('total') if isinstance(data,dict) else 'N/A'}, Items: {len(items)}")
for i in items[:5]:
    print(f"  {i.get('code')} | {i.get('name')} | type={i.get('type')}")
chinese_count = 0
numeric_name_count = 0
for i in items:
    n = str(i.get("name", ""))
    if any("\u4e00" <= c <= "\u9fff" for c in n):
        chinese_count += 1
    if n.isdigit():
        numeric_name_count += 1
print(f"Chinese names: {chinese_count}/{len(items)}, Numeric names: {numeric_name_count}/{len(items)}")
r["name_analysis"] = {"chinese": chinese_count, "numeric": numeric_name_count, "total": len(items)}
results["stock_list"] = r

print("\n=== /api/v1/stock/search?q=000001 ===")
r = fetch("/api/v1/stock/search?q=000001")
print(json.dumps(r, ensure_ascii=False, indent=2)[:800])
results["stock_search"] = r

print("\n=== /api/v1/watchlist/with-quotes ===")
r = fetch("/api/v1/watchlist/with-quotes")
data = r.get("data", [])
wl = data if isinstance(data, list) else data.get("items", [])
print(f"Count: {len(wl)}")
null_name_count = 0
for i in wl[:5]:
    q = i.get("quote", {}) or {}
    name = i.get("name")
    qname = q.get("name")
    if qname is None:
        null_name_count += 1
    print(f"  symbol={i.get('symbol')} name={name} quote.name={qname}")
for i in wl:
    q = i.get("quote", {}) or {}
    if q.get("name") is None:
        null_name_count += 1
print(f"quote.name is null: {null_name_count}/{len(wl)}")
r["null_name_count"] = null_name_count
r["watchlist_count"] = len(wl)
results["watchlist_with_quotes"] = r

print("\n=== /api/v1/quote/000001.SZ/ohlcv?limit=10 ===")
r = fetch("/api/v1/quote/000001.SZ/ohlcv?limit=10")
data = r.get("data", {})
ohlcv = data.get("data", []) if isinstance(data, dict) else data
print(f"Count: {len(ohlcv)}")
if ohlcv:
    for o in ohlcv[:3]:
        print(f"  date={o.get('date')} open={o.get('open')} close={o.get('close')} is_filled={o.get('is_filled')}")
    valid_prices = sum(1 for o in ohlcv if o.get("close", 0) > 0)
    print(f"Prices > 0: {valid_prices}/{len(ohlcv)}")
    r["price_check"] = {"valid": valid_prices, "total": len(ohlcv)}
results["ohlcv"] = r

print("\n=== /api/v1/quote/000001.SZ/indicators ===")
r = fetch("/api/v1/quote/000001.SZ/indicators")
data = r.get("data", {})
print(json.dumps(data, ensure_ascii=False, indent=2)[:1000])
if isinstance(data, dict):
    has_labels = "labels" in data
    keys = [k for k in data.keys() if k != "labels"]
    labels = data.get("labels", {})
    print(f"Keys: {keys[:10]}, Has labels: {has_labels}")
    r["indicator_analysis"] = {"has_labels": has_labels, "keys": keys, "labels_keys": list(labels.keys())}
results["indicators"] = r

print("\n=== /api/v1/quote/000001.SZ/patterns ===")
r = fetch("/api/v1/quote/000001.SZ/patterns")
data = r.get("data", {})
patterns = data.get("patterns", []) if isinstance(data, dict) else data
print(f"Count: {len(patterns)}")
if patterns:
    for p in patterns[:3]:
        print(f"  pattern={p.get('pattern')} name={p.get('name')} display_name={p.get('display_name')}")
    has_display = sum(1 for p in patterns if p.get("display_name"))
    chinese_display = sum(1 for p in patterns if p.get("display_name") and any("\u4e00" <= c <= "\u9fff" for c in str(p.get("display_name"))))
    print(f"has_display_name: {has_display}/{len(patterns)}, chinese_display: {chinese_display}/{len(patterns)}")
    r["pattern_analysis"] = {"has_display_name": has_display, "chinese_display": chinese_display, "total": len(patterns)}
results["patterns"] = r

print("\n=== /api/v1/quote/000001.SZ/signal ===")
r = fetch("/api/v1/quote/000001.SZ/signal")
data = r.get("data", {})
print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
if isinstance(data, dict):
    sig_type = data.get("signal_type")
    strategy = data.get("strategy")
    is_chinese = bool(sig_type and any("\u4e00" <= c <= "\u9fff" for c in str(sig_type)))
    print(f"signal_type={sig_type} strategy={strategy} is_chinese={is_chinese}")
    r["signal_analysis"] = {"signal_type": sig_type, "strategy": strategy, "is_chinese": is_chinese}
results["signal"] = r

print("\n=== /api/v1/quote/000001.SZ/resonance ===")
r = fetch("/api/v1/quote/000001.SZ/resonance")
print(json.dumps(r.get("data"), ensure_ascii=False, indent=2)[:600])
results["resonance"] = r

print("\n=== /api/v1/quote/000001.SZ/volume-analysis ===")
r = fetch("/api/v1/quote/000001.SZ/volume-analysis")
print(json.dumps(r.get("data"), ensure_ascii=False, indent=2)[:600])
results["volume_analysis"] = r

print("\n=== /api/v1/quote/000001.SZ/support-resistance ===")
r = fetch("/api/v1/quote/000001.SZ/support-resistance")
print(json.dumps(r.get("data"), ensure_ascii=False, indent=2)[:600])
results["support_resistance"] = r

print("\n=== /api/v1/market/overview ===")
r = fetch("/api/v1/market/overview")
print(json.dumps(r.get("data"), ensure_ascii=False, indent=2)[:800])
results["market_overview"] = r

print("\n=== /api/v1/market/sentiment ===")
r = fetch("/api/v1/market/sentiment")
data = r.get("data", {})
print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
if isinstance(data, dict):
    source = data.get("source", "missing")
    print(f"source={source}")
    r["sentiment_analysis"] = {"source": source}
results["market_sentiment"] = r

print("\n=== /api/v1/market/hotspots ===")
r = fetch("/api/v1/market/hotspots")
data = r.get("data", {})
hotspots = data if isinstance(data, list) else data.get("items", [])
print(f"Count: {len(hotspots)}")
if hotspots:
    print(f"First: {hotspots[0]}")
else:
    print("Empty hotspots")
results["hotspots"] = r

print("\n=== /api/v1/market/sectors ===")
r = fetch("/api/v1/market/sectors")
data = r.get("data", {})
sectors = data if isinstance(data, list) else data.get("items", [])
print(f"Count: {len(sectors)}")
if sectors:
    for s in sectors[:3]:
        print(f"  {s.get('name')} stock_count={s.get('stock_count')}")
    zero_stock = sum(1 for s in sectors if s.get("stock_count", -1) == 0)
    print(f"stock_count=0: {zero_stock}/{len(sectors)}")
    r["sector_analysis"] = {"zero_stock_count": zero_stock, "total": len(sectors)}
results["sectors"] = r

print("\n=== /api/v1/signals ===")
r = fetch("/api/v1/signals")
data = r.get("data", {})
signals = data if isinstance(data, list) else data.get("items", [])
print(f"Count: {len(signals)}")
if signals:
    for s in signals[:5]:
        print(f"  {s.get('symbol')} type={s.get('signal_type')} strategy={s.get('strategy')} name={s.get('name')}")
    has_name = sum(1 for s in signals if s.get("name"))
    chinese_name = sum(1 for s in signals if s.get("name") and any("\u4e00" <= c <= "\u9fff" for c in str(s.get("name"))))
    print(f"has_name: {has_name}, chinese_name: {chinese_name}")
    r["signals_analysis"] = {"has_name": has_name, "chinese_name": chinese_name, "total": len(signals)}
results["signals"] = r

print("\n=== /api/v1/backtest/strategies ===")
r = fetch("/api/v1/backtest/strategies")
data = r.get("data", {})
strategies = data if isinstance(data, list) else data.get("items", [])
print(f"Count: {len(strategies)}")
if strategies:
    for s in strategies[:3]:
        print(f"  {s.get('name')} {s.get('type')}")
results["backtest_strategies"] = r

os.makedirs("reports/selfcheck", exist_ok=True)
with open("reports/selfcheck/api_raw_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n=== Saved to reports/selfcheck/api_raw_results.json ===")
