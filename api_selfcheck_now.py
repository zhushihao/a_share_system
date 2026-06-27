#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quant Workbench API 全面自检脚本
"""

import json
import requests
import sys
from datetime import datetime

BASE_URL = "http://localhost:5889"
RESULTS = {}

def test_api(name, method, endpoint, expected_fields=None, validation_fn=None):
    """测试单个API并记录结果"""
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = requests.request(method, url, timeout=30)
        status = resp.status_code
        try:
            data = resp.json()
        except Exception:
            data = {"_raw": resp.text[:500]}
        
        ok = status == 200
        summary = ""
        
        if ok and expected_fields:
            missing = [f for f in expected_fields if f not in data]
            if missing:
                ok = False
                summary = f"缺少字段: {missing}"
            else:
                summary = f"字段完整: {expected_fields}"
        
        if ok and validation_fn:
            try:
                validation_fn(data)
                summary += " | 验证通过"
            except Exception as e:
                ok = False
                summary += f" | 验证失败: {e}"
        
        if not summary:
            summary = f"状态码 {status}"
        
        RESULTS[name] = {
            "status": "OK" if ok else "FAILED",
            "http_status": status,
            "summary": summary,
            "data_sample": json.dumps(data, ensure_ascii=False, indent=None)[:500] if isinstance(data, dict) else str(data)[:500]
        }
        
        # 保存完整响应到文件
        with open(f"check_{name.replace(' ', '_').replace('/', '_').lower()}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
    except requests.exceptions.ConnectionError:
        RESULTS[name] = {"status": "FAILED", "http_status": 0, "summary": "连接失败: 后端未运行", "data_sample": ""}
    except Exception as e:
        RESULTS[name] = {"status": "FAILED", "http_status": -1, "summary": f"异常: {e}", "data_sample": ""}
    
    print(f"  [{RESULTS[name]['status']}] {name}: {RESULTS[name]['summary']}")

# ========== 验证函数 ==========

def validate_daily(data):
    """验证OHLCV数据真实性"""
    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("返回数据为空或非数组")
    latest = data[-1]
    for k in ["open", "high", "low", "close", "volume"]:
        if k not in latest:
            raise ValueError(f"缺少{k}")
    if latest["close"] <= 0 or latest["close"] > 100000:
        raise ValueError(f"收盘价异常: {latest['close']}")
    if latest["high"] < latest["low"]:
        raise ValueError(f"high < low")
    if latest["volume"] < 0:
        raise ValueError(f"volume为负")
    print(f"    -> 最新日期: {latest.get('date', 'N/A')}, 收盘价: {latest['close']}, 成交量: {latest['volume']}")

def validate_indicators(data):
    """验证技术指标真实性"""
    for k in ["ma", "kdj", "macd", "rsi", "boll", "obv", "dmi"]:
        if k not in data:
            raise ValueError(f"缺少指标: {k}")
    # 检查KDJ值是否合理
    kdj = data.get("kdj", {})
    if "k" in kdj and kdj["k"] is not None:
        if not (0 <= kdj["k"] <= 100):
            raise ValueError(f"K值异常: {kdj['k']}")
    print(f"    -> 指标完整: MA/KDJ/MACD/RSI/BOLL/OBV/DMI")

def validate_signal(data):
    """验证信号数据"""
    for k in ["signal_type", "entry_price", "stop_loss", "take_profit", "confidence", "rationale"]:
        if k not in data:
            raise ValueError(f"缺少字段: {k}")
    st = data["signal_type"]
    ep = data["entry_price"]
    sl = data["stop_loss"]
    tp = data["take_profit"]
    
    if st == "BUY":
        if sl >= ep:
            raise ValueError(f"BUY时 stop_loss({sl}) >= entry_price({ep})")
        if tp <= ep:
            raise ValueError(f"BUY时 take_profit({tp}) <= entry_price({ep})")
    elif st == "SELL":
        if sl <= ep:
            raise ValueError(f"SELL时 stop_loss({sl}) <= entry_price({ep})")
        if tp >= ep:
            raise ValueError(f"SELL时 take_profit({tp}) >= entry_price({ep})")
    elif st == "HOLD":
        if sl != 0 or tp != 0:
            raise ValueError(f"HOLD时 stop_loss/take_profit 应为0,  got sl={sl}, tp={tp}")
    
    print(f"    -> signal: {st}, entry: {ep}, SL: {sl}, TP: {tp}, confidence: {data['confidence']}")

def validate_patterns(data):
    """验证形态识别"""
    if "patterns" not in data:
        raise ValueError("缺少patterns字段")
    patterns = data["patterns"]
    if not isinstance(patterns, list):
        raise ValueError("patterns不是数组")
    for p in patterns:
        for k in ["pattern_type", "name", "position", "accuracy", "reason"]:
            if k not in p:
                raise ValueError(f"pattern缺少字段: {k}")
    print(f"    -> 发现 {len(patterns)} 个形态")

def validate_volume(data):
    """验证量价分析"""
    if "nodes" not in data:
        raise ValueError("缺少nodes字段")
    nodes = data["nodes"]
    if not isinstance(nodes, list):
        raise ValueError("nodes不是数组")
    for n in nodes:
        for k in ["node_type", "volume", "price", "timestamp", "strength", "reason"]:
            if k not in n:
                raise ValueError(f"node缺少字段: {k}")
    print(f"    -> 发现 {len(nodes)} 个量价节点")

def validate_sr(data):
    """验证支撑阻力"""
    for k in ["supports", "resistances", "fibonacci_levels"]:
        if k not in data:
            raise ValueError(f"缺少字段: {k}")
    for level in data["supports"] + data["resistances"]:
        if level <= 0:
            raise ValueError(f"支撑/阻力位为0或负数: {level}")
    print(f"    -> supports: {len(data['supports'])}, resistances: {len(data['resistances'])}")

def validate_resonance(data):
    """验证多周期共振"""
    for k in ["daily_trend", "weekly_trend", "monthly_trend", "resonance", "confidence", "direction"]:
        if k not in data:
            raise ValueError(f"缺少字段: {k}")
    print(f"    -> resonance: {data['resonance']}, direction: {data['direction']}, confidence: {data['confidence']}")

def validate_signals_list(data):
    """验证信号列表"""
    if not isinstance(data, list):
        raise ValueError("返回数据不是数组")
    # 允许为空，但如果是假数据应该有特征
    print(f"    -> 信号数量: {len(data)}")

def validate_watchlist(data):
    """验证自选股"""
    if not isinstance(data, list):
        raise ValueError("返回数据不是数组")
    print(f"    -> 自选股数量: {len(data)}")

def validate_strategies(data):
    """验证策略列表"""
    if not isinstance(data, list):
        raise ValueError("返回数据不是数组")
    names = [s.get("name", s.get("strategy_name", "")) for s in data]
    if "signal_composer" not in str(names).lower() and "signal_composer" not in str(data).lower():
        print(f"    -> 警告: 未找到 signal_composer 策略")
    print(f"    -> 策略数量: {len(data)}, 策略: {names}")

# ========== 主程序 ==========

if __name__ == "__main__":
    print("="*60)
    print("Quant Workbench API 全面自检")
    print(f"时间: {datetime.now().isoformat()}")
    print("="*60)
    
    print("\n【后端API可用性测试】")
    
    test_api("Daily Quote", "GET", "/api/v1/quote/000001/daily?limit=30", 
             expected_fields=None, validation_fn=validate_daily)
    
    test_api("Indicators", "GET", "/api/v1/quote/000001/indicators?period=daily",
             expected_fields=None, validation_fn=validate_indicators)
    
    test_api("Signal", "GET", "/api/v1/quote/000001/signal?period=daily",
             expected_fields=None, validation_fn=validate_signal)
    
    test_api("Patterns", "GET", "/api/v1/quote/000001/patterns?period=daily",
             expected_fields=None, validation_fn=validate_patterns)
    
    test_api("Volume Analysis", "GET", "/api/v1/quote/000001/volume-analysis?period=daily",
             expected_fields=None, validation_fn=validate_volume)
    
    test_api("Support Resistance", "GET", "/api/v1/quote/000001/support-resistance?period=daily",
             expected_fields=None, validation_fn=validate_sr)
    
    test_api("Resonance", "GET", "/api/v1/quote/000001/resonance",
             expected_fields=None, validation_fn=validate_resonance)
    
    test_api("Signals List", "GET", "/api/v1/signals?limit=5",
             expected_fields=None, validation_fn=validate_signals_list)
    
    test_api("Watchlist", "GET", "/api/v1/watchlist",
             expected_fields=None, validation_fn=validate_watchlist)
    
    test_api("Strategies", "GET", "/api/v1/backtest/strategies",
             expected_fields=None, validation_fn=validate_strategies)
    
    # 额外测试 health endpoint
    test_api("Health", "GET", "/api/health",
             expected_fields=["status", "version", "timestamp"], validation_fn=None)
    
    # 保存结果
    with open("api_selfcheck_results.json", "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    
    # 统计
    ok_count = sum(1 for r in RESULTS.values() if r["status"] == "OK")
    total = len(RESULTS)
    print(f"\n【统计】通过: {ok_count}/{total}")
    print(f"结果已保存到 api_selfcheck_results.json")
