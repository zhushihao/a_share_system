"""
报告生成模块 - 盘后策略报告 + 盘前过滤报告 + 执行偏差报告
"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

from data.pattern_recognition import Pattern
from data.sector_calculation import SectorResult
from strategy.traffic_light import TrafficLightResult


class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, output_dir: str = None):
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate_post_market_report(
        self,
        date: str,
        market_regime: str,
        total_position_limit: float,
        actual_position: float,
        sector_results: List[SectorResult],
        trend_pool: List[TrafficLightResult],
        watch_pool: List[TrafficLightResult],
        risk_pool: List[TrafficLightResult],
        position_signals: List[TrafficLightResult],
        invalidation_signals: List[str],
    ) -> str:
        """
        生成盘后策略报告
        返回: 报告文件路径
        """
        report = f"""# A股动量趋势系统 — 盘后策略报告

日期：{date}
市场状态：{market_regime}
总仓位上限：{total_position_limit*100:.0f}%
当前实际仓位：{actual_position*100:.0f}%

---

## 一、市场状态判定

| 指标 | 数值 | 判定 |
|------|------|------|
| 市场状态 | {market_regime} | - |
| 总仓位上限 | {total_position_limit*100:.0f}% | - |
| 当前实际仓位 | {actual_position*100:.0f}% | {'需减仓' if actual_position > total_position_limit else '正常'} |

## 二、板块动量排名（前10）

| 排名 | 板块 | 生命周期 | 20日涨幅 | 新高股占比 | 成交额变化 | 机构参与度 | 风格 | 建议 |
|------|------|---------|---------|-----------|-----------|-----------|------|------|
"""
        for s in sector_results[:10]:
            report += f"| {s.rank} | {s.sector_name} | {s.lifecycle} | {s.return_20d*100:.1f}% | {s.new_high_ratio*100:.1f}% | {s.volume_change*100:.1f}% | {s.institutional_ratio*100:.1f}% | {s.style} | {s.recommendation} |\n"
        
        report += f"""
## 三、趋势池（可买入）

| 代码 | 名称 | 型态 | 颈线 | 满足点1 | 满足点2 | 入场价 | 止损价 | 风险率 | 建议仓位 | 买点类型 |
|------|------|------|------|---------|---------|--------|--------|--------|---------|---------|
"""
        for t in trend_pool:
            report += f"| {t.code} | {t.name} | - | - | {t.target_1 or '-'} | {t.target_2 or '-'} | {t.entry_price or '-'} | {t.stop_loss or '-'} | {t.risk_rate*100 if t.risk_rate else '-':.1f}% | {t.position_size*100 if t.position_size else '-':.1f}% | - |\n"
        
        report += f"""
## 四、观察池（跟踪）

| 代码 | 名称 | 观察原因 | 信号灯 | 建议 |
|------|------|---------|--------|------|
"""
        for w in watch_pool[:20]:
            reasons = ";".join(w.reasons[:3])
            report += f"| {w.code} | {w.name} | {reasons} | {w.signal} | {w.action} |\n"
        
        report += f"""
## 五、风险池（回避）

| 代码 | 名称 | 风险类型 | 建议 |
|------|------|---------|------|
"""
        for r in risk_pool[:20]:
            reasons = ";".join(r.reasons[:3])
            report += f"| {r.code} | {r.name} | {reasons} | {r.action} |\n"
        
        report += f"""
## 六、持仓信号灯

| 代码 | 名称 | 当前价 | 盈亏 | 信号灯 | 明日操作 |
|------|------|--------|------|--------|---------|
"""
        for p in position_signals:
            report += f"| {p.code} | {p.name} | - | - | {p.signal} | {p.action} |\n"
        
        report += f"""
## 七、失效信号清单（明日若出现则降级）

"""
        for sig in invalidation_signals:
            report += f"- [ ] {sig}\n"
        
        report += f"""
## 八、明日执行清单

- [ ] 09:15 运行盘前扫描脚本
- [ ] 09:20 确认集合竞价过滤结果
- [ ] 09:25 开盘八法判定
- [ ] 09:30-10:00 观察60分钟买点触发
- [ ] 14:30 确认无尾盘新开仓
- [ ] 15:00 收盘后运行盘后脚本

---

> 本报告由 A股动量趋势交易系统 v2.0 自动生成
> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        
        # 保存文件
        filename = f"盘后策略报告_{date}.md"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        
        return filepath
    
    def generate_pre_market_report(
        self,
        date: str,
        market_regime: str,
        filtered_trend_pool: List[TrafficLightResult],
        opening_method: str,
        opening_recommendation: str,
    ) -> str:
        """
        生成盘前过滤报告
        """
        report = f"""# 盘前过滤报告

日期：{date}
市场状态：{market_regime}

## 一、开盘八法判定

开盘组合：{opening_method}
当日预判：{opening_recommendation}

## 二、过滤后候选买点（<=3只）

| 代码 | 名称 | 入场价 | 止损价 | 满足点1 | 建议仓位 | 过滤原因 |
|------|------|--------|--------|---------|---------|---------|
"""
        for t in filtered_trend_pool[:3]:
            report += f"| {t.code} | {t.name} | {t.entry_price or '-'} | {t.stop_loss or '-'} | {t.target_1 or '-'} | {t.position_size*100 if t.position_size else '-':.1f}% | 通过过滤 |\n"
        
        report += f"""
## 三、今日禁止行为

- [ ] 禁止买入观察池标的
- [ ] 禁止在风险市开新仓
- [ ] 禁止亏损加仓
- [ ] 禁止FOMO追高>3%
- [ ] 禁止14:30后开新仓

---

> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        
        filename = f"盘前过滤报告_{date}.md"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        
        return filepath
    
    def generate_deviation_report(
        self,
        date: str,
        deviations: List[Dict],
        discipline_violations: List[str],
        corrections: List[str],
    ) -> str:
        """
        生成执行偏差报告
        """
        report = f"""# 执行偏差报告

