# -*- coding: utf-8 -*-
"""
Tests for Event Engine

运行: python -m pytest tests/test_events.py -v
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from events.event_bus import EventBus, Event, EventType, get_event_bus
from events.trigger_base import TriggerBase, TriggerConfig, TriggerStatus
from events.time_trigger import TimeTrigger, MARKET_SCHEDULE
from events.event_handlers import LoggingHandler, BaseEventHandler
from events.scheduler import EventScheduler


# ════════════════════════════════════════════════════════════
# EventBus Tests
# ════════════════════════════════════════════════════════════

def test_event_bus_singleton():
    """测试单例模式"""
    bus1 = EventBus()
    bus2 = EventBus()
    assert bus1 is bus2


def test_subscribe_publish():
    """测试订阅和发布"""
    bus = EventBus()
    received = []
    
    def handler(event):
        received.append(event.event_type.value)
    
    bus.subscribe(EventType.MARKET_CLOSE, handler)
    bus.publish(Event(EventType.MARKET_CLOSE, {"date": "20250619"}), async_dispatch=False)
    
    assert len(received) == 1
    assert received[0] == "market_close"
    
    # 清理
    bus.unsubscribe(EventType.MARKET_CLOSE, handler)


def test_unsubscribe():
    """测试取消订阅"""
    bus = EventBus()
    received = []
    
    def handler(event):
        received.append(event.event_type.value)
    
    bus.subscribe(EventType.MARKET_OPEN, handler)
    bus.unsubscribe(EventType.MARKET_OPEN, handler)
    bus.publish(Event(EventType.MARKET_OPEN), async_dispatch=False)
    
    assert len(received) == 0


def test_async_publish():
    """测试异步发布"""
    bus = EventBus()
    received = []
    
    def handler(event):
        time.sleep(0.05)  # 模拟耗时处理
        received.append(event.event_type.value)
    
    bus.subscribe(EventType.CUSTOM, handler)
    bus.publish(Event(EventType.CUSTOM), async_dispatch=True)
    
    # 等待异步处理
    time.sleep(0.2)
    assert len(received) == 1


def test_event_to_dict():
    """测试事件序列化"""
    event = Event(EventType.MARKET_CLOSE, {"date": "20250619"})
    d = event.to_dict()
    assert d["event_type"] == "market_close"
    assert d["payload"]["date"] == "20250619"
    assert "event_id" in d
    assert "timestamp" in d


def test_bus_stats():
    """测试总线统计"""
    bus = EventBus()
    stats = bus.get_stats()
    assert "total_subscribers" in stats
    assert "event_history_count" in stats


# ════════════════════════════════════════════════════════════
# TriggerBase Tests
# ════════════════════════════════════════════════════════════

def test_trigger_lifecycle():
    """测试触发器生命周期"""
    
    class TestTrigger(TriggerBase):
        def check(self):
            return None
    
    trigger = TestTrigger(TriggerConfig("test", interval_seconds=1.0))
    assert trigger.status == TriggerStatus.STOPPED
    
    trigger.start()
    time.sleep(0.1)
    assert trigger.status == TriggerStatus.RUNNING
    
    trigger.stop()
    assert trigger.status == TriggerStatus.STOPPED


def test_trigger_pause_resume():
    """测试暂停和恢复"""
    
    class TestTrigger(TriggerBase):
        def check(self):
            return None
    
    trigger = TestTrigger(TriggerConfig("test", interval_seconds=1.0))
    trigger.start()
    time.sleep(0.1)
    
    trigger.pause()
    assert trigger.status == TriggerStatus.PAUSED
    
    trigger.resume()
    assert trigger.status == TriggerStatus.RUNNING
    
    trigger.stop()


def test_trigger_status_dict():
    """测试触发器状态字典"""
    
    class TestTrigger(TriggerBase):
        def check(self):
            return None
    
    trigger = TestTrigger(TriggerConfig("test_stat", interval_seconds=1.0))
    status = trigger.get_status()
    assert status["name"] == "test_stat"
    assert status["status"] == "stopped"
    assert status["trigger_count"] == 0


# ════════════════════════════════════════════════════════════
# TimeTrigger Tests
# ════════════════════════════════════════════════════════════

def test_market_schedule_defined():
    """测试交易时间表已定义"""
    assert len(MARKET_SCHEDULE) > 0
    # 检查包含收盘事件
    close_events = [e for e in MARKET_SCHEDULE if e[1] == EventType.MARKET_CLOSE]
    assert len(close_events) == 1


def test_time_trigger_config():
    """测试时间触发器配置"""
    trigger = TimeTrigger(enabled_events=["market_close"], interval_seconds=30)
    assert trigger.config.name == "time_trigger"
    assert trigger.config.interval_seconds == 30
    assert trigger.enabled_events == {"market_close"}


def test_time_trigger_all_events():
    """测试默认启用所有事件"""
    trigger = TimeTrigger()
    assert trigger.enabled_events is None


def test_time_trigger_next_events():
    """测试获取剩余事件"""
    trigger = TimeTrigger()
    # 启动后设置日期
    trigger._last_date = "20250619"
    next_events = trigger.get_next_events()
    assert isinstance(next_events, list)
    # 所有事件都没触发过，应该有剩余事件


# ════════════════════════════════════════════════════════════
# EventHandler Tests
# ════════════════════════════════════════════════════════════

def test_logging_handler():
    """测试日志处理器"""
    handler = LoggingHandler()
    event = Event(EventType.MARKET_CLOSE, {"date": "20250619"})
    handler(event)  # 不应抛出异常


def test_base_handler():
    """测试基类"""
    
    class TestHandler(BaseEventHandler):
        def handle(self, event):
            pass
    
    handler = TestHandler("test")
    event = Event(EventType.CUSTOM)
    handler(event)
    assert handler._call_count == 1


# ════════════════════════════════════════════════════════════
# Scheduler Tests
# ════════════════════════════════════════════════════════════

def test_scheduler_init():
    """测试调度器初始化"""
    scheduler = EventScheduler()
    assert scheduler.config is not None


def test_scheduler_start_stop():
    """测试调度器启停"""
    scheduler = EventScheduler()
    
    scheduler.start()
    time.sleep(0.2)
    assert scheduler._running is True
    
    scheduler.stop()
    assert scheduler._running is False


def test_scheduler_status():
    """测试调度器状态查询"""
    scheduler = EventScheduler()
    status = scheduler.get_status()
    assert "running" in status
    assert "trigger_count" in status
    assert "bus_stats" in status


def test_manual_trigger():
    """测试手动触发事件"""
    scheduler = EventScheduler()
    received = []
    
    def handler(event):
        received.append(event.event_type.value)
    
    bus = get_event_bus()
    bus.subscribe(EventType.MARKET_CLOSE, handler)
    
    scheduler.trigger_event("market_close", {"date": "20250619"})
    assert len(received) == 1
    
    bus.unsubscribe(EventType.MARKET_CLOSE, handler)


def test_manual_trigger_unknown_event():
    """测试手动触发未知事件"""
    scheduler = EventScheduler()
    scheduler.trigger_event("unknown_event")  # 不应抛出异常


# ════════════════════════════════════════════════════════════
# Main Test Runner
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Running Event Engine Tests...")
    
    tests = [
        test_event_bus_singleton,
        test_subscribe_publish,
        test_unsubscribe,
        test_async_publish,
        test_event_to_dict,
        test_bus_stats,
        test_trigger_lifecycle,
        test_trigger_pause_resume,
        test_trigger_status_dict,
        test_market_schedule_defined,
        test_time_trigger_config,
        test_time_trigger_all_events,
        test_time_trigger_next_events,
        test_logging_handler,
        test_base_handler,
        test_scheduler_init,
        test_scheduler_start_stop,
        test_scheduler_status,
        test_manual_trigger,
        test_manual_trigger_unknown_event,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: {str(e)}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    
    if failed == 0:
        print("All tests PASSED! ✓")
    else:
        print(f"Some tests FAILED ✗")
        sys.exit(1)
