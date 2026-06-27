import urllib.request
import urllib.error
import json
import time
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
            except json.JSONDecodeError:
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

# Check APIs
results["health"] = call_api("/api/health")
results["quote_health"] = call_api("/api/v1/quote/health")
results["ohlcv"] = call_api("/api/v1/quote/ohlcv/000001?period=daily&limit=5")
results["indicators"] = call_api("/api/v1/quote/indicators/000001?period=daily&limit=120")
results["signal"] = call_api("/api/v1/signals/000001")
results["patterns"] = call_api("/api/v1/patterns/000001?period=daily")
results["volume"] = call_api("/api/v1/volume/000001?period=daily")
results["support_resistance"] = call_api("/api/v1/support-resistance/000001?period=daily")
results["resonance"] = call_api("/api/v1/resonance/000001")
results["market_overview"] = call_api("/api/v1/market/overview")
results["watchlist"] = call_api("/api/v1/watchlist/with-quotes")
results["signals_list"] = call_api("/api/v1/signals/list?limit=5")
results["backtest_strategies"] = call_api("/api/v1/backtest/strategies")

with open("api_check_now.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

def validate_data(name, result):
    issues = []
    if not result["ok"]:
        issues.append(f"API fail: {result['status']}")
        return issues
    body = result.get("body", {})
    if name == "ohlcv":
        if "detail" in body:
            issues.append(f"ohlcv error: {body['detail']}")
        else:
            data = body.get("data", [])
            if not data:
                issues.append("ohlcv empty")
            else:
                last = data[0]
                close = last.get("close", 0)
                volume = last.get("volume", 0)
                date_str = last.get("date", "")
                if close <= 0:
                    issues.append(f"close abnormal: {close}")
                if volume <= 0:
                    issues.append(f"volume abnormal: {volume}")
                if not date_str:
                    issues.append("date missing")
                else:
                    try:
                        d = datetime.strptime(str(date_str), "%Y%m%d")
                        delta = (datetime.now() - d).days
                        if delta > 5:
                            issues.append(f"stale data: {delta} days")
                    except:
                        issues.append(f"date format: {date_str}")
    elif name == "indicators":
        indicators = body.get("indicators", {})
        ma5 = indicators.get("ma5", 0)
        if ma5 <= 0:
            issues.append(f"MA5 abnormal: {ma5}")
        data = body.get("data", [])
        if data and len(data) > 1:
            closes = [d.get("close", 0) for d in data[:5]]
            if len(set(closes)) == 1 and closes[0] > 0:
                issues.append(f"possible hardcoded: {closes[0]}")
    elif name == "market_overview":
        indices = body.get("indices", [])
        if not indices:
            issues.append("indices empty")
        else:
            sh = indices[0]
            if sh.get("close", 0) <= 0:
                issues.append("sh close abnormal")
            if sh.get("volume", 0) <= 0:
                issues.append("sh volume abnormal")
    elif name == "watchlist":
        items = body.get("items", [])
        if not items:
            issues.append("watchlist empty")
        else:
            for item in items:
                quote = item.get("quote", {})
                if quote.get("close", 0) <= 0:
                    issues.append(f"watchlist {item.get('symbol')} close abnormal")
                if quote.get("source", "").startswith("mock"):
                    issues.append(f"watchlist {item.get('symbol')} mock data")
    elif name == "signals_list":
        signals = body.get("signals", [])
        if not signals:
            issues.append("signals empty")
        else:
            for sig in signals:
                if sig.get("price", 0) <= 0:
                    issues.append(f"signal {sig.get('symbol')} price abnormal")
    return issues

validation = {}
for name, result in results.items():
    validation[name] = validate_data(name, result)

summary = {
    "timestamp": datetime.now().isoformat(),
    "api_status": {k: {"status": v["status"], "ok": v["ok"]} for k, v in results.items()},
    "validation": validation,
    "total_apis": len(results),
    "ok_apis": sum(1 for v in results.values() if v["ok"]),
    "issue_count": sum(len(v) for v in validation.values() if v)
}

with open("api_validation_now.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"TOTAL: {summary['total_apis']} OK: {summary['ok_apis']} FAIL: {summary['total_apis'] - summary['ok_apis']} ISSUES: {summary['issue_count']}")
for name, issues in validation.items():
    if issues:
        print(f"  {name}: {issues}")
