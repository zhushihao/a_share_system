# -*- coding: utf-8 -*-
"""
TriggerBase - 触发器抽象基类

所有触发器（时间、价格、板块、系统）都继承此类。
触发器在独立线程中运行，定期检测条件，条件满足时通过 EventBus 发布事件。
"""

import time
import threading
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Dict, Optional
from dataclasses import dataclass

from core.observability import get_obs


class TriggerStatus(Enum):
    """触发器状态"""
    STOPPED = "stopped"      # 未启动
    RUNNING = "running"      # 运行中
    PAUSED = "paused"        # 暂停
    ERROR = "error"          # 出错


@dataclass
class TriggerConfig:
    """触发器配置"""
    name: str
    enabled: bool = True
    interval_seconds: float = 60.0  # 检测间隔
    retry_on_error: bool = True
    retry_interval: float = 5.0
    max_retries: int = 3


class TriggerBase(ABC):
    """
    触发器基类
    
    Usage:
        class MyTrigger(TriggerBase):
            def check(self) -> Optional[Event]:
                if condition_met:
                    return Event(EventType.CUSTOM, {"detail": "xxx"})
                return None
        
        trigger = MyTrigger(TriggerConfig("my_trigger", interval_seconds=30))
        trigger.start()  # 启动后台线程
        ...
        trigger.stop()   # 停止
    """
    
    def __init__(self, config: TriggerConfig):
        self.config = config
        self.status = TriggerStatus.STOPPED
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._obs = get_obs()
        self._error_count = 0
        self._last_check_time: Optional[float] = None
        self._last_trigger_time: Optional[float] = None
        self._trigger_count = 0
    
    # ── 抽象接口 ──
    
    @abstractmethod
    def check(self) -> Optional[Any]:
        """
        检测条件是否满足
        
        Returns:
            Event 对象（条件满足）或 None（条件不满足）
        """
        pass
    
    # ── 生命周期 ──
    
    def start(self) -> None:
        """启动触发器（后台线程）"""
        if self.status == TriggerStatus.RUNNING:
            self._obs.log("WARN", f"Trigger {self.config.name} already running", "TriggerBase")
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"trigger_{self.config.name}",
            daemon=True,
        )
        self._thread.start()
        self.status = TriggerStatus.RUNNING
        self._obs.log("INFO", f"Trigger {self.config.name} started (interval={self.config.interval_seconds}s)", "TriggerBase")
    
    def stop(self) -> None:
        """停止触发器"""
        self._stop_event.set()
        self.status = TriggerStatus.STOPPED
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._obs.log("INFO", f"Trigger {self.config.name} stopped", "TriggerBase")
    
    def pause(self) -> None:
        """暂停触发器"""
        self.status = TriggerStatus.PAUSED
        self._obs.log("INFO", f"Trigger {self.config.name} paused", "TriggerBase")
    
    def resume(self) -> None:
        """恢复触发器"""
        self.status = TriggerStatus.RUNNING
        self._obs.log("INFO", f"Trigger {self.config.name} resumed", "TriggerBase")
    
    # ── 运行循环 ──
    
    def _run_loop(self) -> None:
        """主运行循环"""
        while not self._stop_event.is_set():
            if self.status == TriggerStatus.PAUSED:
                time.sleep(1.0)
                continue
            
            try:
                self._last_check_time = time.time()
                result = self.check()
                
                if result is not None:
                    self._on_trigger(result)
                
                self._error_count = 0  # 重置错误计数
                
            except Exception as e:
                self._error_count += 1
                self.status = TriggerStatus.ERROR
                self._obs.log("ERROR", f"Trigger {self.config.name} check failed: {str(e)}", "TriggerBase")
                
                if self._error_count >= self.config.max_retries:
                    self._obs.log("ERROR", f"Trigger {self.config.name} exceeded max retries, stopping", "TriggerBase")
                    break
                
                if self.config.retry_on_error:
                    time.sleep(self.config.retry_interval)
                    continue
            
            # 等待下一轮
            self._stop_event.wait(timeout=self.config.interval_seconds)
    
    def _on_trigger(self, event: Any) -> None:
        """触发事件时的处理"""
        self._last_trigger_time = time.time()
        self._trigger_count += 1
        self._publish(event)
    
    def _publish(self, event: Any) -> None:
        """发布事件到 EventBus（子类可覆盖）"""
        from events.event_bus import EventBus
        bus = EventBus()
        bus.publish(event, async_dispatch=True)
    
    # ── 状态查询 ──
    
    def get_status(self) -> Dict[str, Any]:
        """获取触发器状态"""
        return {
            "name": self.config.name,
            "status": self.status.value,
            "enabled": self.config.enabled,
            "interval": self.config.interval_seconds,
            "trigger_count": self._trigger_count,
            "error_count": self._error_count,
            "last_check": self._last_check_time,
            "last_trigger": self._last_trigger_time,
        }
