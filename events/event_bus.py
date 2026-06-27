# -*- coding: utf-8 -*-
"""
EventBus - 线程安全的事件发布订阅总线

核心能力：
1. 发布/订阅模式 - 解耦事件生产者与消费者
2. 线程安全 - 支持多线程并发 publish/subscribe
3. 同步/异步投递 - 根据处理器需求选择
4. 事件追踪 - 记录事件处理链路
5. 错误隔离 - 单个处理器失败不影响其他处理器
"""

import time
import threading
import traceback
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from core.observability import get_obs


# ════════════════════════════════════════════════════════════
# 事件类型定义
# ════════════════════════════════════════════════════════════

class EventType(Enum):
    """A股交易相关事件类型"""
    
    # ── 时间事件 ──
    MARKET_PRE_OPEN = "market_pre_open"        # 9:15 开盘前（集合竞价开始）
    MARKET_OPEN = "market_open"                # 9:30 连续竞价开始
    MARKET_MID_AM = "market_mid_am"            # 10:30 早盘中场
    MARKET_NOON = "market_noon"                # 11:30 早盘收盘
    MARKET_PM_OPEN = "market_pm_open"          # 13:00 午盘开盘
    MARKET_MID_PM = "market_mid_pm"            # 14:30 尾盘前
    MARKET_CLOSE = "market_close"              # 15:00 收盘
    MARKET_POST_CLOSE = "market_post_close"    # 15:05 收盘后（复盘）
    
    # ── 价格事件 ──
    PRICE_BREAKOUT = "price_breakout"          # 价格突破（向上）
    PRICE_DROP = "price_drop"                  # 价格暴跌（向下）
    VOLUME_SPIKE = "volume_spike"              # 成交量异动
    PRICE_ALERT = "price_alert"                # 通用价格告警
    
    # ── 板块事件 ──
    SECTOR_SURGE = "sector_surge"              # 板块突涨
    SECTOR_DROP = "sector_drop"                # 板块突跌
    SECTOR_LEADER_CHANGE = "sector_leader_change"  # 板块龙头切换
    
    # ── 系统事件 ──
    DATA_SOURCE_DOWN = "data_source_down"      # 数据源故障
    DATA_SOURCE_RECOVER = "data_source_recover"  # 数据源恢复
    CACHE_EXPIRED = "cache_expired"            # 缓存过期
    SYSTEM_ERROR = "system_error"              # 系统错误
    
    # ── 自定义事件 ──
    CUSTOM = "custom"                          # 用户自定义事件


# ════════════════════════════════════════════════════════════
# 事件数据类
# ════════════════════════════════════════════════════════════

@dataclass
class Event:
    """事件对象"""
    event_type: EventType
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: f"evt_{int(time.time()*1000)}_{threading.current_thread().ident}")
    source: str = "system"  # 事件来源
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            "source": self.source,
            "payload": self.payload,
        }


# ════════════════════════════════════════════════════════════
# 事件总线
# ════════════════════════════════════════════════════════════

class EventBus:
    """
    线程安全的事件发布订阅总线（单例模式）
    
    Usage:
        bus = EventBus()
        
        # 订阅
        def my_handler(event: Event):
            print(f"Received: {event.event_type.value}")
        bus.subscribe(EventType.MARKET_CLOSE, my_handler)
        
        # 发布
        bus.publish(Event(EventType.MARKET_CLOSE, {"date": "20250619"}))
        
        # 取消订阅
        bus.unsubscribe(EventType.MARKET_CLOSE, my_handler)
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance
    
    def _init(self):
        """初始化（只执行一次）"""
        self._subscribers: Dict[EventType, List[Callable]] = {et: [] for et in EventType}
        self._subscriber_lock = threading.RLock()
        self._obs = get_obs()
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="evt_handler")
        self._event_history: List[Dict] = []  # 最近事件记录（用于调试）
        self._history_limit = 1000
    
    # ── 订阅管理 ──
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """
        订阅事件
        
        Args:
            event_type: 要监听的事件类型
            handler: 回调函数，接收 Event 对象
        """
        with self._subscriber_lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
                handler_name = getattr(handler, '__name__', getattr(handler, 'name', repr(handler)))
                self._obs.log("INFO", f"Subscribed {handler_name} to {event_type.value}", "EventBus")
    
    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """取消订阅"""
        with self._subscriber_lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
                handler_name = getattr(handler, '__name__', getattr(handler, 'name', repr(handler)))
                self._obs.log("INFO", f"Unsubscribed {handler_name} from {event_type.value}", "EventBus")
    
    def subscribe_all(self, handler: Callable[[Event], None]) -> None:
        """订阅所有事件类型（用于调试/日志）"""
        for event_type in EventType:
            self.subscribe(event_type, handler)
    
    # ── 发布 ──
    
    def publish(self, event: Event, async_dispatch: bool = True) -> None:
        """
        发布事件
        
        Args:
            event: 事件对象
            async_dispatch: True=异步投递（线程池），False=同步投递
        """
        # 记录历史
        self._record_history(event)
        
        with self._subscriber_lock:
            handlers = list(self._subscribers[event.event_type])
        
        if not handlers:
            self._obs.log("DEBUG", f"No handlers for {event.event_type.value}", "EventBus")
            return
        
        self._obs.log("INFO", f"Publishing {event.event_type.value} to {len(handlers)} handlers", "EventBus")
        
        for handler in handlers:
            if async_dispatch:
                self._executor.submit(self._safe_execute, handler, event)
            else:
                self._safe_execute(handler, event)
    
    def _safe_execute(self, handler: Callable, event: Event) -> None:
        """安全执行处理器（隔离错误）"""
        try:
            handler(event)
        except Exception as e:
            handler_name = getattr(handler, '__name__', getattr(handler, 'name', repr(handler)))
            self._obs.log("ERROR", 
                f"Handler {handler_name} failed for {event.event_type.value}: {str(e)}", 
                "EventBus")
    
    def _record_history(self, event: Event) -> None:
        """记录事件历史"""
        self._event_history.append(event.to_dict())
        if len(self._event_history) > self._history_limit:
            self._event_history = self._event_history[-self._history_limit:]
    
    # ── 查询 ──
    
    def get_subscribers(self, event_type: Optional[EventType] = None) -> Dict[str, int]:
        """获取订阅统计"""
        if event_type:
            return {event_type.value: len(self._subscribers[event_type])}
        return {et.value: len(handlers) for et, handlers in self._subscribers.items()}
    
    def get_recent_events(self, limit: int = 50) -> List[Dict]:
        """获取最近事件"""
        return self._event_history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取总线统计"""
        total_subscribers = sum(len(h) for h in self._subscribers.values())
        return {
            "total_subscribers": total_subscribers,
            "subscriber_breakdown": self.get_subscribers(),
            "event_history_count": len(self._event_history),
            "executor_workers": self._executor._max_workers,
        }
    
    # ── 生命周期 ──
    
    def shutdown(self) -> None:
        """关闭事件总线"""
        self._executor.shutdown(wait=True)
        self._obs.log("INFO", "EventBus shutdown complete", "EventBus")


# ════════════════════════════════════════════════════════════
# 便捷函数
# ════════════════════════════════════════════════════════════

def get_event_bus() -> EventBus:
    """获取事件总线实例"""
    return EventBus()
