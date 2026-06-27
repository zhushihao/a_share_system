#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""系统自检脚本 - 只排查不修复"""
import requests
import json
import datetime
import os
import sys

BASE_URL = "http://127.0.0.1:5889"

# 收集所有结果
results = {
    "timestamp": datetime.datetime.now().isoformat(),
    "api_checks": [],
    "data_reality": {},
    "data_timeliness": {},
    "issues": []
}

def check_api(name, path, method="GET", timeout=10):
    """检查API端点"""
    try:
        url = f"{BASE_URL}{path}"
        if method == "GET":
            resp = requests.get(url, timeout=timeout)
        elif method == "POST":
            resp = requests.post(url, timeout=timeout)
        
        status = resp.status_code
        content_type = resp.headers.get('Content-Type', 'unknown')
        
        # 尝试解析JSON
        try:
            data = resp.json()
            data_preview = json.dumps(data, ensure_ascii=False)[:500]
        except:
            data = resp.text[:500]
            data_preview = str(data)
        
        return {
            "name": name,
            "path": path,
            "status": status,
            "ok": status == 200,
            "content_type": content_type,
            "preview": data_preview
        }
    except requests.exceptions.ConnectionError as e:
        return {"name": name, "path": path, "status": -1, "ok": False, "error": f"ConnectionError: {str(e)[:100]}"}
    except requests.exceptions.Timeout as e:
        return {"name": name, "path": path, "status": -2, "ok": False, "error": f"Timeout: {str(e)[:100]}"}
    except Exception as e:
        return {"name": name, "path": path, "status": -3, "ok": False, "error": f"Exception: {str(e)[:100]}"}

print("=" * 60)
print("=== 系统自检脚本 - 只排查不修复 ===")
print("=" * 60)

# T1: 后端存活检查
print("\n=== T1: 后端存活检查 ===")
health = check_api("health", "/api/health")
results["api_checks"].append(health)
print(f"  /api/health: {health['status']} {'OK' if health['ok'] else 'FAIL'}")
if health['ok']:
    try:
        h = json.loads(health['preview'])
        print(f"  版本: {h.get('version', 'unknown')}")
        print(f"  时间戳: {h.get('timestamp', 'unknown')}")
    except:
        print(f"  响应: {health['preview'][:200]}")

# T2: 核心API可用性检查 (11个API)
print("\n=== T2: 核心API可用性检查 ===")
api_list = [
    ("quote_000001", "/api/v1/quote/000001"),
    ("quote_indicators", "/api/v1/quote/000001/indicators"),
    ("market_overview", "/api/v1/market/overview"),
    ("watchlist_groups", "/api/v1/watchlist/groups"),
    ("watchlist_with_quotes", "/api/v1/watchlist/with-quotes"),
    ("signals", "/api/v1/signals"),
    ("data_overview", "/api/v1/data/overview"),
    ("stock_list", "/api/v1/data/stock-list?limit=10"),
    ("data_health", "/api/v1/data/health"),
    ("data_platform_health", "/api/v1/data-platform/health"),
    ("market_indices", "/api/v1/market/indices"),
]

for name, path in api_list:
    result = check_api(name, path)
    results["api_checks"].append(result)
    status_str = f"{result['status']}" if result['status'] > 0 else result.get('error', 'UNKNOWN')
    ok_str = "OK" if result['ok'] else "FAIL"
    print(f"  {path}: HTTP {status_str} [{ok_str}]")

# T3: 数据真实性检查
print("\n=== T3: 数据真实性检查 ===")

# 检查 000001 报价数据
quote_result = check_api("quote_detail", "/api/v1/quote/000001")
if quote_result['ok']:
    try:
        quote_data = json.loads(quote_result['preview'])
        if 'data' in quote_data:
            quote_data = quote_data['data']
        
        close = quote_data.get('close', quote_data.get('price', 0))
        volume = quote_data.get('volume', 0)
        high = quote_data.get('high', 0)
        low = quote_data.get('low', 0)
        open_price = quote_data.get('open', 0)
        
        results["data_reality"]["quote_000001"] = {
            "close": close,
            "volume": volume,
            "high": high,
            "low": low,
            "open": open_price,
            "close_ok": close > 0,
            "volume_ok": volume > 0,
            "high_ok": high > 0,
            "low_ok": low > 0,
            "raw_preview": quote_result['preview'][:300]
        }
        
        print(f"  000001: close={close}, open={open_price}, volume={volume}, high={high}, low={low}")
        print(f"  价格>0: {'OK' if close > 0 else 'FAIL'}, 成交量>0: {'OK' if volume > 0 else 'FAIL'}")
        
        # 检测硬编码/假数据
        if close == 100.0 or close == 10.0 or volume == 1000000 or volume == 999999:
            print(f"  ⚠️ 警告: 价格或成交量可能是硬编码值!")
            results["issues"].append({"severity": "HIGH", "issue": f"000001 价格/成交量可能是硬编码: close={close}, volume={volume}", "location": "/api/v1/quote/000001"})
    except Exception as e:
        results["data_reality"]["quote_000001"] = {"error": str(e), "preview": quote_result['preview'][:300]}
        print(f"  解析失败: {e}")
        results["issues"].append({"severity": "MEDIUM", "issue": f"000001 报价数据解析失败: {e}", "location": "/api/v1/quote/000001"})
