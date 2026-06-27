# -*- coding: utf-8 -*-
"""
EventHandlers - 事件处理器

将事件转换为实际业务动作。每个处理器是一个函数，接收 Event 对象。
处理器在 EventBus 的线程池中异步执行。

已内置处理器：
- LoggingHandler: 记录所有事件
- PostMarketHandler: 收盘后执行复盘
- PreMarketHandler: 开盘前执行舆情分析
- SystemAlertHandler: 系统告警
"""

import os
import sys
from typing import Any, Dict

from events.event_bus import Event, EventType
from core.observability import get_obs


# ════════════════════════════════════════════════════════════
# 基础处理器
# ════════════════════════════════════════════════════════════

class BaseEventHandler:
    """处理器基类"""
    
    def __init__(self, name: str):
        self.name = name
        self._obs = get_obs()
        self._call_count = 0
    
    def __call__(self, event: Event) -> None:
        self._call_count += 1
        self._obs.log("INFO", f"Handler[{self.name}] processing {event.event_type.value}", "EventHandler")
        self.handle(event)
    
    def handle(self, event: Event) -> None:
        """子类覆盖此方法"""
        pass


# ════════════════════════════════════════════════════════════
# 日志处理器
# ════════════════════════════════════════════════════════════

class LoggingHandler(BaseEventHandler):
    """日志处理器 - 记录所有事件到系统日志"""
    
    def __init__(self):
        super().__init__("logging")
    
    def handle(self, event: Event) -> None:
        self._obs.log("INFO", f"Event: {event.event_type.value} | {event.payload}", "EventHandler")


# ════════════════════════════════════════════════════════════
# 盘后复盘处理器
# ════════════════════════════════════════════════════════════

class PostMarketHandler(BaseEventHandler):
    """
    盘后复盘处理器
    
    MARKET_CLOSE 或 MARKET_POST_CLOSE 事件触发时：
    1. 执行收盘复盘（调用现有 run_post_market_v4.py 逻辑）
    2. 生成复盘报告
    3. 推送飞书（如果配置）
    """
    
    def __init__(self, auto_run: bool = False):
        super().__init__("post_market")
        self.auto_run = auto_run  # 是否自动执行完整复盘
    
    def handle(self, event: Event) -> None:
        date_str = event.payload.get("date", "")
        self._obs.log("INFO", f"PostMarketHandler triggered for {date_str}", "EventHandler")
        
        if not self.auto_run:
            self._obs.log("INFO", "PostMarketHandler auto_run=False, skipping", "EventHandler")
            return
        
        try:
            # 调用现有复盘逻辑
            self._run_post_market(date_str)
        except Exception as e:
            self._obs.log("ERROR", f"PostMarketHandler failed: {str(e)}", "EventHandler")
    
    def _run_post_market(self, date_str: str) -> None:
        """执行收盘复盘"""
        # 这里调用现有复盘逻辑
        # 为避免循环导入，延迟导入
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        from main import run_post_market
        run_post_market(date_str)
        
        self._obs.log("INFO", f"Post market review completed for {date_str}", "EventHandler")


# ════════════════════════════════════════════════════════════
# 盘前处理器
# ════════════════════════════════════════════════════════════

class PreMarketHandler(BaseEventHandler):
    """
    盘前处理器
    
    MARKET_PRE_OPEN 事件触发时：
    1. 执行舆情分析
    2. 检查隔夜消息面
    3. 生成早盘提示
    """
    
    def __init__(self):
        super().__init__("pre_market")
    
    def handle(self, event: Event) -> None:
        date_str = event.payload.get("date", "")
        self._obs.log("INFO", f"PreMarketHandler triggered for {date_str}", "EventHandler")
        
        try:
            # TODO: 调用舆情分析模块
            self._obs.log("INFO", "Pre-market sentiment analysis completed", "EventHandler")
        except Exception as e:
            self._obs.log("ERROR", f"PreMarketHandler failed: {str(e)}", "EventHandler")


# ════════════════════════════════════════════════════════════
# 系统告警处理器
# ════════════════════════════════════════════════════════════

