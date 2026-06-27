# -*- coding: utf-8 -*-
"""
SectorTrigger - 板块异动触发器

每5分钟检测板块涨跌幅，当板块整体异动时触发事件。

触发条件（可配置）：
- 板块突涨：板块整体涨幅超过 surge_threshold
- 板块突跌：板块整体跌幅超过 drop_threshold
- 板块龙头切换：板块内涨幅第一的股票发生变化

去重机制：每个板块每天每种事件只触发一次。

配置参数（events.yaml）：
    triggers:
      sector:
        enabled: true
        interval_seconds: 300
        surge_threshold: 0.03
        drop_threshold: 0.03
        sectors: []  # 监控板块列表（空则全部监控）
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from events.trigger_base import TriggerBase, TriggerConfig
from events.event_bus import Event, EventType
from core.observability import get_obs


# 模拟板块定义（后续可接入真实板块数据）
DEFAULT_SECTORS = {
    "半导体": ["688981", "600460", "603501", "002371", "300782"],
    "白酒": ["600519", "000858", "000568", "002304", "600702"],
    "新能源": ["300750", "002594", "601012", "600438", "688063"],
    "银行": ["600036", "601398", "601288", "601939", "600016"],
    "医药": ["600276", "600436", "000538", "603259", "300003"],
    "汽车": ["002594", "601633", "600104", "600741", "000951"],
    "电力": ["600900", "600011", "600795", "601985", "600886"],
    "房地产": ["000002", "600048", "001979", "600383", "000656"],
    "钢铁": ["600019", "000932", "600507", "600808", "000825"],
    "煤炭": ["601088", "601699", "600188", "601898", "600123"],
}


class SectorTrigger(TriggerBase):
    """
    板块异动触发器

    Usage:
        trigger = SectorTrigger(surge_threshold=0.03)
        trigger.start()
    """

    def __init__(self, surge_threshold: float = 0.03,
                 drop_threshold: float = 0.03,
                 sectors: Dict[str, List[str]] = None,
                 interval_seconds: float = 300.0):
        """
        Args:
            surge_threshold: 板块突涨阈值（如 0.03 = 3%）
            drop_threshold: 板块突跌阈值（如 0.03 = 3%）
            sectors: 板块定义 {name: [codes]}
            interval_seconds: 检测间隔（默认5分钟）
        """
        config = TriggerConfig(
            name="sector_trigger",
            interval_seconds=max(interval_seconds, 60.0),  # 最低1分钟
        )
        super().__init__(config)

        self.sectors = sectors or DEFAULT_SECTORS
        self.surge_threshold = surge_threshold
        self.drop_threshold = abs(drop_threshold)

        self._provider = None  # 延迟初始化
        self._triggered_today: Dict[str, Set[str]] = {}  # 去重
        self._leader_cache: Dict[str, str] = {}  # 上次龙头 {sector_name: code}

    def _get_provider(self):
        """延迟初始化数据提供者"""
        if self._provider is None:
            from utils.mootdx_provider import MootdxDataProvider
            self._provider = MootdxDataProvider()
        return self._provider

    def check(self) -> Optional[Event]:
        """检测板块异动"""
        today = datetime.now().strftime("%Y%m%d")
        if today not in self._triggered_today:
            self._triggered_today[today] = set()

        try:
            provider = self._get_provider()

            for sector_name, codes in self.sectors.items():
                # 获取板块内股票行情
                quotes = provider.fetch_realtime_quote(codes)
                if quotes is None or len(quotes) == 0:
                    continue

                # 计算板块平均涨跌幅
                total_change = 0
                count = 0
                leader_code = None
                leader_change = float('-inf')
                top_stocks = []

                for _, row in quotes.iterrows():
                    code = str(row.get("code", ""))
                    price = float(row.get("price", 0))
                    last_close = float(row.get("last_close", 0)) or 1
                    change_pct = (price - last_close) / last_close

                    total_change += change_pct
                    count += 1
                    top_stocks.append({"code": code, "change_pct": round(change_pct * 100, 2)})

                    if change_pct > leader_change:
                        leader_change = change_pct
                        leader_code = code

                if count == 0:
                    continue

                avg_change = total_change / count
                top_stocks.sort(key=lambda x: x["change_pct"], reverse=True)

                # 检测板块突涨
                if avg_change >= self.surge_threshold:
                    event_key = f"{today}_{sector_name}_surge"
                    if event_key not in self._triggered_today[today]:
                        self._triggered_today[today].add(event_key)
                        return Event(
                            event_type=EventType.SECTOR_SURGE,
                            payload={
                                "sector": sector_name,
                                "change_pct": round(avg_change * 100, 2),
                                "leader": leader_code,
                                "leader_change": round(leader_change * 100, 2),
                                "top_stocks": top_stocks[:3],
                            },
                            source="sector_trigger",
                        )

                # 检测板块突跌
                if avg_change <= -self.drop_threshold:
                    event_key = f"{today}_{sector_name}_drop"
                    if event_key not in self._triggered_today[today]:
                        self._triggered_today[today].add(event_key)
                        return Event(
                            event_type=EventType.SECTOR_DROP,
                            payload={
                                "sector": sector_name,
                                "change_pct": round(avg_change * 100, 2),
                                "leader": leader_code,
                                "leader_change": round(leader_change * 100, 2),
                                "top_stocks": top_stocks[:3],
                            },
                            source="sector_trigger",
                        )

                # 检测龙头切换
                if sector_name in self._leader_cache:
                    if self._leader_cache[sector_name] != leader_code:
                        event_key = f"{today}_{sector_name}_leader_change"
                        if event_key not in self._triggered_today[today]:
                            self._triggered_today[today].add(event_key)
                            self._leader_cache[sector_name] = leader_code
                            return Event(
                                event_type=EventType.SECTOR_LEADER_CHANGE,
                                payload={
                                    "sector": sector_name,
                                    "old_leader": self._leader_cache.get(sector_name, ""),
                                    "new_leader": leader_code,
                                    "new_leader_change": round(leader_change * 100, 2),
                                },
                                source="sector_trigger",
                            )
                else:
                    self._leader_cache[sector_name] = leader_code

        except Exception as e:
            self._obs.log("WARN", f"SectorTrigger check failed: {str(e)}", "SectorTrigger")

        return None

    def get_status(self) -> Dict[str, Any]:
        """获取触发器状态"""
        base = super().get_status()
        base.update({
            "sector_count": len(self.sectors),
            "surge_threshold": self.surge_threshold,
            "drop_threshold": self.drop_threshold,
        })
        return base
