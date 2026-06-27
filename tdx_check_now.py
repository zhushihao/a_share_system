# -*- coding: utf-8 -*-
"""
Quant Workbench v92.0 TDX 对齐全面验证脚本
验证36+ API端点 + 数据库 + 前端构建 + 代码真实性
"""

import requests, json, sqlite3, os, sys, time, subprocess
from datetime import datetime

BASE_URL = "http://127.0.0.1:5889"
REPORTS = []

def check_api(method, path, name, expect=200, post_data=None, check_fn=None):
    """验证单个API端点"""
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=30)
        elif method == "POST":
            r = requests.post(url, json=post_data, timeout=30)
        else:
            r = requests.request(method, url, timeout=30)
        ok = r.status_code == expect
        extra = ""
        if ok and check_fn:
            try:
                check_fn(r.json())
            except Exception as e:
                ok = False
                extra = f" check_fn fail: {e}"
        status = "OK" if ok else "FAIL"
        REPORTS.append({"name": name, "status": status, "code": r.status_code, "extra": extra})
        return ok
    except Exception as e:
        REPORTS.append({"name": name, "status": "FAIL", "code": str(e), "extra": ""})
        return False

# 基础
ok1 = check_api("GET", "/api/health", "基础健康")
ok2 = check_api("GET", "/api/v1/quote/health", "行情健康")
ok3 = check_api("GET", "/api/v1/data/health", "数据健康")

# 数据平台
ok4 = check_api("GET", "/api/v1/data/overview", "数据概览")
ok5 = check_api("GET", "/api/v1/data/diagnose/000001", "数据诊断")
ok6 = check_api("GET", "/api/v1/data/quality", "数据质量")
ok7 = check_api("GET", "/api/v1/data/compare?symbol=000001", "数据比对")

# 行情K线多周期
ok8 = check_api("GET", "/api/v1/quote/000001/ohlcv?period=daily", "日线K线")
ok9 = check_api("GET", "/api/v1/quote/000001/ohlcv?period=1m", "1分钟K线")
ok10 = check_api("GET", "/api/v1/quote/000001/ohlcv?period=5m", "5分钟K线")
ok11 = check_api("GET", "/api/v1/quote/000001/ohlcv?period=15m", "15分钟K线")
ok12 = check_api("GET", "/api/v1/quote/000001/ohlcv?period=30m", "30分钟K线")
ok13 = check_api("GET", "/api/v1/quote/000001/ohlcv?period=60m", "60分钟K线")
ok14 = check_api("GET", "/api/v1/quote/000001/ohlcv?period=weekly", "周线K线")
ok15 = check_api("GET", "/api/v1/quote/000001/ohlcv?period=monthly", "月线K线")

# 行情分析
ok16 = check_api("GET", "/api/v1/quote/000001/indicators", "技术指标")
ok17 = check_api("GET", "/api/v1/quote/000001/signal", "信号")
ok18 = check_api("GET", "/api/v1/quote/000001/resonance", "共振")
ok19 = check_api("GET", "/api/v1/quote/000001/patterns", "形态")
ok20 = check_api("GET", "/api/v1/quote/000001/volume-analysis", "量价分析")
ok21 = check_api("GET", "/api/v1/quote/000001/support-resistance", "支撑阻力")

# 行情增强
ok22 = check_api("GET", "/api/v1/quote/000001/intraday", "分时图")
ok23 = check_api("GET", "/api/v1/quote/000001/profile", "F10资料")
ok24 = check_api("GET", "/api/v1/quote/000001/orderbook", "五档行情")

# 市场
ok25 = check_api("GET", "/api/v1/market/overview", "大盘概览")
ok26 = check_api("GET", "/api/v1/market/sectors", "板块列表")
ok27 = check_api("GET", "/api/v1/market/sector/%E9%A3%9F%E5%93%81%E9%A5%AE%E6%96%99", "板块详情")
ok28 = check_api("GET", "/api/v1/market/index/sh000001", "指数K线")

# 自选股
ok29 = check_api("GET", "/api/v1/watchlist", "自选股")
ok30 = check_api("GET", "/api/v1/watchlist/with-quotes", "自选股含报价")
ok31 = check_api("GET", "/api/v1/watchlist/groups", "分组管理")

# 信号/回测
ok32 = check_api("GET", "/api/v1/signals", "信号列表")
ok33 = check_api("GET", "/api/v1/signals/performance", "信号绩效")
ok34 = check_api("GET", "/api/v1/backtest/strategies", "策略")
ok35 = check_api("GET", "/api/v1/backtest/results", "回测结果")

# 设置
ok36 = check_api("GET", "/api/v1/settings", "设置")

# 扫描
ok37 = check_api("POST", "/api/v1/quote/scan/resonance", "批量扫描", post_data={"symbols": ["000001", "600519", "000858"]})

# 打印汇总
passed = sum(1 for r in REPORTS if r["status"] == "OK")
total = len(REPORTS)
print(f"\n{'='*60}")
print(f"API 验证结果: {passed}/{total} 通过")
print(f"{'='*60}")
for r in REPORTS:
    print(f"[{r['status']}] {r['name']} ({r['code']}){r['extra']}")

# 数据库检查
db_path = os.path.join(os.path.dirname(__file__), "data", "backend", "quant_workbench.db")
print(f"\n{'='*60}")
print(f"数据库检查: {db_path}")
print(f"{'='*60}")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"表列表: {tables}")
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            count = cursor.fetchone()[0]
            print(f"  {t}: {count} 行")
        except Exception as e:
            print(f"  {t}: 查询失败 {e}")
    cursor.execute("PRAGMA journal_mode")
    jm = cursor.fetchone()[0]
    print(f"journal_mode: {jm}")
    if 'realtime_kline_cache' in tables:
        cursor.execute("SELECT MAX(date) FROM realtime_kline_cache")
        max_date = cursor.fetchone()[0]
        print(f"realtime_kline_cache 最新日期: {max_date}")
    if 'signals' in tables:
        cursor.execute("SELECT COUNT(*) FROM signals WHERE status='open'")
        open_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM signals WHERE status='closed'")
        closed_count = cursor.fetchone()[0]
        print(f"signals: open={open_count}, closed={closed_count}")
        # 检查列数
        cursor.execute("PRAGMA table_info(signals)")
        cols = [c[1] for c in cursor.fetchall()]
        print(f"signals 列数: {len(cols)} (期望19)")
    conn.close()
else:
    print(f"数据库不存在: {db_path}")

# 前端构建检查
print(f"\n{'='*60}")
print(f"前端构建检查")
print(f"{'='*60}")
dist_dir = os.path.join(os.path.dirname(__file__), "frontend_react", "dist", "assets")
if os.path.exists(dist_dir):
    for f in os.listdir(dist_dir):
        if f.endswith(".js"):
            size = os.path.getsize(os.path.join(dist_dir, f))
            print(f"  {f}: {size/1024:.1f} KB")
else:
    print(f"dist目录不存在: {dist_dir}")

# 输出JSON汇总
result = {
    "timestamp": datetime.now().isoformat(),
    "passed": passed,
    "total": total,
    "details": REPORTS,
    "db_path": db_path if os.path.exists(db_path) else None,
    "tables": tables if os.path.exists(db_path) else [],
}
with open("tdx_check_results_now.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存到 tdx_check_results_now.json")
