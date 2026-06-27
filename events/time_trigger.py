# -*- coding: utf-8 -*-
"""
TimeTrigger - A股交易时间触发器

根据A股交易时间表自动触发事件：
- 9:15  开盘前（集合竞价开始）
- 9:30  开盘（连续竞价开始）
- 10:30 早盘中场
- 11:30 早盘收盘
- 13:00 午盘开盘
- 14:30 尾盘前
- 15:00 收盘
- 15:05 收盘后（复盘）

设计：
- 每分钟检测一次当前时间
- 匹配到交易时间点后，发布对应事件
- 每个时间点只触发一次（直到下一个交易日）
- 支持配置启用/禁用特定事件
"""

import time
from datetime import datetime, time as dt_time
from typing import Any, Dict, List, Optional, Set

from events.trigger_base import TriggerBase, TriggerConfig
from events.event_bus import Event, EventType


# ════════════════════════════════════════════════════════════
# A股交易时间表
# ════════════════════════════════════════════════════════════

MARKET_SCHEDULE = [
    # (时间, 事件类型, 事件名称, 是否工作日)
    (dt_time(9, 15),  EventType.MARKET_PRE_OPEN,  "开盘前",    True),
    (dt_time(9, 30),  EventType.MARKET_OPEN,      "开盘",      True),
    (dt_time(10, 30), EventType.MARKET_MID_AM,    "早盘中场",  True),
    (dt_time(11, 30), EventType.MARKET_NOON,      "早盘收盘",  True),
    (dt_time(13, 0),  EventType.MARKET_PM_OPEN,   "午盘开盘",  True),
    (dt_time(14, 30), EventType.MARKET_MID_PM,    "尾盘前",    True),
    (dt_time(15, 0),  EventType.MARKET_CLOSE,     "收盘",      True),
    (dt_time(15, 5),  EventType.MARKET_POST_CLOSE, "收盘后复盘", True),
]


# ════════════════════════════════════════════════════════════
# 时间触发器
# ════════════════════════════════════════════════════════════

class TimeTrigger(TriggerBase):
    """
    A股交易时间触发器
    
    Usage:
        trigger = TimeTrigger(enabled_events=["market_close", "market_post_close"])
        trigger.start()
        ...
        trigger.stop()
    """
    
    def __init__(self, enabled_events: Optional[List[str]] = None, 
                 interval_seconds: float = 60.0):
        """
        Args:
            enabled_events: 要启用的事件类型列表（EventType.value），None=全部启用
            interval_seconds: 检测间隔（默认60秒，最低30秒）
        """
        config = TriggerConfig(
            name="time_trigger",
            interval_seconds=max(interval_seconds, 30.0),
        )
        super().__init__(config)
        
        self.enabled_events: Set[str] = set(enabled_events) if enabled_events else None
        self._triggered_today: Set[str] = set()  # 今日已触发的时间点
        self._last_date: Optional[str] = None
    
    def check(self) -> Optional[Event]:
        """
        检测当前时间是否匹配交易时间表
        
        Returns:
            Event 对象（如果匹配到新的时间点）或 None
        """
        now = datetime.now()
        current_time = now.time()
        current_date = now.strftime("%Y%m%d")
        
        # 跨日重置
        if current_date != self._last_date:
            self._triggered_today.clear()
            self._last_date = current_date
            self._obs.log("INFO", f"New trading day: {current_date}", "TimeTrigger")
        
        # 检查每个时间点
        for trigger_time, event_type, name, workday_only in MARKET_SCHEDULE:
            # 检查是否已触发
            event_key = f"{current_date}_{event_type.value}"
            if event_key in self._triggered_today:
                continue
            
            # 检查是否启用
            if self.enabled_events is not None and event_type.value not in self.enabled_events:
                continue
            
            # 检查时间匹配（允许1分钟误差）
            time_diff = self._time_diff_seconds(current_time, trigger_time)
            if abs(time_diff) <= 60:  # 误差1分钟内
                self._triggered_today.add(event_key)
                self._obs.log("INFO", f"TimeTrigger fired: {name} ({event_type.value})", "TimeTrigger")
                return Event(
                    event_type=event_type,
                    payload={
                        "date": current_date,
                        "time": trigger_time.strftime("%H:%M"),
                        "name": name,
                    },
                    source="time_trigger",
                )
        
        return None
    
    def _time_diff_seconds(self, t1, t2) -> int:
        """计算两个 time 对象的秒差"""
        dt1 = datetime.combine(datetime.today(), t1)
        dt2 = datetime.combine(datetime.today(), t2)
        return int((dt1 - dt2).total_seconds())
    
    def get_next_events(self) -> List[Dict[str, Any]]:
        """
        获取今日剩余事件列表
        
        Returns:
            尚未触发的事件列表
        """
        now = datetime.now()
        current_time = now.time()
        current_date = now.strftime("%Y%m%d")
        
        result = []
        for trigger_time, event_type, name, _ in MARKET_SCHEDULE:
            event_key = f"{current_date}_{event_type.value}"
            if event_key in self._triggered_today:
                continue
            if trigger_time < current_time:
                continue
            result.append({
                "time": trigger_time.strftime("%H:%M"),
                "event_type": event_type.value,
                "name": name,
                "seconds_until": self._time_diff_seconds(trigger_time, current_time),
            })
        return result
