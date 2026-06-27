#!/usr/bin/env python3
"""
A股动量趋势系统 v4.0 - 盘后流水线执行脚本
整合：Pipeline 编排 + Observability + Resilience + SQLite + LLM 增强 + 盘后简报
"""

import sys
import os
import time
import json
from datetime import datetime

# 确保路径正确
sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")

from core.harness import (
    Registry, Runner, Context, RunMode, ErrorPolicy,
    HarnessConfig, Pipeline, PreRunHook, PostRunHook,
)
from core.observability import ObservabilityEngine, get_obs
from core.persistence import PersistenceEngine
from core.resilience import get_resilience
from core.llm_agent import LLMAnalyzer

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


class ObservabilityPreHook(PreRunHook):
    """PreRun Hook: 开始 Span"""
    def __init__(self, obs: ObservabilityEngine, trace_id: str):
        self.obs = obs
        self.trace_id = trace_id
        self._spans = {}
    
    def before(self, harness_name: str, inputs: dict, ctx: Context) -> None:
        span = self.obs.start_span(self.trace_id, harness_name)
        self._spans[harness_name] = span


class ObservabilityPostHook(PostRunHook):
    """PostRun Hook: 结束 Span 并记录指标"""
    def __init__(self, obs: ObservabilityEngine, pre_hook: ObservabilityPreHook):
        self.obs = obs
        self.pre_hook = pre_hook
    
    def after(self, harness_name: str, result: dict, duration_ms: float, ctx: Context) -> None:
        span = self.pre_hook._spans.get(harness_name)
        success = ctx.harness_results and ctx.harness_results[-1].success if ctx.harness_results else True
        if span:
            self.obs.finish_span(self.pre_hook.trace_id, span, status="ok" if success else "error")
        # 记录指标
        self.obs.record_histogram("harness_latency_ms", duration_ms, {"name": harness_name})
        self.obs.record_counter("harness_runs", 1, {"name": harness_name, "status": "success" if success else "failure"})
        # 数据血缘
        for key, value in result.items():
            self.obs.record_lineage(key, harness_name, type(value).__name__)


def build_post_market_v4_pipeline() -> Pipeline:
    """v4.0 扩展盘后流水线：包含 backtest"""
    return Pipeline(
        name="post_market_v4",
        description="A股动量趋势系统 v4.0 盘后全自动执行流水线（含回测）",
        steps=[
            HarnessConfig(name="data_fetcher", error_policy=ErrorPolicy.FALLBACK, params={"days_back": 180}),
            HarnessConfig(name="pattern_recognition", error_policy=ErrorPolicy.FALLBACK, params={"min_history": 60}),
            HarnessConfig(name="sector_calculation", error_policy=ErrorPolicy.FALLBACK, params={"top_n": 30, "max_sectors": 15, "max_components": 10}),
            HarnessConfig(name="traffic_light", error_policy=ErrorPolicy.FALLBACK),
            HarnessConfig(name="backtest", error_policy=ErrorPolicy.FALLBACK, params={"initial_capital": 1000000}),
            HarnessConfig(name="report_generator", error_policy=ErrorPolicy.TERMINATE),
        ],
    )


def save_to_database(ctx: Context, run_id: str) -> dict:
    """保存所有结果到 SQLite 数据库"""
    pers = PersistenceEngine()
    date_str = ctx.date
    
    saved = {}
    
    # 1. 保存流水线执行记录
    pipeline_success = all(r.success for r in ctx.harness_results)
    pers.save_pipeline_run(
        run_id=run_id,
        date=date_str,
        mode="post_market_v4",
        pipeline_name="post_market_v4",
        success=pipeline_success,
        completed=len([r for r in ctx.harness_results if r.success]),
        total=len(ctx.harness_results),
        duration_ms=sum(r.duration_ms for r in ctx.harness_results),
        context_keys=ctx.keys(),
    )
    saved["pipeline_run"] = True
    
    # 2. 保存 Harness 指标
    for r in ctx.harness_results:
        pers.save_harness_metric(
            run_id=run_id,
            name=r.name,
            success=r.success,
            duration_ms=r.duration_ms,
            inputs=r.inputs,
            outputs=r.outputs,
            error=r.error or "",
        )
    saved["harness_metrics"] = len(ctx.harness_results)
    
    # 3. 保存型态识别结果
    all_patterns = ctx.get("all_patterns", [])
    if all_patterns:
        pers.save_patterns(all_patterns)
    saved["patterns"] = len(all_patterns)
    
    # 4. 保存板块排名
    sector_results = ctx.get("sector_results", [])
    if sector_results:
        pers.save_sector_rankings(date_str, sector_results)
    saved["sector_rankings"] = len(sector_results)
    
    # 5. 保存交通灯信号
    trend_pool = ctx.get("traffic_light.trend_pool", [])
    watch_pool = ctx.get("traffic_light.watch_pool", [])
    risk_pool = ctx.get("traffic_light.risk_pool", [])
    all_signals = []
    for t in trend_pool:
        d = t.to_dict() if hasattr(t, "to_dict") else t
        d["category"] = "趋势池"
        all_signals.append(d)
    for t in watch_pool:
        d = t.to_dict() if hasattr(t, "to_dict") else t
        d["category"] = "观察池"
        all_signals.append(d)
    for t in risk_pool:
        d = t.to_dict() if hasattr(t, "to_dict") else t
        d["category"] = "风险池"
        all_signals.append(d)
    if all_signals:
        pers.save_traffic_signals(date_str, all_signals)
    saved["traffic_signals"] = len(all_signals)
    
    return saved