else:
    results["data_reality"]["quote_000001"] = {"error": "API unavailable", "status": quote_result['status']}
    print(f"  000001 报价API不可用: {quote_result.get('error', 'unknown')}")
    results["issues"].append({"severity": "HIGH", "issue": "000001 报价API不可用", "location": "/api/v1/quote/000001"})

# 检查指标数据
indicators_result = check_api("indicators_detail", "/api/v1/quote/000001/indicators")
if indicators_result['ok']:
    try:
        ind_data = json.loads(indicators_result['preview'])
        if 'data' in ind_data:
            ind_data = ind_data['data']
        
        indicators = ind_data.get('indicators', {})
        indicator_names = ['MA5', 'MA10', 'MA20', 'MACD', 'RSI', 'KDJ', 'BOLL']
        found_indicators = {k: v for k, v in indicators.items() if k in indicator_names}
        
        results["data_reality"]["indicators"] = {
            "found": list(found_indicators.keys()),
            "count": len(found_indicators),
            "ok": len(found_indicators) > 0,
            "raw_preview": indicators_result['preview'][:300]
        }
        print(f"  找到指标: {list(found_indicators.keys())}")
        
        # 检查指标值是否合理
        for name, val in found_indicators.items():
            if val is not None and isinstance(val, (int, float)) and val <= 0:
                print(f"  ⚠️ 警告: 指标 {name} = {val} 可能不合理")
    except Exception as e:
        results["data_reality"]["indicators"] = {"error": str(e), "preview": indicators_result['preview'][:300]}
        print(f"  解析失败: {e}")
else:
    results["data_reality"]["indicators"] = {"error": "API unavailable", "status": indicators_result['status']}
    print(f"  指标API不可用")

# 检查信号数据
signals_result = check_api("signals_detail", "/api/v1/signals")
if signals_result['ok']:
    try:
        sig_data = json.loads(signals_result['preview'])
        if 'data' in sig_data:
            sig_data = sig_data['data']
        
        signals_list = sig_data if isinstance(sig_data, list) else sig_data.get('signals', [])
        
        if signals_list and len(signals_list) > 0:
            first_signal = signals_list[0]
            results["data_reality"]["signals"] = {
                "count": len(signals_list),
                "first_type": first_signal.get('type', 'N/A'),
                "first_price": first_signal.get('price', 0),
                "first_symbol": first_signal.get('symbol', 'N/A'),
                "has_data": True,
                "raw_preview": signals_result['preview'][:300]
            }
            print(f"  信号数量: {len(signals_list)}, 首个: {first_signal.get('symbol', 'N/A')} {first_signal.get('type', 'N/A')} @ {first_signal.get('price', 'N/A')}")
        else:
            results["data_reality"]["signals"] = {"count": 0, "has_data": False, "raw_preview": signals_result['preview'][:200]}
            print(f"  信号列表为空（可能正常，如果当前无信号）")
    except Exception as e:
        results["data_reality"]["signals"] = {"error": str(e), "preview": signals_result['preview'][:300]}
        print(f"  解析失败: {e}")
else:
    results["data_reality"]["signals"] = {"error": "API unavailable", "status": signals_result['status']}
    print(f"  信号API不可用")

# 检查大盘数据
market_result = check_api("market_overview_detail", "/api/v1/market/overview")
if market_result['ok']:
    try:
        mkt_data = json.loads(market_result['preview'])
        if 'data' in mkt_data:
            mkt_data = mkt_data['data']
        
        indices = mkt_data.get('indices', {})
        shanghai = indices.get('sh', indices.get('000001.SH', {}))
        
        close = shanghai.get('close', 0) if isinstance(shanghai, dict) else 0
        change_pct = shanghai.get('change_pct', 0) if isinstance(shanghai, dict) else 0
        
        results["data_reality"]["market_overview"] = {
            "shanghai_close": close,
            "shanghai_change_pct": change_pct,
            "close_ok": close > 2000,  # 上证一般在 2000-5000
            "raw_preview": market_result['preview'][:300]
        }
        print(f"  上证 close={close}, change_pct={change_pct}%")
        
        if close < 2000 or close > 6000:
            print(f"  ⚠️ 警告: 上证点数 {close} 可能不合理")
            results["issues"].append({"severity": "MEDIUM", "issue": f"上证点数异常: {close}", "location": "/api/v1/market/overview"})
    except Exception as e:
        results["data_reality"]["market_overview"] = {"error": str(e), "preview": market_result['preview'][:300]}
        print(f"  解析失败: {e}")
