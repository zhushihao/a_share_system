# -*- coding: utf-8 -*-
"""
EventBridge - 核心系统与事件引擎的桥接层

将现有系统的关键节点接入事件总线，使事件引擎可以：
1. 监听数据获取完成事件
2. 监听策略信号生成事件
3. 监听系统异常事件
4. 手动触发复盘/分析任务

使用方式：
    from core.event_bridge import EventBridge
    bridge = EventBridge()
    bridge.connect()  # 连接所有桥接点
"""

from typing import Any, Callable, Dict, Optional

from events.event_bus import EventBus, Event, EventType, get_event_bus
from core.observability import get_obs


class EventBridge:
    """
    事件桥接器
    
    将现有系统的 Observable 点接入 EventBus，实现：
    - 数据异常自动触发降级事件
    - 分析完成自动触发报告事件
    - 手动触发业务任务
    """
    
    def __init__(self):
        self._obs = get_obs()
        self._bus = get_event_bus()
        self._connected = False
    
    def connect(self) -> None:
        """连接所有桥接点"""
        if self._connected:
            return
        
        # 桥接数据降级事件
        self._bridge_resilience()
        
        # 桥接系统异常
        self._bridge_observability()
        
        self._connected = True
        self._obs.log("INFO", "EventBridge connected", "EventBridge")
    
    def _bridge_resilience(self) -> None:
        """桥接数据降级系统"""
        # 当数据源异常时，发布 DATA_SOURCE_DOWN 事件
        # 由 resilience 系统在降级时调用
        pass  # 由 resilience 主动调用 publish 方法
    
    def _bridge_observability(self) -> None:
        """桥接可观测性系统"""
        # 当系统错误日志出现时，发布 SYSTEM_ERROR 事件
        pass  # 由 observability 主动调用
    
    # ── 主动触发接口（供现有系统调用）──
    
    def publish_data_source_down(self, source_name: str, error: str) -> None:
        """数据降级时调用"""
        self._bus.publish(Event(
            event_type=EventType.DATA_SOURCE_DOWN,
            payload={"source": source_name, "error": error},
            source="resilience",
        ))
    
    def publish_data_source_recover(self, source_name: str) -> None:
        """数据恢复时调用"""
        self._bus.publish(Event(
            event_type=EventType.DATA_SOURCE_RECOVER,
            payload={"source": source_name},
            source="resilience",
        ))
    
    def publish_system_error(self, component: str, error: str) -> None:
        """系统错误时调用"""
        self._bus.publish(Event(
            event_type=EventType.SYSTEM_ERROR,
            payload={"component": component, "error": error},
            source="system",
        ))
    
    def publish_price_alert(self, code: str, alert_type: str, detail: Dict) -> None:
        """价格告警时调用"""
        event_map = {
            "breakout": EventType.PRICE_BREAKOUT,
            "drop": EventType.PRICE_DROP,
            "volume_spike": EventType.VOLUME_SPIKE,
        }
        event_type = event_map.get(alert_type, EventType.PRICE_ALERT)
        self._bus.publish(Event(
            event_type=event_type,
            payload={"code": code, **detail},
            source="price_monitor",
        ))
    
    def publish_sector_alert(self, sector_name: str, change_pct: float, top_stocks: list) -> None:
        """板块异动时调用"""
        event_type = EventType.SECTOR_SURGE if change_pct > 0 else EventType.SECTOR_DROP
        self._bus.publish(Event(
            event_type=event_type,
            payload={
                "sector": sector_name,
                "change_pct": change_pct,
                "top_stocks": top_stocks,
            },
            source="sector_monitor",
        ))