def llm_enhance_patterns(ctx: Context) -> dict:
    """使用 LLMAnalyzer 对 Top 型态进行智能增强分析"""
    stock_data = ctx.get("stock_data", {})
    patterns_map = ctx.get("patterns", {})
    
    if not stock_data or not patterns_map:
        return {"llm_used": False, "error": "No data"}
    
    analyzer = LLMAnalyzer()
    
    # 收集所有型态，按置信度排序取 Top 10
    all_p = []
    for code, p_list in patterns_map.items():
        for p in p_list:
            all_p.append((code, p))
    all_p.sort(key=lambda x: x[1].confidence if hasattr(x[1], "confidence") else 0, reverse=True)
    top_codes = list(dict.fromkeys([code for code, _ in all_p[:10]]))  # 去重，保留顺序
    
    results = {}
    for code in top_codes[:5]:  # 取 Top 5 股票做 LLM 分析（控制成本）
        df = stock_data.get(code)
        if df is not None and len(df) >= 20:
            try:
                signal = analyzer.analyze_stock(code, df)
                results[code] = signal.to_dict()
            except Exception as e:
                results[code] = {"error": str(e)}
    
    return {"llm_used": True, "top_signals": results, "count": len(results)}


def generate_post_market_brief(ctx: Context, run_id: str, db_stats: dict, llm_stats: dict) -> str:
    """生成盘后简报 Markdown"""
    date_str = ctx.date
    obs = get_obs()
    
    # 获取市场状态
    market_regime = ctx.get("market_regime", "未知")
    
    # 获取板块 Top 5
    sector_results = ctx.get("sector_results", [])
    top_sectors = sector_results[:5] if sector_results else []
    
    # 获取型态 Top 5
    all_patterns = ctx.get("all_patterns", [])
    top_patterns = sorted(all_patterns, key=lambda x: x.get("confidence", 0), reverse=True)[:5] if all_patterns else []
    
    # 获取交通灯
    trend_pool = ctx.get("traffic_light.trend_pool", [])
    watch_pool = ctx.get("traffic_light.watch_pool", [])
    risk_pool = ctx.get("traffic_light.risk_pool", [])
    
    # 获取 Observability 统计
    harness_stats = obs.get_all_harness_stats()
    
    # 获取回测摘要
    backtest_summary = ctx.get("backtest.summary", {})
    
    # 生成简报
    brief = f"""# 📊 A股动量趋势系统 v4.0 — 盘后简报

**日期**: {date_str}  
**执行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Run ID**: {run_id}

---

## 一、市场状态

- **市场状态**: {market_regime}
- **趋势池**: {len(trend_pool)} 只
- **观察池**: {len(watch_pool)} 只
- **风险池**: {len(risk_pool)} 只

---

## 二、板块热点（Top 5）

"""
    for s in top_sectors:
        d = s.to_dict() if hasattr(s, "to_dict") else s
        brief += f"- **{d.get('sector_name', '-')}** | 生命周期: {d.get('lifecycle', '-')} | 20日涨幅: {d.get('return_20d', 0)*100:.1f}% | 建议: {d.get('recommendation', '-')}\n"
    
    brief += f"""
---

## 三、Top 型态

"""
    for p in top_patterns:
        brief += f"- **{p.get('code', '-')}** | {p.get('pattern_type', '-')} | 置信度: {p.get('confidence', 0):.2f} | 状态: {p.get('status', '-')}\n"
    
    if llm_stats.get("llm_used"):
        brief += f"\n> 🤖 LLM 智能分析: 已对 Top {llm_stats.get('count', 0)} 只股票进行增强分析\n"
    
    brief += f"""
---

## 四、流水线执行指标

| Harness | 耗时(ms) | 状态 | 输出 |
|---------|---------|------|------|
"""
    for r in ctx.harness_results:
        status = "[OK]" if r.success else "[WARN]降级" if not r.error else "[FAIL]"
        outputs = ", ".join(r.outputs.keys())[:30]
        brief += f"| {r.name} | {r.duration_ms:.0f} | {status} | {outputs} |\n"
    
    brief += f"""
---

## 五、数据库保存状态

| 表名 | 保存数量 |
|------|---------|
| pipeline_runs | 1 |
| harness_metrics | {db_stats.get('harness_metrics', 0)} |
| patterns | {db_stats.get('patterns', 0)} |
| sector_rankings | {db_stats.get('sector_rankings', 0)} |
| traffic_signals | {db_stats.get('traffic_signals', 0)} |

---

## 六、回测绩效

"""
    if backtest_summary and not backtest_summary.get("error"):
        for k, v in backtest_summary.items():
            if isinstance(v, (int, float, str)):
                brief += f"- {k}: {v}\n"
    else:
        brief += "- 回测状态: 今日为简化回测（单日信号快照），历史回测需完整序列数据\n"
    
    brief += f"""
---

## 七、明日执行清单

- [ ] 09:15 运行盘前扫描脚本
- [ ] 09:20 确认集合竞价过滤结果
- [ ] 09:25 开盘八法判定
- [ ] 09:30-10:00 观察60分钟买点触发
- [ ] 14:30 确认无尾盘新开仓
- [ ] 15:00 收盘后运行盘后脚本

---

> 本简报由 A股动量趋势交易系统 v4.0 自动生成
> Resilience 状态: {get_resilience().get_health_status()}
"""
    
    # 保存文件
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"盘后简报_{date_str}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(brief)
    
    return filepath