日期：{date}

## 计划 vs 实际

| 项目 | 计划 | 实际 | 偏差 | 原因 |
|------|------|------|------|------|
"""
        for d in deviations:
            report += f"| {d.get('item', '-')} | {d.get('plan', '-')} | {d.get('actual', '-')} | {d.get('deviation', '-')} | {d.get('reason', '-')} |\n"
        
        report += f"""
## 纪律检查

"""
        for v in discipline_violations:
            report += f"- [x] {v}\n"
        
        report += f"""
## 明日修正

"""
        for c in corrections:
            report += f"- {c}\n"
        
        filename = f"执行偏差报告_{date}.md"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        
        return filepath


    def generate_position_csv(
        self,
        date: str,
        market_regime: str,
        total_position_limit: float,
        actual_position: float,
        positions: List[Dict],  # [{code, name, sector, pattern, entry_date, entry_price, stop_loss, current_price, pnl_pct, position_pct, signal, target_1, target_2, next_action, notes}]
    ) -> str:
        """
        生成持仓CSV文件（附录A格式）
        """
        import csv
        
        filename = f"持仓更新_{date}.csv"
        filepath = os.path.join(self.output_dir, filename)
        
        headers = ["日期", "代码", "名称", "板块", "型态", "入场日期", "入场价", "止损价", "当前价", "盈亏比例", "仓位比例", "信号灯", "满足点1", "满足点2", "明日操作", "备注"]
        
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for pos in positions:
                writer.writerow([
                    date,
                    pos.get("code", ""),
                    pos.get("name", ""),
                    pos.get("sector", ""),
                    pos.get("pattern", ""),
                    pos.get("entry_date", ""),
                    pos.get("entry_price", ""),
                    pos.get("stop_loss", ""),
                    pos.get("current_price", ""),
                    f"{pos.get('pnl_pct', 0)*100:.2f}%" if isinstance(pos.get('pnl_pct'), (int, float)) else pos.get('pnl_pct', ""),
                    f"{pos.get('position_pct', 0)*100:.2f}%" if isinstance(pos.get('position_pct'), (int, float)) else pos.get('position_pct', ""),
                    pos.get("signal", ""),
                    pos.get("target_1", ""),
                    pos.get("target_2", ""),
                    pos.get("next_action", ""),
                    pos.get("notes", ""),
                ])
        
        # 同时生成JSON格式
        json_path = os.path.join(self.output_dir, f"持仓更新_{date}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "date": date,
                "market_regime": market_regime,
                "total_position_limit": total_position_limit,
                "actual_position": actual_position,
                "positions": positions,
            }, f, ensure_ascii=False, indent=2)
        
        return filepath

    def generate_deviation_report(
        self,
        date: str,
        deviations: List[Dict],
        discipline_violations: List[str],
        corrections: List[str],
    ) -> str:
        """
        生成执行偏差报告
        """
        report = f"""# 执行偏差报告

日期：{date}

## 计划 vs 实际

| 项目 | 计划 | 实际 | 偏差 | 原因 |
|------|------|------|------|------|
"""
        for d in deviations:
            report += f"| {d.get('item', '-')} | {d.get('plan', '-')} | {d.get('actual', '-')} | {d.get('deviation', '-')} | {d.get('reason', '-')} |\n"
        
        report += f"""
## 纪律检查

"""
        for v in discipline_violations:
            report += f"- [x] {v}\n"
        
        report += f"""
## 情绪记录

| 指标 | 评分(1-10) | 说明 |
|------|-----------|------|
| 今日交易情绪 | - | - |
| 睡眠质量 | - | - |
| 连续盈亏天数 | - | - |

## 明日修正

"""
        for c in corrections:
            report += f"- {c}\n"
        
        report += f"""
---

> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        
        filename = f"执行偏差报告_{date}.md"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        
        return filepath


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")
    
    gen = ReportGenerator()
    
    # 测试生成报告
    filepath = gen.generate_post_market_report(
        date="20250619",
        market_regime="结构性趋势",
        total_position_limit=0.50,
        actual_position=0.35,
        sector_results=[],
        trend_pool=[],
        watch_pool=[],
        risk_pool=[],
        position_signals=[],
        invalidation_signals=["最高连板股跌停开", "北向净流出>50亿"],
    )
    print(f"Report saved to: {filepath}")
    
    # 测试持仓CSV
    csv_path = gen.generate_position_csv(
        date="20250619",
        market_regime="结构性趋势",
        total_position_limit=0.50,
        actual_position=0.35,
        positions=[{
            "code": "600519", "name": "贵州茅台", "sector": "白酒", "pattern": "W底",
            "entry_date": "2026-06-15", "entry_price": 1680.00, "stop_loss": 1600.00,
            "current_price": 1720.00, "pnl_pct": 0.0238, "position_pct": 0.10,
            "signal": "绿灯", "target_1": 1850.00, "target_2": 2020.00,
            "next_action": "持有", "notes": "板块发酵期"
        }]
    )
    print(f"Position CSV saved to: {csv_path}")
    
    # 测试执行偏差报告
    dev_path = gen.generate_deviation_report(
        date="20250619",
        deviations=[{"item": "买入XXX", "plan": "突破XX元买入", "actual": "未买入", "deviation": "是", "reason": "开盘八法弱势"}],
        discipline_violations=["未执行止损"],
        corrections=["明日严格按止损价执行"],
    )
    print(f"Deviation report saved to: {dev_path}")
