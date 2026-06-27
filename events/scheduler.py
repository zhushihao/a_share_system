# -*- coding: utf-8 -*-
"""
EventScheduler - 事件调度器

整合所有触发器，统一管理启动、停止、状态监控。
作为事件引擎的入口，用户通过此类与事件系统交互。

Usage:
    from events import EventScheduler
    
    scheduler = EventScheduler()
    scheduler.start()   # 启动所有触发器
    ...
    scheduler.stop()    # 停止所有触发器
    
    # 获取状态
    print(scheduler.get_status())
"""

import time
import threading
import yaml
from typing import Any, Dict, List, Optional

from events.event_bus import EventBus, get_event_bus
from events.trigger_base import TriggerBase, TriggerStatus
from events.time_trigger import TimeTrigger
from events.price_trigger import PriceTrigger
from events.sector_trigger import SectorTrigger
from events.system_trigger import SystemTrigger
from events.event_handlers import register_default_handlers
from core.observability import get_obs


# ════════════════════════════════════════════════════════════
# 事件调度器
# ════════════════════════════════════════════════════════════

class EventScheduler:
    """
    事件调度器 - 事件引擎主入口
    
    职责：
    1. 管理所有触发器的生命周期
    2. 加载配置并注册处理器
    3. 提供状态监控接口
    4. 优雅关闭
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: events.yaml 路径，默认使用 config/events.yaml
        """
        self._obs = get_obs()
        self._bus = get_event_bus()
        self._triggers: List[TriggerBase] = []
        self._running = False
        self._lock = threading.Lock()
        
        # 加载配置
        self.config = self._load_config(config_path)
        self._register_handlers()
    
    # ── 配置加载 ──
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载事件配置"""
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "events.yaml")
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                self._obs.log("INFO", f"Event config loaded: {config_path}", "EventScheduler")
                return config.get("events", {})
        except Exception as e:
            self._obs.log("WARN", f"Failed to load event config: {str(e)}, using defaults", "EventScheduler")
            return {}
    
    # ── 注册处理器 ──
    
    def _register_handlers(self) -> None:
        """注册事件处理器"""
        register_default_handlers(self._bus, self.config)
        self._obs.log("INFO", "Default event handlers registered", "EventScheduler")
    
    # ── 触发器管理 ──
    
    def _init_triggers(self) -> None:
        """初始化所有触发器"""
        triggers_cfg = self.config.get("triggers", {})
        
        # 时间触发器
        time_cfg = triggers_cfg.get("time", {})
        if time_cfg.get("enabled", True):
            enabled_events = time_cfg.get("enabled_events")
            interval = time_cfg.get("interval_seconds", 60.0)
            trigger = TimeTrigger(
                enabled_events=enabled_events,
                interval_seconds=interval,
            )
            self._triggers.append(trigger)
            self._obs.log("INFO", f"TimeTrigger initialized (events={enabled_events or 'all'})", "EventScheduler")
        
        # 价格触发器
        price_cfg = triggers_cfg.get("price", {})
        if price_cfg.get("enabled", False):
            trigger = PriceTrigger(
                watchlist=price_cfg.get("watchlist", []),
                breakout_threshold=price_cfg.get("breakout_threshold", 0.05),
                drop_threshold=price_cfg.get("drop_threshold", 0.05),
                volume_spike_ratio=price_cfg.get("volume_spike_ratio", 2.0),
                interval_seconds=price_cfg.get("interval_seconds", 30.0),
            )
            self._triggers.append(trigger)
            self._obs.log("INFO", f"PriceTrigger initialized (watchlist={len(trigger.watchlist)})", "EventScheduler")
        
        # 板块触发器
        sector_cfg = triggers_cfg.get("sector", {})
        if sector_cfg.get("enabled", False):
            trigger = SectorTrigger(
                surge_threshold=sector_cfg.get("surge_threshold", 0.03),
                drop_threshold=sector_cfg.get("drop_threshold", 0.03),
                interval_seconds=sector_cfg.get("interval_seconds", 300.0),
            )
            self._triggers.append(trigger)
            self._obs.log("INFO", "SectorTrigger initialized", "EventScheduler")
        
        # 系统监控触发器
        system_cfg = triggers_cfg.get("system", {})
        if system_cfg.get("enabled", True):
            trigger = SystemTrigger(
                memory_threshold=system_cfg.get("memory_threshold", 80.0),
                disk_threshold=system_cfg.get("disk_threshold", 90.0),
                data_source_check=system_cfg.get("data_source_check", True),
                interval_seconds=system_cfg.get("interval_seconds", 60.0),
            )
            self._triggers.append(trigger)
            self._obs.log("INFO", "SystemTrigger initialized", "EventScheduler")
    
    # ── 生命周期 ──
    
    def start(self) -> None:
        """启动事件调度器（启动所有触发器）"""
        with self._lock:
            if self._running:
                self._obs.log("WARN", "EventScheduler already running", "EventScheduler")
                return
            
            self._init_triggers()
            
            for trigger in self._triggers:
                trigger.start()
            
            self._running = True
            self._obs.log("INFO", f"EventScheduler started ({len(self._triggers)} triggers active)", "EventScheduler")
    
    def stop(self) -> None:
        """停止事件调度器（停止所有触发器）"""
        with self._lock:
            if not self._running:
                return
            
            for trigger in self._triggers:
                trigger.stop()
            
            self._triggers.clear()
            self._running = False
            self._obs.log("INFO", "EventScheduler stopped", "EventScheduler")
    
    def restart(self) -> None:
        """重启事件调度器"""
        self.stop()
        time.sleep(0.5)
        self.start()
    
    # ── 手动触发 ──
    
    def trigger_event(self, event_type_str: str, payload: Optional[Dict] = None) -> None:
        """
        手动触发事件（用于测试或命令行触发）
        
        Args:
            event_type_str: EventType.value 字符串，如 "market_post_close"
            payload: 事件载荷
        """
        from events.event_bus import EventType, Event
        
        try:
            event_type = EventType(event_type_str)
        except ValueError:
            self._obs.log("ERROR", f"Unknown event type: {event_type_str}", "EventScheduler")
            return
        
        event = Event(
            event_type=event_type,
            payload=payload or {},
            source="manual_trigger",
        )
        self._bus.publish(event, async_dispatch=False)  # 同步执行，方便观察
        self._obs.log("INFO", f"Manually triggered: {event_type_str}", "EventScheduler")
    
    # ── 状态查询 ──
    
    def get_status(self) -> Dict[str, Any]:
        """获取调度器完整状态"""
        return {
            "running": self._running,
            "trigger_count": len(self._triggers),
            "triggers": [t.get_status() for t in self._triggers],
            "bus_stats": self._bus.get_stats(),
        }
    
    def get_next_events(self) -> List[Dict[str, Any]]:
        """获取今日剩余事件列表"""
        for trigger in self._triggers:
            if isinstance(trigger, TimeTrigger):
                return trigger.get_next_events()
        return []
    
    # ── 运行模式 ──
    
    def run_forever(self) -> None:
        """
        阻塞运行（用于独立进程）
        
        保持主线程存活，等待 KeyboardInterrupt 停止。
        """
        self.start()
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._obs.log("INFO", "KeyboardInterrupt received, shutting down...", "EventScheduler")
        finally:
            self.stop()
            self._bus.shutdown()


import os
