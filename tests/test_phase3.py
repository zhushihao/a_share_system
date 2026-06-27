# -*- coding: utf-8 -*-
"""
Phase 3 Tests - 高级触发器 + 看板增强 + 并行运行

运行: python tests/test_phase3.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from events.price_trigger import PriceTrigger
from events.sector_trigger import SectorTrigger, DEFAULT_SECTORS
from events.system_trigger import SystemTrigger
from events.trigger_base import TriggerConfig, TriggerStatus
from events.event_bus import Event, EventType


# ════════════════════════════════════════════════════════════
# PriceTrigger Tests
# ════════════════════════════════════════════════════════════

def test_price_trigger_init():
    """测试价格触发器初始化"""
    trigger = PriceTrigger(
        watchlist=["000001"],
        breakout_threshold=0.05,
        interval_seconds=10,
    )
    assert trigger.config.name == "price_trigger"
    assert trigger.watchlist == ["000001"]
    assert trigger.breakout_threshold == 0.05


def test_price_trigger_status():
    """测试价格触发器状态"""
    trigger = PriceTrigger(watchlist=["000001", "600519"])
    status = trigger.get_status()
    assert status["watchlist_count"] == 2
    assert status["breakout_threshold"] == 0.05


def test_price_trigger_history():
    """测试价格历史更新"""
    trigger = PriceTrigger(watchlist=["000001"])
    trigger._update_history("000001", 10.0, 1000)
    trigger._update_history("000001", 11.0, 2000)
    trigger._update_history("000001", 12.0, 3000)
    
    assert len(trigger._price_history["000001"]) == 3
    avg = trigger._get_avg_volume("000001")
    assert avg == 1500.0  # (1000+2000)/2


def test_price_trigger_no_watchlist():
    """测试无watchlist时返回None"""
    trigger = PriceTrigger(watchlist=[])
    result = trigger.check()
    assert result is None


def test_price_trigger_lifecycle():
    """测试价格触发器生命周期"""
    trigger = PriceTrigger(watchlist=["000001"], interval_seconds=1)
    trigger.start()
    time.sleep(0.1)
    assert trigger.status == TriggerStatus.RUNNING
    trigger.stop()
    assert trigger.status == TriggerStatus.STOPPED


# ════════════════════════════════════════════════════════════
# SectorTrigger Tests
# ════════════════════════════════════════════════════════════

def test_sector_trigger_init():
    """测试板块触发器初始化"""
    trigger = SectorTrigger(surge_threshold=0.03, interval_seconds=10)
    assert trigger.config.name == "sector_trigger"
    assert trigger.surge_threshold == 0.03
    assert len(trigger.sectors) > 0


def test_sector_trigger_status():
    """测试板块触发器状态"""
    trigger = SectorTrigger()
    status = trigger.get_status()
    assert status["sector_count"] == len(DEFAULT_SECTORS)
    assert status["surge_threshold"] == 0.03


def test_sector_trigger_lifecycle():
    """测试板块触发器生命周期"""
    trigger = SectorTrigger(interval_seconds=1)
    trigger.start()
    time.sleep(0.1)
    assert trigger.status == TriggerStatus.RUNNING
    trigger.stop()
    assert trigger.status == TriggerStatus.STOPPED


# ════════════════════════════════════════════════════════════
# SystemTrigger Tests
# ════════════════════════════════════════════════════════════

def test_system_trigger_init():
    """测试系统触发器初始化"""
    trigger = SystemTrigger(memory_threshold=80, interval_seconds=10)
    assert trigger.config.name == "system_trigger"
    assert trigger.memory_threshold == 80


def test_system_trigger_status():
    """测试系统触发器状态"""
    trigger = SystemTrigger()
    status = trigger.get_status()
    assert "memory_percent" in status
    assert status["memory_threshold"] == 80


def test_system_trigger_check():
    """测试系统触发器检测"""
    trigger = SystemTrigger(memory_threshold=99, disk_threshold=99)
    # 正常情况下不应触发（内存/磁盘使用<99%）
    result = trigger.check()
    # 可能返回None（正常）或Event（如果系统资源紧张）
    assert result is None or isinstance(result, Event)


def test_system_trigger_lifecycle():
    """测试系统触发器生命周期"""
    trigger = SystemTrigger(interval_seconds=1)
    trigger.start()
    time.sleep(0.1)
    assert trigger.status == TriggerStatus.RUNNING
    trigger.stop()
    assert trigger.status == TriggerStatus.STOPPED


# ════════════════════════════════════════════════════════════
# Dashboard Tests
# ════════════════════════════════════════════════════════════

def test_dashboard_sectors_page():
    """测试板块详情页"""
    from dashboard.app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get('/sectors')
    assert resp.status_code == 200


def test_dashboard_signals_page():
    """测试信号列表页"""
    from dashboard.app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get('/signals')
    assert resp.status_code == 200


def test_dashboard_stock_page():
    """测试单股详情页"""
    from dashboard.app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get('/stock/000001')
    assert resp.status_code == 200


def test_dashboard_data_service():
    """测试数据服务新增方法"""
    from dashboard.data_service import DashboardDataService
    service = DashboardDataService()
    
    sectors = service.get_all_sectors()
    assert len(sectors) > 0
    assert "name" in sectors[0]
    
    kline = service.get_stock_kline("000001")
    assert isinstance(kline, list)
    
    analysis = service.get_stock_analysis("000001")
    assert "momentum_score" in analysis


# ════════════════════════════════════════════════════════════
# Parallel Running Tests
# ════════════════════════════════════════════════════════════

def test_scheduler_with_all_triggers():
    """测试调度器加载所有触发器"""
    from events.scheduler import EventScheduler
    scheduler = EventScheduler()
    
    # 手动设置配置（启用所有触发器）
    scheduler.config = {
        "triggers": {
            "time": {"enabled": True, "interval_seconds": 60},
            "price": {"enabled": True, "watchlist": ["000001"], "interval_seconds": 10},
            "sector": {"enabled": True, "interval_seconds": 10},
            "system": {"enabled": True, "interval_seconds": 10},
        }
    }
    
    scheduler._init_triggers()
    assert len(scheduler._triggers) == 4
    
    for trigger in scheduler._triggers:
        trigger.stop()


def test_main_all_mode():
    """测试 --mode all 的导入可用性"""
    from dashboard.app import create_app
    from events.scheduler import EventScheduler
    
    app = create_app()
    scheduler = EventScheduler()
    
    assert app is not None
    assert scheduler is not None


# ════════════════════════════════════════════════════════════
# Main Test Runner
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Running Phase 3 Tests...")
    
    tests = [
        test_price_trigger_init,
        test_price_trigger_status,
        test_price_trigger_history,
        test_price_trigger_no_watchlist,
        test_price_trigger_lifecycle,
        test_sector_trigger_init,
        test_sector_trigger_status,
        test_sector_trigger_lifecycle,
        test_system_trigger_init,
        test_system_trigger_status,
        test_system_trigger_check,
        test_system_trigger_lifecycle,
        test_dashboard_sectors_page,
        test_dashboard_signals_page,
        test_dashboard_stock_page,
        test_dashboard_data_service,
        test_scheduler_with_all_triggers,
        test_main_all_mode,
    ]
    
    passed = 0
    failed = 0
    errors = []
    
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: {str(e)}")
            failed += 1
            errors.append(f"{test.__name__}: {str(e)}")
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    
    if failed == 0:
        print("All Phase 3 tests PASSED! ✓")
    else:
        print(f"Some tests FAILED ✗")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