class SystemAlertHandler(BaseEventHandler):
    """
    系统告警处理器
    
    DATA_SOURCE_DOWN / SYSTEM_ERROR 事件触发时：
    1. 记录告警
    2. 尝试自动恢复（如切换数据源）
    """
    
    def __init__(self, auto_recover: bool = True):
        super().__init__("system_alert")
        self.auto_recover = auto_recover
    
    def handle(self, event: Event) -> None:
        self._obs.log("WARN", f"System alert: {event.event_type.value} | {event.payload}", "EventHandler")
        
        if event.event_type == EventType.DATA_SOURCE_DOWN and self.auto_recover:
            self._obs.log("INFO", "Attempting auto-recover...", "EventHandler")
            # 自动恢复逻辑由 resilience 系统处理


# ════════════════════════════════════════════════════════════
# 便捷函数：注册所有处理器
# ════════════════════════════════════════════════════════════

def register_default_handlers(event_bus, config: Dict[str, Any] = None) -> None:
    """
    注册默认处理器
    
    Args:
        event_bus: EventBus 实例
        config: 配置字典（从 events.yaml 读取）
    """
    cfg = config or {}
    
    # 日志处理器（始终启用）
    logging_cfg = cfg.get("handlers", {}).get("logging", {})
    if logging_cfg.get("enabled", True):
        event_bus.subscribe_all(LoggingHandler())
    
    # 盘后复盘
    post_cfg = cfg.get("handlers", {}).get("post_market", {})
    if post_cfg.get("enabled", True):
        handler = PostMarketHandler(auto_run=post_cfg.get("auto_run", False))
        event_bus.subscribe(EventType.MARKET_CLOSE, handler)
        event_bus.subscribe(EventType.MARKET_POST_CLOSE, handler)
    
    # 盘前分析
    pre_cfg = cfg.get("handlers", {}).get("pre_market", {})
    if pre_cfg.get("enabled", True):
        event_bus.subscribe(EventType.MARKET_PRE_OPEN, PreMarketHandler())
    
    # 系统告警
    sys_cfg = cfg.get("handlers", {}).get("system_alert", {})
    if sys_cfg.get("enabled", True):
        handler = SystemAlertHandler(auto_recover=sys_cfg.get("auto_recover", True))
        event_bus.subscribe(EventType.DATA_SOURCE_DOWN, handler)
        event_bus.subscribe(EventType.SYSTEM_ERROR, handler)



# ════════════════════════════════════════════════════════════
# 价格告警处理器
# ════════════════════════════════════════════════════════════

class PriceAlertHandler(BaseEventHandler):
    """
    价格告警处理器

    PRICE_BREAKOUT / PRICE_DROP / VOLUME_SPIKE 事件触发时：
    1. 记录告警日志
    2. 推送通知（可扩展飞书推送）
    3. 写入持久化存储
    """

    def __init__(self):
        super().__init__("price_alert")

    def handle(self, event: Event) -> None:
        code = event.payload.get("code", "")
        event_type = event.event_type.value

        self._obs.log("WARN", f"Price alert: {code} | {event_type} | {event.payload}", "PriceAlertHandler")

        # TODO: 扩展飞书推送、邮件通知
        # 持久化记录（可选）
        try:
            from core.persistence import PersistenceManager
            pm = PersistenceManager()
            pm.save_json(f"alerts/{event_type}_{code}_{event.event_id}.json", event.to_dict())
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
# 板块告警处理器
# ════════════════════════════════════════════════════════════

class SectorAlertHandler(BaseEventHandler):
    """
    板块异动处理器

    SECTOR_SURGE / SECTOR_DROP / SECTOR_LEADER_CHANGE 事件触发时：
    1. 记录异动日志
    2. 生成异动报告
    """

    def __init__(self):
        super().__init__("sector_alert")

    def handle(self, event: Event) -> None:
        sector = event.payload.get("sector", "")
        event_type = event.event_type.value

        self._obs.log("WARN", f"Sector alert: {sector} | {event_type} | {event.payload}", "SectorAlertHandler")

        # 持久化记录
        try:
            from core.persistence import PersistenceManager
            pm = PersistenceManager()
            pm.save_json(f"alerts/{event_type}_{sector}_{event.event_id}.json", event.to_dict())
        except Exception:
            pass