def main():
    date_str = datetime.now().strftime("%Y%m%d")
    run_id = f"pm-{date_str}-{int(time.time())}"
    
    print(f"\n{'='*70}")
    print(f"A股动量趋势系统 v4.0 - 盘后流水线执行")
    print(f"Date: {date_str} | Run ID: {run_id}")
    print(f"{'='*70}\n")
    
    # 初始化 Observability
    obs = get_obs()
    obs.reset()
    trace = obs.start_trace(run_id, "post_market_v4")
    
    # 构建流水线
    pipeline = build_post_market_v4_pipeline()
    pre_hook = ObservabilityPreHook(obs, run_id)
    post_hook = ObservabilityPostHook(obs, pre_hook)
    runner = Runner(pipeline, pre_hooks=[pre_hook], post_hooks=[post_hook])
    
    # 执行上下文
    ctx = Context(mode=RunMode.POST_MARKET, date=date_str)
    ctx.set("date", date_str)
    
    # 执行流水线
    pipeline_start = time.time()
    result = runner.run(ctx)
    pipeline_duration_ms = (time.time() - pipeline_start) * 1000
    
    # 完成链路追踪
    obs.finish_trace(run_id, status="ok" if result["success"] else "error")
    
    # 输出执行结果
    print(f"\n{'='*70}")
    print(f"Pipeline: {'[OK] 成功' if result['success'] else '[WARN] 部分成功'}")
    print(f"Steps: {result['completed_steps']}/{result['total_steps']}")
    print(f"Duration: {pipeline_duration_ms:.0f}ms")
    print(f"{'='*70}\n")
    
    for r in result["results"]:
        status = "[OK]" if r["success"] else "[FAIL]"
        print(f"  {status} {r['name']}: {r['duration_ms']:.0f}ms")
        if r.get("error"):
            print(f"     ERROR: {r['error']}")
    
    # LLM 增强分析
    print(f"\n{'='*70}")
    print("LLM 智能分析启动...")
    llm_stats = llm_enhance_patterns(ctx)
    print(f"LLM 分析完成: {llm_stats}")
    
    # 保存到数据库
    print(f"\n{'='*70}")
    print("保存结果到 SQLite 数据库...")
    db_stats = save_to_database(ctx, run_id)
    print(f"数据库保存完成: {db_stats}")
    
    # 生成盘后简报
    print(f"\n{'='*70}")
    print("生成盘后简报...")
    brief_path = generate_post_market_brief(ctx, run_id, db_stats, llm_stats)
    print(f"盘后简报已保存: {brief_path}")
    
    # 输出关键指标摘要
    print(f"\n{'='*70}")
    print("关键指标摘要")
    print(f"{'='*70}")
    print(f"  市场状态: {ctx.get('market_regime', '未知')}")
    print(f"  趋势池: {len(ctx.get('traffic_light.trend_pool', []))} 只")
    print(f"  观察池: {len(ctx.get('traffic_light.watch_pool', []))} 只")
    print(f"  风险池: {len(ctx.get('traffic_light.risk_pool', []))} 只")
    print(f"  型态总数: {len(ctx.get('all_patterns', []))}")
    print(f"  板块排名: {len(ctx.get('sector_results', []))}")
    print(f"  盘后报告: {ctx.get('reports.post_market', 'N/A')}")
    print(f"  持仓CSV: {ctx.get('reports.position_csv', 'N/A')}")
    print(f"  简报文件: {brief_path}")
    print(f"  数据库: data/system.db")
    
    # Observability 统计
    print(f"\n{'='*70}")
    print("Observability 统计")
    print(f"{'='*70}")
    for stat in obs.get_all_harness_stats():
        print(f"  {stat['name']}: avg_latency={stat.get('avg_latency_ms', 'N/A')}ms, success_rate={stat.get('success_rate', 'N/A')}")
    
    print(f"\n{'='*70}")
    print("A股动量趋势系统 v4.0 - 盘后流水线执行完成")
    print(f"{'='*70}\n")
    
    return {
        "run_id": run_id,
        "success": result["success"],
        "pipeline_duration_ms": pipeline_duration_ms,
        "ctx": ctx,
        "brief_path": brief_path,
        "db_stats": db_stats,
        "llm_stats": llm_stats,
    }


if __name__ == "__main__":
    main()
