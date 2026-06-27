"""
Events Module - 事件引擎

提供事件总线、触发器、处理器、调度器的完整事件驱动架构。

Usage:
    from events import EventBus, EventType, Event
    
    bus = EventBus()
    bus.subscribe(EventType.MARKET_CLOSE, my_handler)
    bus.publish(Event(EventType.MARKET_CLOSE, {"date": "20250619"}))
"""

from .event_bus import EventBus, Event, EventType
from .trigger_base import TriggerBase, TriggerStatus
from .time_trigger import TimeTrigger, MARKET_SCHEDULE
from .event_handlers import (
    BaseEventHandler, LoggingHandler, PostMarketHandler, PreMarketHandler
)
from .scheduler import EventScheduler

__all__ = [
    "EventBus",
    "Event",
    "EventType",
    "TriggerBase",
    "TriggerStatus",
    "TimeTrigger",
    "MARKET_SCHEDULE",
    "BaseEventHandler",
    "LoggingHandler",
    "PostMarketHandler",
    "PreMarketHandler",
    "EventScheduler",
]
