# -*- coding: utf-8 -*-
"""
PriceTrigger - 价格触发器

监控关注列表中的股票价格变化，当满足条件时触发事件。

触发条件（全部可配置）：
- 价格突破：涨幅超过 breakout_threshold
- 价格暴跌：跌幅超过 drop_threshold（绝对值）
- 成交量异动：成交量超过前5日均量的 volume_spike_ratio 倍

去重机制：每只股票的每个事件类型每天只触发一次。

配置参数（events.yaml）：
    triggers:
      price:
        enabled: true
        interval_seconds: 30
        watchlist: ["000001", "600519", "300750"]
        breakout_threshold: 0.05
        drop_threshold: 0.05
        volume_spike_ratio: 2.0
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from events.trigger_base import TriggerBase, TriggerConfig
from events.event_bus import Event, EventType
from utils.mootdx_provider import MootdxDataProvider
from core.observability import get_obs


class PriceTrigger(TriggerBase):
    """
    价格触发器

    Usage:
        trigger = PriceTrigger(watchlist=["000001"], breakout_threshold=0.05)
        trigger.start()
        ...
        trigger.stop()
    """

    def __init__(self, watchlist: List[str] = None,
                 breakout_threshold: float = 0.05,
                 drop_threshold: float = 0.05,
                 volume_spike_ratio: float = 2.0,
                 interval_seconds: float = 30.0):
        """
        Args:
            watchlist: 监控股票列表
            breakout_threshold: 突破阈值（涨幅比例，如 0.05 = 5%）
            drop_threshold: 暴跌阈值（跌幅比例，如 0.05 = 5%）
            volume_spike_ratio: 成交量异动倍率（如前5日平均的2倍）
            interval_seconds: 检测间隔
        """
        config = TriggerConfig(
            name="price_trigger",
            interval_seconds=max(interval_seconds, 10.0),  # 最低10秒
        )
        super().__init__(config)

        self.watchlist = watchlist or []
        self.breakout_threshold = breakout_threshold
        self.drop_threshold = abs(drop_threshold)  # 统一为正数
        self.volume_spike_ratio = volume_spike_ratio

        self._provider = MootdxDataProvider()
        self._triggered_today: Dict[str, Set[str]] = {}  # {date: {event_key}}
        self._price_history: Dict[str, List[float]] = {}  # 价格历史（用于计算均量）
        self._volume_history: Dict[str, List[float]] = {}  # 成交量历史

    def check(self) -> Optional[Event]:
        """
        检测价格异动

        Returns:
            Event 对象（如果检测到异动）或 None
        """
        if not self.watchlist:
            return None

        today = datetime.now().strftime("%Y%m%d")
        if today not in self._triggered_today:
            self._triggered_today[today] = set()

        try:
            # 批量获取实时行情
            quotes = self._provider.fetch_realtime_quote(self.watchlist)
            if quotes is None or len(quotes) == 0:
                return None

            for _, row in quotes.iterrows():
                code = str(row.get("code", ""))
                if not code:
                    continue

                price = float(row.get("price", 0))
                last_close = float(row.get("last_close", 0)) or 1
                volume = float(row.get("volume", 0))

                change_pct = (price - last_close) / last_close

                # 更新历史
                self._update_history(code, price, volume)

                # 检测突破
                if change_pct >= self.breakout_threshold:
                    event_key = f"{today}_{code}_breakout"
                    if event_key not in self._triggered_today[today]:
                        self._triggered_today[today].add(event_key)
                        return Event(
                            event_type=EventType.PRICE_BREAKOUT,
                            payload={
                                "code": code,
                                "price": round(price, 2),
                                "last_close": round(last_close, 2),
                                "change_pct": round(change_pct * 100, 2),
                                "volume": int(volume),
                            },
                            source="price_trigger",
                        )

                # 检测暴跌
                if change_pct <= -self.drop_threshold:
                    event_key = f"{today}_{code}_drop"
                    if event_key not in self._triggered_today[today]:
                        self._triggered_today[today].add(event_key)
                        return Event(
                            event_type=EventType.PRICE_DROP,
                            payload={
                                "code": code,
                                "price": round(price, 2),
                                "last_close": round(last_close, 2),
                                "change_pct": round(change_pct * 100, 2),
                                "volume": int(volume),
                            },
                            source="price_trigger",
                        )

                # 检测成交量异动
                avg_volume = self._get_avg_volume(code)
                if avg_volume > 0 and volume >= avg_volume * self.volume_spike_ratio:
                    event_key = f"{today}_{code}_volume_spike"
                    if event_key not in self._triggered_today[today]:
                        self._triggered_today[today].add(event_key)
                        return Event(
                            event_type=EventType.VOLUME_SPIKE,
                            payload={
                                "code": code,
                                "price": round(price, 2),
                                "volume": int(volume),
                                "avg_volume": int(avg_volume),
                                "ratio": round(volume / avg_volume, 2),
                            },
                            source="price_trigger",
                        )

        except Exception as e:
            self._obs.log("WARN", f"PriceTrigger check failed: {str(e)}", "PriceTrigger")

        return None

    def _update_history(self, code: str, price: float, volume: float) -> None:
        """更新价格和成交量历史"""
        if code not in self._price_history:
            self._price_history[code] = []
            self._volume_history[code] = []

        self._price_history[code].append(price)
        self._volume_history[code].append(volume)

        # 只保留最近5条
        if len(self._price_history[code]) > 5:
            self._price_history[code] = self._price_history[code][-5:]
        if len(self._volume_history[code]) > 5:
            self._volume_history[code] = self._volume_history[code][-5:]

    def _get_avg_volume(self, code: str) -> float:
        """获取前5次平均成交量"""
        if code not in self._volume_history or len(self._volume_history[code]) < 2:
            return 0
        # 排除最新一条（当前记录），取前几条平均
        prev_volumes = self._volume_history[code][:-1]
        return sum(prev_volumes) / len(prev_volumes) if prev_volumes else 0

    def get_status(self) -> Dict[str, Any]:
        """获取触发器状态"""
        base = super().get_status()
        base.update({
            "watchlist_count": len(self.watchlist),
            "breakout_threshold": self.breakout_threshold,
            "drop_threshold": self.drop_threshold,
            "volume_spike_ratio": self.volume_spike_ratio,
        })
        return base
