#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quant Workbench 每小时自主迭代循环

1. 自动确保 Windows 定时任务已注册
2. 读取 reports/selfcheck/ 下最新的系统自检报告
3. 同时识别 reports/ux/ 下最新的 UX 检查报告
4. 触发 iterate_agent.py 按 P0/P1/P2 优先级执行自主迭代

注：本脚本不再生成新的自检报告，只消费已有报告。
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reports.iterate_agent import run_iteration, _find_latest_report

BASE_URL = "http://127.0.0.1:5889"
REPORT_DIR = PROJECT_ROOT / "reports" / "selfcheck"

ENDPOINTS = [
    {"name": "health", "path": "/api/health", "group": "基础健康"},
    {"name": "quote_health", "path": "/api/v1/quote/health", "group": "数据平台"},
    {"name": "data_health", "path": "/api/v1/data/health", "group": "数据平台"},
    {"name": "data_overview", "path": "/api/v1/data/overview", "group": "数据平台"},
    {"name": "ohlcv", "path": "/api/v1/quote/000001/ohlcv?period=daily&limit=5", "group": "行情数据"},
    {"name": "indicators", "path": "/api/v1/quote/000001/indicators?period=daily&limit=120", "group": "行情数据"},
    {"name": "signal", "path": "/api/v1/quote/000001/signal", "group": "行情数据"},
    {"name": "patterns", "path": "/api/v1/quote/000001/patterns?period=daily", "group": "行情数据"},
    {"name": "volume", "path": "/api/v1/quote/000001/volume-analysis?period=daily", "group": "行情数据"},
    {"name": "support_resistance", "path": "/api/v1/quote/000001/support-resistance?period=daily", "group": "行情数据"},
    {"name": "resonance", "path": "/api/v1/quote/000001/resonance", "group": "行情数据"},
    {"name": "market_overview", "path": "/api/v1/market/overview", "group": "大盘数据"},
    {"name": "watchlist", "path": "/api/v1/watchlist/with-quotes", "group": "自选股"},
    {"name": "signals", "path": "/api/v1/signals?limit=5", "group": "信号系统"},
    {"name": "backtest_strategies", "path": "/api/v1/backtest/strategies", "group": "回测系统"},
]


def _call_api(path: str, timeout: int = 15) -> dict:
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                data = json.loads(body)
            except Exception:
                data = {"raw": body[:500]}
            return {"ok": True, "status": resp.status, "data": data}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": str(e.reason)}
    except Exception as e:
        return {"ok": False, "status": -1, "error": str(e)}


def _find_backend_pid() -> int:
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if ":5889" in line and "LISTENING" in line:
                m = re.search(r"LISTENING\s+(\d+)", line)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return 0


def _check_frontend_dist() -> Tuple[bool, str]:
    index_html = PROJECT_ROOT / "frontend_react" / "dist" / "index.html"
    assets_dir = PROJECT_ROOT / "frontend_react" / "dist" / "assets"
    if not index_html.exists():
        return False, "dist/index.html 不存在"
    if not assets_dir.exists():
        return False, "dist/assets 不存在"
    mtime = datetime.fromtimestamp(index_html.stat().st_mtime)
    return True, f"存在，最新于 {mtime.strftime('%Y-%m-%d %H:%M')}"


def _validate_ohlcv(result: dict) -> List[str]:
    issues = []
    if not result["ok"]:
        issues.append(f"HTTP {result['status']}: {result.get('error')}")
        return issues
    data = result.get("data", {}).get("data", [])
    if not data:
        issues.append("OHLCV 数据为空")
        return issues
    last = data[0]
    close = last.get("close", 0)
    volume = last.get("volume", 0)
    date_str = str(last.get("date", ""))
    if close <= 0:
        issues.append(f"close 异常: {close}")
    if volume <= 0:
        issues.append(f"volume 异常: {volume}")
    if len(date_str) == 8:
        try:
            d = datetime.strptime(date_str, "%Y%m%d")
            delta = (datetime.now() - d).days
            if delta > 5:
                issues.append(f"数据滞后 {delta} 天")
        except Exception:
            issues.append(f"日期格式异常: {date_str}")
    if "is_filled" not in last:
        issues.append("OHLCV 返回缺少 is_filled 字段，建议启用非交易日填充标记")
    return issues


