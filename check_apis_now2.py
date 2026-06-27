import urllib.request
import urllib.error
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:5889"
results = {}

def call_api(path, method="GET", timeout=30):
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                data = json.loads(body)
            except:
                data = body
            return {"status": resp.status, "body": data, "ok": True}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            data = json.loads(body)
        except:
            data = body
        return {"status": e.code, "body": data, "ok": False}
    except Exception as e:
        return {"status": -1, "body": str(e), "ok": False}

paths = {
    "health": "/api/health",
    "quote_health": "/api/v1/quote/health",
    "ohlcv": "/api/v1/quote/000001/ohlcv?period=daily&limit=5",
    "indicators": "/api/v1/quote/000001/indicators?period=daily&limit=120",
    "signal": "/api/v1/quote/000001/signal",
    "patterns": "/api/v1/quote/000001/patterns?period=daily",
    "volume": "/api/v1/quote/000001/volume-analysis?period=daily",
    "support_resistance": "/api/v1/quote/000001/support-resistance?period=daily",
    "resonance": "/api/v1/quote/000001/resonance",
    "market_overview": "/api/v1/market/overview",
    "watchlist": "/api/v1/watchlist/with-quotes",
    "signals": "/api/v1/signals",
    "backtest_strategies": "/api/v1/backtest/strategies",
}

for name, path in paths.items():
    results[name] = call_api(path)

with open("api_check_now2.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

def validate(name, result):
    issues = []
    if not result["ok"]:
        issues.append(f"HTTP {result['status']}")
        return issues
    body = result.get("body", {})
    if name == "ohlcv":
        if "detail" in body:
            issues.append(f"detail: {body['detail']}")
        else:
            data = body.get("data", [])
            if not data:
                issues.append("empty data")
            else:
                last = data[0]
                close = last.get("close", 0)
                volume = last.get("volume", 0)
                date_str = last.get("date", "")
                if close <= 0:
                    issues.append(f"close <= 0: {close}")
                if volume <= 0:
                    issues.append(f"volume <= 0: {volume}")
                if not date_str:
                    issues.append("missing date")
                else:
                    try:
                        d = datetime.strptime(str(date_str), "%Y%m%d")
                        delta = (datetime.now() - d).days
                        if delta > 5:
                            issues.append(f"stale: {delta} days")
                    except:
                        issues.append(f"bad date: {date_str}")
    elif name == "indicators":
        indicators = body.get("indicators", {})
        ma5 = indicators.get("ma5", 0)
        if ma5 <= 0:
            issues.append(f"MA5 <= 0: {ma5}")
        data = body.get("data", [])
        if data and len(data) > 1:
            closes = [d.get("close", 0) for d in data[:5]]
            if len(set(closes)) == 1 and closes[0] > 0:
                issues.append(f"hardcoded? same close: {closes[0]}")
    elif name == "market_overview":
        indices = body.get("indices", [])
        if not indices:
            issues.append("empty indices")
        else:
            sh = indices[0]
            if sh.get("close", 0) <= 0:
                issues.append("sh close <= 0")
            if sh.get("volume", 0) <= 0:
                issues.append("sh volume <= 0")
    elif name == "watchlist":
        items = body.get("items", [])
        if not items:
            issues.append("empty watchlist")
        else:
            for item in items:
                quote = item.get("quote", {})
                if quote.get("close", 0) <= 0:
                    issues.append(f"{item.get('symbol')} close <= 0")
                if quote.get("source", "").startswith("mock"):
                    issues.append(f"{item.get('symbol')} mock source")
    elif name == "signals":
        signals = body.get("signals", [])
        if not signals:
            issues.append("empty signals")
        else:
            for sig in signals:
                if sig.get("price", 0) <= 0:
                    issues.append(f"{sig.get('symbol')} price <= 0")
    elif name == "signal":
        stype = body.get("type", "")
        if stype not in ["BUY", "SELL", "HOLD"]:
            issues.append(f"unknown signal type: {stype}")
    elif name == "volume":
        nodes = body.get("nodes", [])
        if not nodes:
            issues.append("empty volume nodes")
    elif name == "patterns":
        patterns = body.get("patterns", [])
        if not patterns:
            issues.append("empty patterns")
    elif name == "support_resistance":
        levels = body.get("levels", [])
        if not levels:
            issues.append("empty levels")
    elif name == "resonance":
        if body.get("resonance") is None:
            issues.append("resonance field missing")
    return issues

validation = {}
for name, result in results.items():
    validation[name] = validate(name, result)

summary = {
    "timestamp": datetime.now().isoformat(),
    "api_status": {k: {"status": v["status"], "ok": v["ok"]} for k, v in results.items()},
    "validation": validation,
    "total": len(results),
    "ok": sum(1 for v in results.values() if v["ok"]),
    "issue_count": sum(len(v) for v in validation.values() if v)
}

with open("api_validation_now2.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"TOTAL: {summary['total']} OK: {summary['ok']} FAIL: {summary['total'] - summary['ok']} ISSUES: {summary['issue_count']}")
for name, issues in validation.items():
    if issues:
        print(f"  {name}: {issues}")
