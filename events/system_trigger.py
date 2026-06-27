# -*- coding: utf-8 -*-
"""
SystemTrigger - 系统监控触发器

监控系统健康状态，包括内存、磁盘、数据源可用性。

触发条件（可配置）：
- 内存使用率超过 memory_threshold
- 磁盘使用率超过 disk_threshold
- 数据源不可用（离线+实时均失败）

配置参数（events.yaml）：
    triggers:
      system:
        enabled: true
        interval_seconds: 60
        memory_threshold: 80
        disk_threshold: 90
        data_source_check: true
"""

import os
import psutil
from datetime import datetime
from typing import Any, Dict, Optional

from events.trigger_base import TriggerBase, TriggerConfig
from events.event_bus import Event, EventType


class SystemTrigger(TriggerBase):
    """
    系统监控触发器

    Usage:
        trigger = SystemTrigger(memory_threshold=80)
        trigger.start()
    """

    def __init__(self, memory_threshold: float = 80.0,
                 disk_threshold: float = 90.0,
                 data_source_check: bool = True,
                 interval_seconds: float = 60.0):
        """
        Args:
            memory_threshold: 内存使用率告警阈值（%）
            disk_threshold: 磁盘使用率告警阈值（%）
            data_source_check: 是否检查数据源可用性
            interval_seconds: 检测间隔
        """
        config = TriggerConfig(
            name="system_trigger",
            interval_seconds=max(interval_seconds, 30.0),
        )
        super().__init__(config)

        self.memory_threshold = memory_threshold
        self.disk_threshold = disk_threshold
        self.data_source_check = data_source_check

        self._last_memory_alert: Optional[str] = None
        self._last_disk_alert: Optional[str] = None
        self._last_data_alert: Optional[str] = None
        self._data_source_recovered: bool = True

    def check(self) -> Optional[Event]:
        """检测系统异常"""
        today = datetime.now().strftime("%Y%m%d")

        # 1. 内存检测
        try:
            memory = psutil.virtual_memory()
            if memory.percent >= self.memory_threshold:
                alert_key = f"{today}_memory"
                if self._last_memory_alert != alert_key:
                    self._last_memory_alert = alert_key
                    return Event(
                        event_type=EventType.SYSTEM_ERROR,
                        payload={
                            "component": "memory",
                            "usage_percent": memory.percent,
                            "threshold": self.memory_threshold,
                            "available_mb": memory.available // (1024 * 1024),
                            "total_mb": memory.total // (1024 * 1024),
                        },
                        source="system_trigger",
                    )
            else:
                self._last_memory_alert = None
        except Exception as e:
            self._obs.log("WARN", f"Memory check failed: {str(e)}", "SystemTrigger")

        # 2. 磁盘检测
        try:
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100
            if disk_percent >= self.disk_threshold:
                alert_key = f"{today}_disk"
                if self._last_disk_alert != alert_key:
                    self._last_disk_alert = alert_key
                    return Event(
                        event_type=EventType.SYSTEM_ERROR,
                        payload={
                            "component": "disk",
                            "usage_percent": round(disk_percent, 2),
                            "threshold": self.disk_threshold,
                            "free_gb": disk.free // (1024 * 1024 * 1024),
                            "total_gb": disk.total // (1024 * 1024 * 1024),
                        },
                        source="system_trigger",
                    )
            else:
                self._last_disk_alert = None
        except Exception as e:
            self._obs.log("WARN", f"Disk check failed: {str(e)}", "SystemTrigger")

        # 3. 数据源检测
        if self.data_source_check:
            try:
                from utils.mootdx_provider import MootdxDataProvider
                provider = MootdxDataProvider()
                health = provider.health_check()

                offline_ok = health.get("offline_available", False)
                realtime_ok = health.get("realtime_available", False)

                if not offline_ok and not realtime_ok:
                    alert_key = f"{today}_datasource"
                    if self._last_data_alert != alert_key:
                        self._last_data_alert = alert_key
                        self._data_source_recovered = False
                        return Event(
                            event_type=EventType.DATA_SOURCE_DOWN,
                            payload={
                                "offline_available": offline_ok,
                                "realtime_available": realtime_ok,
                                "tdxdir_exists": health.get("tdxdir_exists", False),
                            },
                            source="system_trigger",
                        )
                else:
                    # 恢复检测
                    if not self._data_source_recovered:
                        self._data_source_recovered = True
                        self._last_data_alert = None
                        return Event(
                            event_type=EventType.DATA_SOURCE_RECOVER,
                            payload={
                                "offline_available": offline_ok,
                                "realtime_available": realtime_ok,
                            },
                            source="system_trigger",
                        )
                    self._last_data_alert = None

            except Exception as e:
                self._obs.log("WARN", f"Data source check failed: {str(e)}", "SystemTrigger")

        return None

    def get_status(self) -> Dict[str, Any]:
        """获取触发器状态"""
        base = super().get_status()
        try:
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            base.update({
                "memory_percent": memory.percent,
                "memory_threshold": self.memory_threshold,
                "disk_percent": round((disk.used / disk.total) * 100, 2),
                "disk_threshold": self.disk_threshold,
                "data_source_check": self.data_source_check,
            })
        except Exception:
            pass
        return base