def _validate_signal(result: dict) -> List[str]:
    issues = []
    if not result["ok"]:
        issues.append(f"HTTP {result['status']}: {result.get('error')}")
        return issues
    sig = result.get("data", {})
    stype = sig.get("type", "")
    entry = sig.get("entry_price", 0)
    sl = sig.get("stop_loss", 0)
    if stype == "BUY" and sl >= entry:
        issues.append(f"BUY 信号止损价 {sl} 不低于入场价 {entry}")
    if stype == "SELL" and sl <= entry:
        issues.append(f"SELL 信号止损价 {sl} 不高于入场价 {entry}")
    return issues


def _validate_market_overview(result: dict) -> List[str]:
    issues = []
    if not result["ok"]:
        issues.append(f"HTTP {result['status']}: {result.get('error')}")
        return issues
    indices = result.get("data", {}).get("indices", [])
    if not indices:
        issues.append("大盘指数为空")
        return issues
    sh = indices[0]
    if sh.get("close", 0) <= 0:
        issues.append("上证指数 close 异常")
    if sh.get("volume", 0) <= 0:
        issues.append("上证指数 volume 异常")
    return issues


def _run_selfcheck() -> dict:
    # 对齐到当前小时的整点，作为本次报告的“计划时间”
    scheduled_time = datetime.now().replace(minute=0, second=0, microsecond=0)
    pid = _find_backend_pid()
    backend_alive = pid > 0

    api_results = {}
    issues_by_endpoint = {}
    all_issues = []

    for ep in ENDPOINTS:
        name = ep["name"]
        res = _call_api(ep["path"])
        api_results[name] = res
        endpoint_issues = []
        if not res["ok"]:
            endpoint_issues.append(f"HTTP {res['status']}: {res.get('error')}")
        elif name == "ohlcv":
            endpoint_issues = _validate_ohlcv(res)
        elif name == "signal":
            endpoint_issues = _validate_signal(res)
        elif name == "market_overview":
            endpoint_issues = _validate_market_overview(res)
        issues_by_endpoint[name] = endpoint_issues
        all_issues.extend(endpoint_issues)

    dist_ok, dist_msg = _check_frontend_dist()
    if not dist_ok:
        all_issues.append(f"前端构建异常: {dist_msg}")

    # 数据时效性：最新日期
    latest_date = ""
    if api_results.get("ohlcv", {}).get("ok"):
        rows = api_results["ohlcv"].get("data", {}).get("data", [])
        if rows:
            latest_date = str(rows[0].get("date", ""))

    return {
        "timestamp": datetime.now().isoformat(),
        "scheduled_time": scheduled_time.isoformat(),
        "backend_alive": backend_alive,
        "backend_pid": pid,
        "api_results": api_results,
        "issues_by_endpoint": issues_by_endpoint,
        "all_issues": all_issues,
        "frontend_dist_ok": dist_ok,
        "frontend_dist_msg": dist_msg,
        "latest_date": latest_date,
    }


