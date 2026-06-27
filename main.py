#!/usr/bin/env python3
"""
A股动量趋势交易系统 v3.0 - Harness Engineering 编排入口

架构：
1. Core: harness.py (Runner + Context + Registry + Pipeline)
2. Harnesses: 6个业务模块（data_fetcher / pattern_recognition / sector_calculation / traffic_light / report_generator / backtest）
3. 模式：post_market / pre_market / backtest / deviation

Usage:
    python main.py --mode post_market --date 20250619
    python main.py --mode pre_market --date 20250619
    python main.py --mode backtest --date 20250619
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.harness import (
    Registry, Runner, Context, RunMode, ErrorPolicy,
    build_post_market_pipeline, build_pre_market_pipeline,
    build_backtest_pipeline, build_deviation_pipeline,
)

# 注册所有 Harness
from harnesses.data_fetcher_harness import DataFetcherHarness
from harnesses.pattern_recognition_harness import PatternRecognitionHarness
from harnesses.sector_calculation_harness import SectorCalculationHarness
from harnesses.traffic_light_harness import TrafficLightHarness
from harnesses.report_generator_harness import ReportGeneratorHarness
from harnesses.backtest_harness import BacktestHarness

Registry.register("data_fetcher", DataFetcherHarness)
Registry.register("pattern_recognition", PatternRecognitionHarness)
Registry.register("sector_calculation", SectorCalculationHarness)
Registry.register("traffic_light", TrafficLightHarness)
Registry.register("report_generator", ReportGeneratorHarness)
Registry.register("backtest", BacktestHarness)


def run_post_market(date_str: str, codes: list = None):
    """盘后全自动流水线"""
    print(f"\n{'='*60}")
    print(f"A股动量趋势系统 v3.0 - 盘后执行 (Harness)")
    print(f"Date: {date_str}")
    print(f"Registered harnesses: {Registry.list()}")
    print(f"{'='*60}\n")
    
    pipeline = build_post_market_pipeline()
    runner = Runner(pipeline)
    
    ctx = Context(mode=RunMode.POST_MARKET, date=date_str)
    ctx.set("date", date_str)
    
    # 通过 Runner 配置传递参数
    for step in pipeline.get_enabled_steps():
        if step.name == "data_fetcher" and codes:
            step.params["codes"] = codes
    
    result = runner.run(ctx)
    
    print(f"\n{'='*60}")
    print(f"Pipeline: {result['success']}")
    print(f"Steps: {result['completed_steps']}/{result['total_steps']}")
    print(f"Context keys: {result['context_keys']}")
    print(f"{'='*60}\n")
    
    # 打印每个 Harness 的执行结果
    for r in result["results"]:
        status = "✅" if r["success"] else "❌"
        print(f"  {status} {r['name']}: {r['duration_ms']}ms")
        if r["error"]:
            print(f"     ERROR: {r['error']}")
    
    # 输出关键结果
    report_path = ctx.get("reports.post_market")
    csv_path = ctx.get("reports.position_csv")
    regime = ctx.get("market_regime")
    trend_pool = ctx.get("traffic_light.trend_pool", [])
    
    print(f"\n  市场状态: {regime}")
    print(f"  趋势池: {len(trend_pool)} 只")
    print(f"  盘后报告: {report_path}")
    print(f"  持仓CSV: {csv_path}")
    
    return result


def run_pre_market(date_str: str):
    """盘前快速流水线"""
    print(f"\n{'='*60}")
    print(f"A股动量趋势系统 v3.0 - 盘前执行 (Harness)")
    print(f"Date: {date_str}")
    print(f"{'='*60}\n")
    
    pipeline = build_pre_market_pipeline()
    runner = Runner(pipeline)
    
    ctx = Context(mode=RunMode.PRE_MARKET, date=date_str)
    ctx.set("date", date_str)
    
    result = runner.run(ctx)
    
    print(f"\nPipeline: {result['success']}")
    print(f"Steps: {result['completed_steps']}/{result['total_steps']}")
    
    return result


def run_backtest(date_str: str):
    """回测流水线"""
    print(f"\n{'='*60}")
    print(f"A股动量趋势系统 v3.0 - 回测执行 (Harness)")
    print(f"Date: {date_str}")
    print(f"{'='*60}\n")
    
    pipeline = build_backtest_pipeline()
    runner = Runner(pipeline)
    
    ctx = Context(mode=RunMode.BACKTEST, date=date_str)
    ctx.set("date", date_str)
    
    result = runner.run(ctx)
    
    print(f"\nPipeline: {result['success']}")
    print(f"Steps: {result['completed_steps']}/{result['total_steps']}")
    
    backtest_summary = ctx.get("backtest.summary")
    if backtest_summary:
        print(f"\n  回测结果: {backtest_summary}")
    
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A股动量趋势交易系统 v5.0 (Harness)")
    parser.add_argument("--mode", type=str, choices=["post_market", "pre_market", "backtest", "dashboard", "event_engine", "trigger", "all"], default="post_market")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y%m%d"), help="YYYYMMDD")
    parser.add_argument("--codes", type=str, default="", help="逗号分隔的股票代码列表")
    parser.add_argument("--event", type=str, default="", help="事件类型（用于 trigger 模式）")
    parser.add_argument("--payload", type=str, default="", help="事件载荷JSON（用于 trigger 模式）")
    
    args = parser.parse_args()
    
    codes = args.codes.split(",") if args.codes else None
    
    if args.mode == "post_market":
        run_post_market(args.date, codes)
    elif args.mode == "pre_market":
        run_pre_market(args.date)
    elif args.mode == "backtest":
        run_backtest(args.date)
    elif args.mode == "dashboard":
        # 启动实时看板
        from dashboard.app import main as dashboard_main
        dashboard_main()
    elif args.mode == "event_engine":
        # 启动事件引擎
        from events.scheduler import EventScheduler
        scheduler = EventScheduler()
        scheduler.run_forever()
    elif args.mode == "trigger":
        # 手动触发事件
        import json
        from events.scheduler import EventScheduler
        scheduler = EventScheduler()
        payload = json.loads(args.payload) if args.payload else {}
        scheduler.trigger_event(args.event or "market_post_close", payload)

    elif args.mode == "all":
        # 同时启动看板 + 事件引擎
        import threading
        from events.scheduler import EventScheduler
        from dashboard.app import create_app
        
        print("\n" + "="*50)
        print("A股动量趋势系统 v5.0 - 并行模式")
        print("="*50)
        
        # 启动事件引擎（后台线程）
        scheduler = EventScheduler()
        scheduler.start()
        print("✅ 事件引擎已启动")
        
        # 启动看板（主线程）
        app = create_app()
        print("✅ 看板服务已启动")
        print("访问地址: http://127.0.0.1:5888")
        print("按 Ctrl+C 停止所有服务")
        print("="*50 + "\n")
        
        try:
            app.run(host='127.0.0.1', port=5888, debug=False, threaded=True)
        except KeyboardInterrupt:
            print("\n正在停止所有服务...")
        finally:
            scheduler.stop()
            scheduler._bus.shutdown()
            print("所有服务已停止")