else:
    results["data_reality"]["market_overview"] = {"error": "API unavailable", "status": market_result['status']}
    print(f"  大盘API不可用")

# T4: 数据时效性检查
print("\n=== T4: 数据时效性检查 ===")

# 尝试从OHLCV获取最新日期
ohlcv_result = check_api("ohlcv", "/api/v1/quote/000001/ohlcv")
if ohlcv_result['ok']:
    try:
        ohlcv_data = json.loads(ohlcv_result['preview'])
        if 'data' in ohlcv_data:
            ohlcv_data = ohlcv_data['data']
        
        ohlcv_list = ohlcv_data if isinstance(ohlcv_data, list) else ohlcv_data.get('data', [])
        if ohlcv_list and len(ohlcv_list) > 0:
            latest_date = ohlcv_list[-1].get('date', ohlcv_list[-1].get('trade_date', 'unknown'))
            results["data_timeliness"]["ohlcv_latest_date"] = latest_date
            print(f"  000001 OHLCV最新日期: {latest_date}")
            
            # 计算延迟
            try:
                latest_dt = datetime.datetime.strptime(str(latest_date), "%Y-%m-%d")
                today = datetime.datetime.now()
                delay_days = (today - latest_dt).days
                results["data_timeliness"]["delay_days"] = delay_days
                print(f"  数据延迟: {delay_days} 天")
                if delay_days > 2:
                    print(f"  ⚠️ 警告: 数据延迟超过2天")
                    results["issues"].append({"severity": "MEDIUM", "issue": f"数据延迟 {delay_days} 天", "location": "OHLCV数据"})
            except Exception as e:
                print(f"  无法计算延迟: {e}")
        else:
            results["data_timeliness"]["ohlcv_latest_date"] = "unknown (empty list)"
            print(f"  OHLCV数据为空")
    except Exception as e:
        results["data_timeliness"]["ohlcv_latest_date"] = f"error: {str(e)[:100]}"
        print(f"  解析失败: {e}")
else:
    results["data_timeliness"]["ohlcv_latest_date"] = f"API unavailable ({ohlcv_result['status']})"
    print(f"  OHLCV API不可用")

# 检查股票列表中的最新日期
stock_list_result = check_api("stock_list_detail", "/api/v1/data/stock-list?limit=5")
if stock_list_result['ok']:
    try:
        sl_data = json.loads(stock_list_result['preview'])
        if 'data' in sl_data:
            sl_data = sl_data['data']
        
        stocks = sl_data if isinstance(sl_data, list) else sl_data.get('stocks', [])
        if stocks and len(stocks) > 0:
            first_stock = stocks[0]
            last_date = first_stock.get('last_date', first_stock.get('date', 'unknown'))
            results["data_timeliness"]["stock_list_latest_date"] = last_date
            print(f"  股票列表最新日期: {last_date}")
        else:
            results["data_timeliness"]["stock_list_latest_date"] = "unknown (empty list)"
            print(f"  股票列表为空")
    except Exception as e:
        results["data_timeliness"]["stock_list_latest_date"] = f"error: {str(e)[:100]}"
        print(f"  解析失败: {e}")
else:
    results["data_timeliness"]["stock_list_latest_date"] = f"API unavailable ({stock_list_result['status']})"
    print(f"  股票列表API不可用")

# 保存结果到JSON文件
output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "selfcheck")
os.makedirs(output_dir, exist_ok=True)
json_path = os.path.join(output_dir, "selfcheck_raw_data.json")
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n原始数据已保存到: {json_path}")

# 输出汇总
print("\n" + "=" * 60)
print("=== 自检汇总 ===")
print("=" * 60)
ok_count = sum(1 for r in results["api_checks"] if r['ok'])
total_count = len(results["api_checks"])
print(f"API 检查: {ok_count}/{total_count} 通过")
print(f"发现问题: {len(results['issues'])} 个")
for i, issue in enumerate(results['issues'], 1):
    print(f"  {i}. [{issue['severity']}] {issue['issue']} (位置: {issue['location']})")

print(f"\n自检完成。")