def _write_report(summary: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    scheduled = datetime.fromisoformat(summary["scheduled_time"])
    filename = f"SYSTEM_LOOP_CHECK_REPORT_{scheduled.strftime('%Y-%m-%d_%H%M')}.md"
    path = REPORT_DIR / filename

    lines = [
        "=== 系统循环排查报告 ===",
        f"计划时间：{scheduled.isoformat()}",
        f"实际生成时间：{now.isoformat()}",
        f"本次迭代：v2.0 系统循环排查",
        "",
        "【后端状态】",
        f"- 进程：{'存活' if summary['backend_alive'] else '未运行'} (PID: {summary['backend_pid']})",
        f"- 最新数据日期：{summary['latest_date']}",
        "",
        "【API 可用性】",
    ]
    for ep in ENDPOINTS:
        name = ep["name"]
        res = summary["api_results"].get(name, {})
        status = "200 OK" if res.get("ok") else f"{res.get('status')} {res.get('error', '')}".strip()
        lines.append(f"- {name}: {status}")
    lines.append("")

    lines.append("【发现的问题】")
    if summary["all_issues"]:
        for idx, issue in enumerate(summary["all_issues"], 1):
            lines.append(f"{idx}. ⚠️ {issue}")
    else:
        lines.append("1. 无（本次排查未发现问题）")
    lines.append("")

    lines.append("【前端构建】")
    lines.append(f"- 构建产物：{summary['frontend_dist_msg']}")
    lines.append("")

    lines.append("【优化建议】")
    if summary["all_issues"]:
        lines.append("1. 根据上述问题，由 iterate_agent 自主判断并修复低风险项")
    else:
        lines.append("1. 继续保持监控")
    lines.append("")

    lines.append("【下一步】")
    lines.append("- 等待 iterate_agent 处理本次排查发现的问题")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _pid_exists(pid: int) -> bool:
    """检查 Windows 上某 PID 是否仍在运行"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def _acquire_lock() -> bool:
    """获取单例锁，防止上一轮还没跑完就启动新一轮"""
    lock_dir = PROJECT_ROOT / "data" / "backend"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / "selfcheck_loop.lock"
    try:
        if lock_file.exists():
            try:
                old_pid = int(lock_file.read_text(encoding="utf-8").strip())
                if old_pid != os.getpid() and _pid_exists(old_pid):
                    return False
            except Exception:
                pass
        lock_file.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[WARN] 无法获取锁: {e}")
        return False


def _release_lock() -> None:
    lock_file = PROJECT_ROOT / "data" / "backend" / "selfcheck_loop.lock"
    try:
        if lock_file.exists() and lock_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lock_file.unlink()
    except Exception:
        pass


def _install_scheduler() -> bool:
    """自动注册 Windows 每小时自检任务；失败时启动看门狗兜底"""
    task_name = "QuantWorkbench-SelfCheckLoop"
    python_exe = r"C:\Users\江厉害\AppData\Local\Programs\Python\Python312\python.exe"
    script_path = str(PROJECT_ROOT / "scripts" / "selfcheck_loop.py")
    task_cmd = f'"{python_exe}" "{script_path}"'

    # 先查询任务是否已存在
    query = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if query.returncode == 0:
        return True

    create = subprocess.run(
        ["schtasks", "/Create", "/SC", "HOURLY", "/TN", task_name, "/TR", task_cmd, "/ST", "00:00", "/F"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if create.returncode == 0:
        return True

    # Task Scheduler 失败，启动本地守护进程兜底（仅启动一次）
    if os.environ.get("_QW_DAEMON") != "1":
        print("[WARN] Task Scheduler 注册失败，启动本地看门狗兜底")
        try:
            watchdog_path = str(PROJECT_ROOT / "scripts" / "scheduler_watchdog.py")
            subprocess.Popen(
                [python_exe, watchdog_path],
                cwd=PROJECT_ROOT,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except Exception as e:
            print(f"[ERROR] 启动看门狗失败: {e}")
    return False


def main():
    if not _acquire_lock():
        print("[INFO] 上一轮迭代尚未结束，本次跳过")
        return

    try:
        print(f"=== 自主迭代循环开始 ({datetime.now().isoformat()}) ===")

        # 每次启动时自动确保定时任务已注册
        if _install_scheduler():
            print("[INFO] 定时任务已确认注册")
        else:
            print("[WARN] 定时任务注册失败，将依赖本次进程/看门狗继续迭代")

        # 只读取已有检查报告，不重新生成
        system_report_dirs = [PROJECT_ROOT / "reports" / "selfcheck"]
        system_latest = _find_latest_report(system_report_dirs)
        reports_to_iterate: List[Path] = []
        if system_latest is not None:
            reports_to_iterate.append(system_latest[0])
            print(f"[INFO] 识别到系统自检报告: {system_latest[0].name}")
        else:
            print("[WARN] 未找到系统自检报告")

        # 同时识别 reports/ux/ 下的最新 UX 检查报告
        ux_report_dirs = [PROJECT_ROOT / "reports" / "ux"]
        ux_latest = _find_latest_report(ux_report_dirs)
        if ux_latest is not None:
            ux_path, ux_time = ux_latest
            reports_to_iterate.append(ux_path)
            print(f"[INFO] 识别到 UX 报告: {ux_path.name}")
        else:
            print("[INFO] 未找到 UX 报告")

        if not reports_to_iterate:
            print("[WARN] 未找到任何可用的检查报告，跳过本次迭代")
            return

        print("[INFO] 触发自主迭代代理...")
        iteration_path = run_iteration(reports_to_iterate)
        print(f"[INFO] 迭代报告: {iteration_path}")
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
